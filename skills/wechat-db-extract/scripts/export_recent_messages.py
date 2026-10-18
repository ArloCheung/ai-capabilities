#!/usr/bin/env python3
"""从已解密的微信数据库导出最近 N 分钟的聊天记录。

读取解密后的 message_0.db + contact.db，按时间窗口过滤 Msg_* 表，
把消息内容（含 zstd 压缩字段）还原为文本，输出 JSON / CSV / summary。

用法:
    python export_recent_messages.py \
        --decrypted-root ./decrypted \
        --minutes 10 \
        --output-dir ./wechat_recent_exports

时间参照:
    默认以 --source-message-db 的文件修改时间为"现在"（这是原始加密库最后
    写入的时刻，比解密副本的 mtime 更接近真实时间）。未提供该参数时退回到
    解密库自身的 mtime；也可用 --reference-epoch 指定一个 Unix 秒时间戳。
"""
import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import re
import sqlite3
from pathlib import Path

try:
    import zstd
except ImportError:
    zstd = None


def local_time(timestamp: int) -> str:
    return dt.datetime.fromtimestamp(timestamp).isoformat(sep=" ", timespec="seconds")


def decompress_value(value, compression_type):
    """微信把部分文本字段用 zstd 压缩存储，WCDB_CT_* 列标记压缩类型（4=zstd）。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if not isinstance(value, (bytes, bytearray)):
        return str(value)
    if compression_type == 4 and zstd is not None:
        try:
            return zstd.decompress(value).decode("utf-8", errors="replace")
        except Exception:
            pass
    try:
        return bytes(value).decode("utf-8", errors="replace")
    except Exception:
        return repr(value)


def clean_text(text: str) -> str:
    """去掉群聊消息正文前面的 "wxid_xxx:\n" / "发送者:\n" 前缀。"""
    if not text:
        return ""
    text = re.sub(r"^wxid_[a-z0-9_]+:\s*\n?", "", text)
    text = re.sub(r"^[A-Za-z0-9_.-]+:\s*\n", "", text)
    return text.strip()


def extract_title(xml_text: str) -> str:
    """链接/小程序等消息的正文为空，标题在 source 字段的 <title> 里。"""
    if not xml_text:
        return ""
    for pattern in (
        r"<title><!\[CDATA\[(.*?)\]\]></title>",
        r"<title>(.*?)</title>",
    ):
        match = re.search(pattern, xml_text, re.DOTALL)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def display_name(username: str, contacts: dict) -> str:
    if not username:
        return ""
    return contacts.get(username, username)


def load_contacts(contact_db: Path) -> dict:
    """username -> 备注名/昵称/username（优先备注）。"""
    contacts = {}
    with sqlite3.connect(contact_db) as conn:
        for username, remark, nick_name in conn.execute(
            "SELECT username, remark, nick_name FROM contact"
        ):
            contacts[username] = remark or nick_name or username
    return contacts


def load_name_maps(message_db: Path):
    """Msg_* 表名的后缀是 username 的 md5；Name2Id 把 rowid 映射回 username。"""
    suffix_to_username = {}
    rowid_to_username = {}
    with sqlite3.connect(message_db) as conn:
        for rowid, username in conn.execute("SELECT rowid, user_name FROM Name2Id"):
            rowid_to_username[rowid] = username
            suffix_to_username[hashlib.md5(username.encode("utf-8")).hexdigest()] = username
    return suffix_to_username, rowid_to_username


def export_recent(args):
    db_root = Path(args.decrypted_root)
    message_db = db_root / "message" / "message_0.db"
    contact_db = db_root / "contact" / "contact.db"

    if not message_db.exists():
        raise SystemExit(f"找不到消息库: {message_db}（--decrypted-root 是否指向解密目录？）")
    if not contact_db.exists():
        raise SystemExit(f"找不到联系人库: {contact_db}")

    if args.reference_epoch:
        reference_time = args.reference_epoch
    elif args.source_message_db and Path(args.source_message_db).exists():
        reference_time = int(Path(args.source_message_db).stat().st_mtime)
    else:
        reference_time = int(message_db.stat().st_mtime)

    cutoff = reference_time - args.minutes * 60
    contacts = load_contacts(contact_db)
    suffix_to_username, rowid_to_username = load_name_maps(message_db)

    records = []
    with sqlite3.connect(message_db) as conn:
        conn.row_factory = sqlite3.Row
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
            )
        ]
        for table in tables:
            suffix = table.removeprefix("Msg_")
            conversation_id = suffix_to_username.get(suffix, suffix)
            conversation_name = display_name(conversation_id, contacts)
            rows = conn.execute(
                f"""
                SELECT local_id, server_id, local_type, real_sender_id, create_time,
                       source, message_content, WCDB_CT_message_content, WCDB_CT_source
                FROM {table}
                WHERE create_time >= ? AND create_time <= ?
                ORDER BY create_time ASC, local_id ASC
                """,
                (cutoff, reference_time),
            )
            for row in rows:
                sender_id = rowid_to_username.get(row["real_sender_id"], "")
                content = decompress_value(
                    row["message_content"], row["WCDB_CT_message_content"]
                )
                source = decompress_value(row["source"], row["WCDB_CT_source"])
                text = clean_text(content)
                if not text:
                    text = extract_title(source) or clean_text(source)
                records.append(
                    {
                        "time": local_time(row["create_time"]),
                        "timestamp": row["create_time"],
                        "conversation_id": conversation_id,
                        "conversation": conversation_name,
                        "sender_id": sender_id,
                        "sender": display_name(sender_id, contacts),
                        "local_type": row["local_type"],
                        "local_id": row["local_id"],
                        "server_id": row["server_id"],
                        "text": text,
                    }
                )

    records.sort(key=lambda item: (item["timestamp"], item["conversation"], item["local_id"]))

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.fromtimestamp(reference_time).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"wechat_recent_{args.minutes}min_{stamp}.json"
    csv_path = out_dir / f"wechat_recent_{args.minutes}min_{stamp}.csv"
    meta_path = out_dir / f"wechat_recent_{args.minutes}min_{stamp}_summary.json"

    payload = {
        "window": {
            "minutes": args.minutes,
            "reference_time": local_time(reference_time),
            "cutoff_time": local_time(cutoff),
            "reference_epoch": reference_time,
            "cutoff_epoch": cutoff,
        },
        "record_count": len(records),
        "records": records,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "time", "conversation", "sender", "local_type", "text",
                "conversation_id", "sender_id", "local_id", "server_id",
            ],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(records)

    summary = {
        "window": payload["window"],
        "record_count": len(records),
        "conversations": sorted(
            {
                record["conversation"]: sum(
                    1 for item in records if item["conversation"] == record["conversation"]
                )
                for record in records
            }.items(),
            key=lambda item: item[1],
            reverse=True,
        ),
        "json": str(json_path.resolve()),
        "csv": str(csv_path.resolve()),
    }
    meta_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="导出最近 N 分钟微信聊天记录")
    parser.add_argument("--decrypted-root", required=True,
                        help="解密后的数据库根目录（内含 message/ 和 contact/ 子目录）")
    parser.add_argument("--minutes", type=int, default=10, help="时间窗口分钟数，默认 10")
    parser.add_argument("--source-message-db",
                        help="原始加密 message_0.db 路径，用其 mtime 作为时间参照（可选）")
    parser.add_argument("--reference-epoch", type=int,
                        help="手动指定参照时间（Unix 秒），优先级最高")
    parser.add_argument("--output-dir", default="wechat_recent_exports",
                        help="输出目录，默认 ./wechat_recent_exports")
    export_recent(parser.parse_args())


if __name__ == "__main__":
    main()
