#!/usr/bin/env python3
"""从已解密的微信 contact.db 导出联系人 / 好友列表。

contact 表的筛选逻辑（区分真实好友 vs 群聊/公众号/服务号/已删除）:
    local_type = 1        普通联系人（排除群聊 @chatroom、公众号 gh_）
    flag & 1   = 1        双向好友标志
    delete_flag = 0       未删除
    verify_flag = 0       已通过验证
再排除一批系统账号（filehelper / weixin 等）。

用法:
    # 只要真实好友:
    python export_contacts.py --contact-db ./decrypted/contact/contact.db --output friends.json
    # 导出全部联系人（含群聊/公众号）并带分类统计:
    python export_contacts.py --contact-db ./decrypted/contact/contact.db --all --output contacts.json
"""
import argparse
import json
import sqlite3
from pathlib import Path

# 微信内置的系统/功能账号，不算好友
SYSTEM_ACCOUNTS = {
    "filehelper", "fmessage", "medianote", "floatbottle", "qqmail",
    "tmessage", "qmessage", "weixin", "newsapp", "weibo", "qqsync",
    "feedsapp", "brandsessionholder",
}


def connect_ro(db_path: Path) -> sqlite3.Connection:
    """以只读方式打开，避免误写解密副本。"""
    con = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def export_contacts(args):
    db_path = Path(args.contact_db)
    if not db_path.exists():
        raise SystemExit(f"找不到 contact.db: {db_path}")

    exclude = set(SYSTEM_ACCOUNTS)
    if args.self_wxid:
        exclude.add(args.self_wxid)

    with connect_ro(db_path) as con:
        columns = {r[1] for r in con.execute("PRAGMA table_info(contact)")}

        if args.all:
            # 全部联系人 + 分类标签
            rows = con.execute(
                """SELECT username, remark, nick_name, alias, local_type,
                          flag, delete_flag, verify_flag
                   FROM contact ORDER BY local_type, username"""
            ).fetchall()
            data = []
            for r in rows:
                username = r["username"]
                if username.endswith("@chatroom"):
                    kind = "chatroom"
                elif username.startswith("gh_"):
                    kind = "official_account"
                elif username in SYSTEM_ACCOUNTS:
                    kind = "system"
                elif r["local_type"] == 1:
                    kind = "friend"
                else:
                    kind = "other"
                data.append({
                    "username": username,
                    "display": r["remark"] or r["nick_name"] or username,
                    "nick_name": r["nick_name"] or "",
                    "remark": r["remark"] or "",
                    "alias": r["alias"] or "",
                    "kind": kind,
                    "local_type": r["local_type"],
                })
            summary = {}
            for item in data:
                summary[item["kind"]] = summary.get(item["kind"], 0) + 1
            payload = {"count": len(data), "by_kind": summary, "rows": data}
        else:
            # 仅真实好友
            rows = con.execute(
                """SELECT username, remark, nick_name, alias
                   FROM contact
                   WHERE local_type = 1 AND (flag & 1) = 1
                     AND delete_flag = 0 AND verify_flag = 0
                     AND username NOT LIKE '%@chatroom'
                     AND username NOT LIKE 'gh_%'
                   ORDER BY COALESCE(NULLIF(remark,''), NULLIF(nick_name,''), username)
                            COLLATE NOCASE, username"""
            ).fetchall()
            data = []
            idx = 0
            for r in rows:
                if r["username"] in exclude:
                    continue
                idx += 1
                data.append({
                    "index": idx,
                    "display": r["remark"] or r["nick_name"] or r["username"],
                    "nick_name": r["nick_name"] or "",
                    "remark": r["remark"] or "",
                    "alias": r["alias"] or "",
                    "username": r["username"],
                })
            payload = {"count": len(data), "rows": data}

    out_path = Path(args.output)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"导出 {payload['count']} 条联系人 -> {out_path.resolve()}")
    if "by_kind" in payload:
        print("分类:", json.dumps(payload["by_kind"], ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="从已解密 contact.db 导出联系人/好友")
    parser.add_argument("--contact-db", required=True, help="解密后的 contact.db 路径")
    parser.add_argument("--output", default="contacts.json", help="输出 JSON 路径")
    parser.add_argument("--all", action="store_true",
                        help="导出全部联系人并带分类统计（默认只导出真实好友）")
    parser.add_argument("--self-wxid", help="自己的 wxid，从好友列表中排除（可选）")
    export_contacts(parser.parse_args())


if __name__ == "__main__":
    main()
