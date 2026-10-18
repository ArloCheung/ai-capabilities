# 微信数据库密钥提取原理与背景

微信数据库用 WCDB（基于 SQLCipher4）加密。本工具只做一件事：把从微信自己的进程里
**合法地取出自己账号**数据库密钥的思路和代码整理出来——不采集、不批量、不接触任何
服务器通信。

## 核心密码学逻辑（三平台通用）

1. **拿到密钥原料**（按微信版本二选一）
   - 老版本（4.0.x）：微信把 `raw key + salt` 拼成十六进制明文缓存在进程内存里，
     直接内存扫描 `x'<hex>'` 即可拿到。
   - 新版本（4.1+）：内存里只剩 passphrase。passphrase 只在**登录时**算一次后常驻，
     不再重算。
2. **PBKDF2 派生每库真实密钥**：对每个 .db 文件，用它自己的 16 字节 salt 做
   `PBKDF2-HMAC-SHA512`、**256,000 轮**，派生出该库专属的 32 字节 AES-256 密钥。
3. **HMAC 校验**：派生/扫描到的密钥必须对数据库第一页做 `HMAC-SHA512` 校验，和库里
   存的 HMAC 对上才算真的对。这是判断是否"抓对"的唯一标准。
4. **AES-256-CBC 逐页解密**：还原成标准 SQLite 文件（页大小 4096，每页尾部保留
   IV(16)+HMAC(64)）。

## Windows 主路径：只读 runtime `Config.Cipher` 扫描

微信 4.1+ 会把可用的 `com.Tencent.WCDB.Config.Cipher` 相关对象留在进程内存里。
脚本在进程内定位该对象，解码候选 `x'<64hex key><32hex salt>'` 片段，再用数据库
HMAC 验证；扫不到时自动回退到老版本内存扫描。调试器（若用到）只在密钥计算瞬间读
一次寄存器/内存就立即 detach，不改微信行为、不触发封号。

## 跨平台取原料的差异（仅背景，本 skill 只含 Windows 脚本）

- **Linux**：微信二进制无可用系统符号，用 ELF 静态分析在 `.rodata` 找 WCDB 特征
  字符串、顺交叉引用定位处理密钥的函数入口，再用 GDB 断点；触发时需退出登录再
  重新登录以产生一次新的密钥计算。
- **macOS**：微信直接调用系统 `CommonCrypto` 的 `CCKeyDerivationPBKDF`（公开符号），
  用 LLDB 断在该函数上即可，无需逆向微信自身；首次需对 App 重签名去掉 Hardened
  Runtime 以允许 `task_for_pid`。

## passphrase 缓存

提取到的 passphrase 存在 `~/.wcdb-key-tool/wechat-passphrase.json`（权限 600，仅当前
用户可读），之后再 `extract` 会优先用它派生，省去重新触发计算的步骤。

## 致谢 / Credits

- kkocdko — Linux 上 GDB 断点法的原始思路
- wxchat-export — Linux 上 ELF 静态分析方法
- ylytdeng/wechat-decrypt — 内存扫描基础代码
- TANGandXUE — PBKDF2 派生方法 + macOS/Windows 移植 + 完整集成
  （https://github.com/TANGandXUE/wcdb-key-tool，MIT License）
