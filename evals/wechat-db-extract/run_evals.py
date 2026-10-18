#!/usr/bin/env python3
"""wechat-db-extract 导出脚本的回归测试。

用合成数据（虚构的 wxid、昵称、群名）构造最小 contact.db 和 message_0.db，
验证 export_contacts.py 和 export_recent_messages.py 的筛选与解析逻辑。
不需要真实微信数据，也不覆盖密钥提取（那一步只能在真机上验证）。

运行:
    uv run --project skills/wechat-db-extract python evals/wechat-db-extract/run_evals.py
"""
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import zstd
except ImportError:
    zstd = None

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "wechat-db-extract" / "scripts"
NOW = 1_700_000_000

CONTACTS = [
    # username, remark, nick_name, alias, local_type, flag, delete_flag, verify_flag
    ("wxid_alice", "Alice备注", "alice", "alice01", 1, 1, 0, 0),
    ("wxid_bob", "", "Bob", "", 1, 1, 0, 0),
    ("wxid_self", "", "Me", "", 1, 1, 0, 0),
    ("wxid_deleted", "", "Gone", "", 1, 1, 1, 0),
    ("wxid_oneway", "", "OneWay", "", 1, 0, 0, 0),
    ("10001@chatroom", "", "测试群", "", 2, 1, 0, 0),
    ("gh_demo", "", "示例公众号", "", 1, 1, 0, 8),
    ("filehelper", "", "文件传输助手", "", 1, 1, 0, 0),
]


def build_contact_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE contact (username TEXT, remark TEXT, nick_name TEXT, alias TEXT,"
        " local_type INTEGER, flag INTEGER, delete_flag INTEGER, verify_flag INTEGER)"
    )
    con.executemany("INSERT INTO contact VALUES (?,?,?,?,?,?,?,?)", CONTACTS)
    con.commit()
    con.close()


def build_message_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE Name2Id (user_name TEXT)")
    names = ["wxid_alice", "wxid_bob", "10001@chatroom"]
    con.executemany("INSERT INTO Name2Id (rowid, user_name) VALUES (?, ?)",
                    list(enumerate(names, start=1)))
    columns = ("local_id INTEGER, server_id INTEGER, local_type INTEGER, real_sender_id INTEGER,"
               " create_time INTEGER, source BLOB, message_content BLOB,"
               " WCDB_CT_message_content INTEGER, WCDB_CT_source INTEGER")

    def table(username):
        name = "Msg_" + hashlib.md5(username.encode("utf-8")).hexdigest()
        con.execute(f"CREATE TABLE {name} ({columns})")
        return name

    alice = table("wxid_alice")
    group = table("10001@chatroom")
    compressed = zstd.compress("压缩的消息".encode("utf-8")) if zstd else None
    con.executemany(f"INSERT INTO {alice} VALUES (?,?,?,?,?,?,?,?,?)", [
        (1, 101, 1, 1, NOW - 60, None, "你好", 0, 0),
        (2, 102, 1, 1, NOW - 7200, None, "窗口外的旧消息", 0, 0),
        (3, 103, 49, 1, NOW - 30, "<msg><title><![CDATA[一篇文章]]></title></msg>", "", 0, 0),
    ])
    rows = [(1, 201, 1, 2, NOW - 120, None, "wxid_bob:\n群里说一句", 0, 0)]
    if compressed:
        rows.append((2, 202, 1, 2, NOW - 90, None, compressed, 4, 0))
    con.executemany(f"INSERT INTO {group} VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def run(script: str, *args: str) -> None:
    subprocess.run([sys.executable, str(SCRIPTS / script), *args], check=True,
                   capture_output=True, encoding="utf-8")


def main() -> int:
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp) / "decrypted"
        contact_db = root / "contact" / "contact.db"
        build_contact_db(contact_db)
        build_message_db(root / "message" / "message_0.db")

        out = Path(tmp) / "friends.json"
        run("export_contacts.py", "--contact-db", str(contact_db), "--output", str(out),
            "--self-wxid", "wxid_self")
        friends = json.loads(out.read_text(encoding="utf-8"))
        check("好友只含双向、未删除的个人账号",
              sorted(r["username"] for r in friends["rows"]) == ["wxid_alice", "wxid_bob"])
        check("显示名优先用备注",
              any(r["display"] == "Alice备注" for r in friends["rows"]))

        out_all = Path(tmp) / "contacts.json"
        run("export_contacts.py", "--contact-db", str(contact_db), "--all", "--output", str(out_all))
        by_kind = json.loads(out_all.read_text(encoding="utf-8"))["by_kind"]
        check("--all 分类统计",
              by_kind.get("chatroom") == 1 and by_kind.get("official_account") == 1
              and by_kind.get("system") == 1 and by_kind.get("friend") == 5)

        out_dir = Path(tmp) / "exports"
        run("export_recent_messages.py", "--decrypted-root", str(root), "--minutes", "10",
            "--reference-epoch", str(NOW), "--output-dir", str(out_dir))
        payload = json.loads(next(out_dir.glob("wechat_recent_10min_*[0-9].json")).read_text(encoding="utf-8"))
        texts = [r["text"] for r in payload["records"]]
        check("时间窗口过滤掉旧消息", "窗口外的旧消息" not in texts)
        check("群聊正文去掉发送者前缀", "群里说一句" in texts)
        check("链接消息取 source 里的标题", "一篇文章" in texts)
        check("会话名映射到联系人显示名",
              {r["conversation"] for r in payload["records"]} == {"Alice备注", "测试群"})
        if zstd:
            check("zstd 压缩字段解压", "压缩的消息" in texts)
        else:
            print("SKIP zstd 压缩字段解压（未安装 zstd）")

    print(f"\n{len(failures)} 项失败" if failures else "\n全部通过")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
