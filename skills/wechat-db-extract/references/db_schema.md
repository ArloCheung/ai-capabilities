# 解密后微信数据库字段参考

## message/message_N.db — 聊天消息

- 每个会话一张表 `Msg_<md5>`，其中 `<md5>` = `md5(会话username)`。
- `Name2Id` 表：`rowid -> user_name`，用于把 `real_sender_id` 还原成发送者 username，
  也用于反查表名后缀对应的会话 username。

`Msg_*` 常用列：

| 列 | 含义 |
|---|---|
| `local_id` | 本地自增 id |
| `server_id` | 服务器消息 id |
| `local_type` | 消息类型（1=文本，3=图片，34=语音，43=视频，49=链接/小程序/文件 等） |
| `real_sender_id` | 发送者，对应 `Name2Id.rowid` |
| `create_time` | 发送时间，**Unix 秒** |
| `message_content` | 正文，可能被压缩 |
| `WCDB_CT_message_content` | 压缩类型，`4` = zstd |
| `source` | 附加 XML（链接/小程序的标题等在这里的 `<title>`） |
| `WCDB_CT_source` | `source` 的压缩类型 |

解析要点：
- `WCDB_CT_*` 为 4 时对应字段是 zstd 压缩的 bytes，需要 `zstd.decompress` 再按 utf-8 解码。
- 群聊文本正文常带 `wxid_xxx:\n` 或 `发送者:\n` 前缀，需要清理。
- 正文为空的消息（链接/小程序/文件），标题在 `source` 的 `<title><![CDATA[...]]></title>`。
- 时间参照：原始加密 `message_0.db` 的文件 mtime 最接近"最后写入时刻"，比解密副本准。

## contact/contact.db — 联系人

`contact` 表常用列与筛选标志：

| 列 | 含义 |
|---|---|
| `username` | 唯一标识：`wxid_*` / `*@chatroom`（群）/ `gh_*`（公众号/服务号） |
| `remark` | 备注名 |
| `nick_name` | 昵称 |
| `alias` | 微信号 |
| `local_type` | 1=普通联系人 |
| `flag` | 位标志，`flag & 1 = 1` 表示双向好友 |
| `delete_flag` | 0=未删除 |
| `verify_flag` | 0=已通过验证 |

真实好友的判定：`local_type=1 AND (flag&1)=1 AND delete_flag=0 AND verify_flag=0`，
再排除 `%@chatroom`、`gh_%` 和内置系统账号
（filehelper / fmessage / medianote / floatbottle / qqmail / tmessage / qmessage /
weixin / newsapp / weibo / qqsync / feedsapp / brandsessionholder）。

显示名优先级：`remark` > `nick_name` > `username`。

## WAL 说明

解密工具产出的是已合并、干净的 SQLite 文件。若要解析**实时**数据库快照（边运行边读），
需要额外校验加密 WAL 的滚动校验和并只回放已提交帧——这超出本 skill 的常规流程，
常规做法是先用密钥工具解密出静态副本再解析。
