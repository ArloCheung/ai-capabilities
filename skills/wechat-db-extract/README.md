# wechat-db-extract

从**自己本机、自己登录**的 Windows 微信 4.x 里提取数据库密钥，把 WCDB/SQLCipher4 加密库解密成标准 SQLite，再导出最近聊天记录和联系人列表。

## 用途

- 把最近 N 分钟的聊天导出成 JSON/CSV，交给 Agent 做总结、提取待办。
- 导出好友列表，或按好友 / 群聊 / 公众号 / 系统账号分类统计联系人。

## 用法

作为 Claude Skill 安装（见根目录 [README](../../README.md#使用-skills)），Agent 会按 [SKILL.md](SKILL.md) 的三步走。也可以直接运行脚本：

```powershell
# 管理员终端，微信保持登录
$env:PYTHONIOENCODING = "utf-8"
uv run --project . python scripts/wcdb_key_tool_windows.py extract --decrypt --output wechat_keys.json
uv run --project . python scripts/export_recent_messages.py --decrypted-root .\decrypted --minutes 30
uv run --project . python scripts/export_contacts.py --contact-db .\decrypted\contact\contact.db --all
```

| 脚本 | 作用 |
|---|---|
| `scripts/wcdb_key_tool_windows.py` | 提取密钥（runtime `Config.Cipher` 扫描 / raw key 内存扫描）、解密、回放 WAL |
| `scripts/export_recent_messages.py` | 从解密库导出最近 N 分钟消息 |
| `scripts/export_contacts.py` | 从解密的 `contact.db` 导出好友或全部联系人 |

## 限制

- 仅支持 Windows；Linux / macOS 只在 [references/key_extraction_notes.md](references/key_extraction_notes.md) 里记了思路。
- 需要管理员权限和微信登录状态；微信大版本升级可能让内存扫描失效。
- 最近消息导出只读 `message_0.db`，更早的分库（`message_1.db` …）需要自行扩展。
- 只用于自己的设备和账号。密钥、解密库、导出结果都是敏感数据，不要提交到任何公开仓库。

## 测试

```bash
uv run --project skills/wechat-db-extract python evals/wechat-db-extract/run_evals.py
```

用合成的 contact.db / message_0.db 验证两个导出脚本，不需要真实微信数据。密钥提取依赖真机，没有自动化测试。

## 致谢

密钥工具基于 [TANGandXUE/wcdb-key-tool](https://github.com/TANGandXUE/wcdb-key-tool)（MIT），见 [NOTICE.md](NOTICE.md)。
