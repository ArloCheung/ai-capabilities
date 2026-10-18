---
name: wechat-db-extract
description: 提取并解析本机微信（WeChat/Weixin 4.x）数据库。在用户想从自己本机、自己登录的微信里导出聊天记录、联系人/好友列表，或需要提取微信数据库密钥（WCDB / SQLCipher4）、解密 message/contact 等 .db 文件时使用。涵盖 Windows 的 raw key 内存扫描与 4.1+ runtime Config.Cipher 扫描、PBKDF2 密钥派生、AES-256-CBC 逐页解密、加密 WAL 回放，以及对解密后数据库的最近消息导出和联系人分类导出。触发词：微信导出、微信聊天记录、微信数据库、wcdb、SQLCipher、微信密钥、decrypt wechat、export wechat messages/contacts。
---

# 微信数据库提取与解析

把本机微信数据库从加密的 WCDB/SQLCipher4 格式提取出密钥、解密成标准 SQLite，
再解析出聊天记录和联系人。流程分三步：**提取密钥 → 解密 → 解析**。

下文的 `<skill>` 指本 Skill 所在目录（含 `pyproject.toml`）。所有命令用 uv 运行：
`uv run --project <skill> python <skill>/scripts/<脚本>.py ...`，首次运行会自动装好依赖。

## 适用范围与前提（务必先确认）

只用于**用户本人拥有、且当前已登录**的那台 Windows 电脑上的**自己的**微信账号。
工具只读地扫描微信自己进程的内存来取出用户自己数据库的密钥，不接触网络、不修改
微信行为、不针对任何他人账号。如果请求涉及他人设备或他人账号，停下来说明这超出
本工具用途。

运行前提：
- Windows，微信处于**登录**状态。
- 以**管理员身份**运行终端（读取进程内存需要足够权限）。
- 已安装 [uv](https://docs.astral.sh/uv/)，Python 3.10+（密钥工具用系统自带的 `bcrypt.dll`）。
- PowerShell 下先执行 `$env:PYTHONIOENCODING = "utf-8"`，避免中文输出乱码。

数据库目录形如 `<数据盘>\...\xwechat_files\<wxid_目录>\db_storage`。脚本会读
`%APPDATA%\Tencent\xwechat\config\*.ini` 自动检测，检测不到再用 `--db-dir` 指定。

## 先找已有密钥

如果设置了 `BRAIN_DIR`，先看 `$BRAIN_DIR/secrets/` 下有没有本机账号的密钥文件
（`wechat-db-keys-*.json`）。微信不重新登录时密钥不变，有就直接跳到第 1 步的
`decrypt`，不必再扫内存。

## 第 1 步：提取密钥 + 解密数据库

```powershell
uv run --project <skill> python <skill>/scripts/wcdb_key_tool_windows.py extract --decrypt `
    --db-dir "<...>\xwechat_files\<wxid_目录>\db_storage" `
    --output wechat_keys.json
```

它会：
1. 优先用**只读 runtime `Config.Cipher` 扫描**拿微信 4.1+ 的密钥，老版本回退到
   **raw key 内存扫描**；
2. 候选值必须通过 **HMAC-SHA512 校验**才算数；
3. 对每个库做 **AES-256-CBC 逐页解密**，并回放加密 WAL 里已提交的页，避免漏掉
   最近几分钟的消息。

- 成功后生成密钥文件和解密目录 `decrypted/`。`--db-dir` 省略时自动检测。
- 已有密钥文件时只解密：`... wcdb_key_tool_windows.py decrypt --keys <密钥文件> --output decrypted`。
- 4.1+ 且 runtime 扫描失败：用其他手段拿到 32 字节 passphrase 后
  `set-passphrase <64位hex>`，再 `extract`。`capture-experimental` 是未经真机验证的
  研究性路线，不要当成可用方案。
- 建议解密后按账号改名：`Rename-Item .\decrypted .\decrypted_<wxid>`。

解密目录的常用库：
- `message/message_0.db` … `message_N.db`：聊天消息，按会话分 `Msg_<md5>` 表
- `contact/contact.db`：联系人
- `session/session.db`：会话列表
- `head_image/`、`emoticon/`、`favorite/`、`sns/`：头像、表情、收藏、朋友圈

## 第 2 步：导出最近聊天记录

```powershell
uv run --project <skill> python <skill>/scripts/export_recent_messages.py `
    --decrypted-root .\decrypted `
    --minutes 30 `
    --source-message-db "<...>\db_storage\message\message_0.db" `
    --output-dir .\wechat_recent_exports
```

输出 JSON + CSV + summary。自动处理 zstd 压缩字段、群聊正文的发送者前缀、
链接/小程序消息的 `<title>`、`Msg_<md5>` 表名到会话名的映射。

- `--minutes` 控制时间窗口。
- `--source-message-db`（可选）用原始加密库的 mtime 作"现在"，比解密副本准；
  也可用 `--reference-epoch <unix秒>`。
- 字段说明见 [references/db_schema.md](references/db_schema.md)。

## 第 3 步：导出联系人 / 好友

```powershell
# 只要真实双向好友
uv run --project <skill> python <skill>/scripts/export_contacts.py --contact-db .\decrypted\contact\contact.db --output friends.json
# 全部联系人，按 friend/chatroom/official_account/system/other 分类
uv run --project <skill> python <skill>/scripts/export_contacts.py --contact-db .\decrypted\contact\contact.db --all --output contacts.json
```

- `--self-wxid <自己的wxid>`（可选）把自己从好友列表排除。

## 产物放哪里

- **密钥文件**：可以存进用户的私有知识库 `$BRAIN_DIR/secrets/`，方便下次复用。
  **绝不**写进任何公开仓库（包括本仓库）。
- **解密库和导出结果**：含聊天内容和他人信息，放在工作目录的临时位置，用完删除，
  不要提交到任何 git 仓库。

```powershell
Remove-Item .\decrypted* -Recurse -Force
Remove-Item .\wechat_recent_exports -Recurse -Force
```

passphrase 会缓存在 `~/.wcdb-key-tool/wechat-passphrase.json`，不需要时一并删除。

## 原理速览

微信 4.1+ 内存里只保留 passphrase，每库真实密钥要用该库自己的 16 字节 salt 做
`PBKDF2-HMAC-SHA512`（256,000 轮）派生出 32 字节 AES-256 密钥，再用 HMAC-SHA512
校验第一页，最后 AES-256-CBC 逐页解密。背景、跨平台思路和致谢见
[references/key_extraction_notes.md](references/key_extraction_notes.md)。
