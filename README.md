# ai-capabilities

个人 AI 能力库：可直接安装、调用的 Agent 资产。

作者：张鸿生（[ArloCheung](https://github.com/ArloCheung)）。RPA / 自动化交付约 6 年，UiARD 认证。RPA 作品见 [UiPathProjects](https://github.com/ArloCheung/UiPathProjects)。

## 能力清单

| 能力 | 类型 | 状态 | 说明 |
|---|---|---|---|
| [windows-uia](mcp-servers/windows-uia/) | MCP Server | 🚧 开发中 | 让 LLM Agent 通过 UI Automation 读取和操作 Windows 桌面应用 |
| [capture](skills/capture/) | Skill | ✅ | 把对话结论整理成笔记，存入知识库 inbox |
| [weekly-review](skills/weekly-review/) | Skill | ✅ | 清理 inbox：归类、补 frontmatter 和双链 |
| [tool-eval](skills/tool-eval/) | Skill | ✅ | 给一个工具名，生成工具卡片初稿 |
| [interview-prep](skills/interview-prep/) | Skill | ✅ | 从项目复盘中提炼 STAR 故事 |
| [wechat-db-extract](skills/wechat-db-extract/) | Skill | ✅ | 提取本机微信 4.x 数据库密钥并解密，导出最近聊天记录和联系人（Windows） |

## 目录

```
skills/        Claude Skills（每个目录一个 SKILL.md）
mcp-servers/   MCP Server
prompts/       经过验证的 Prompt，附用法和样例
templates/     Agent 项目脚手架
evals/         各能力的测试用例
```

## 使用 Skills

把 `skills/` 下的目录复制或链接到 Claude Code 的 skills 目录：

```bash
# Linux / WSL
ln -s "$(pwd)/skills/capture" ~/.claude/skills/capture
```

```powershell
# Windows（需要开发者模式或管理员权限）
New-Item -ItemType SymbolicLink -Path "$HOME\.claude\skills\capture" -Target "$PWD\skills\capture"
```

部分 Skill 需要知道知识库位置，请设置环境变量 `BRAIN_DIR`。

## 提交前密钥扫描

仓库自带 pre-commit 钩子（`.githooks/pre-commit`），提交前用 [gitleaks](https://github.com/gitleaks/gitleaks) 扫描暂存区，发现疑似密钥会阻止提交。`.gitleaks.toml` 在默认规则外补充了微信数据库密钥的规则；`.gitignore` 排除了密钥文件、解密库和导出结果。clone 后执行一次：

```bash
# 安装 gitleaks（Windows 示例，macOS 可用 brew install gitleaks）
winget install --id Gitleaks.Gitleaks -e

# 启用仓库自带的钩子
git config core.hooksPath .githooks
```

## License

MIT
