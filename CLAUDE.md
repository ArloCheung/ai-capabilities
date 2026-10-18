# 给 Agent 的说明（ai-capabilities 仓库）

这是**公开仓库**，所有内容都会被他人看到。

## 规则
- 不写入任何公司内部数据、客户名称、内网地址、账号密钥、个人本机路径。
- 链接用标准 Markdown `[text](path.md)`，不用 Obsidian 双链。
- 每个能力一个目录，包含：README（用途、用法、限制）和测试样例（放 `evals/`）。
- 新增能力后，同步更新根目录 README 的能力清单。
- Skill 遵循 `skills/<name>/SKILL.md` 结构，frontmatter 写 `name` 和 `description`。
- Python 项目用 uv 管理，`pyproject.toml` 声明依赖；代码需同时考虑 Windows 原生运行（UTF-8、路径）。
