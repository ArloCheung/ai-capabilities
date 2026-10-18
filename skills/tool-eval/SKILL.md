---
name: tool-eval
description: 给定一个 AI 工具名，查资料并生成工具卡片初稿，包含定价、国内可用性、Windows 支持、适合场景和坑。用户说"评估一下 X""给 X 建工具卡片"时使用。
---

# tool-eval

## 步骤
1. 用网络搜索查官方文档、定价页、GitHub，以及近 3 个月的实际使用反馈。
2. 按以下字段生成卡片，写入 `$BRAIN_DIR/20-tools/<tool-name>.md`：

```markdown
---
name:
category: model | agent-framework | mcp | coding-agent | rpa | saas | dev-infra
pricing:
china_access: 直连 | 需代理 | 不可用
windows_support: 原生 | WSL | 无
rating:
last_verified: <今天>
tags: [tool]
---
## 适合场景
## 坑
## 我的用法 / 链接到能力库
## 来源
```

3. `rating` 和"我的用法"留空，由用户试用后填写。
4. 无法确认的字段写"待核实"，不要猜测。
5. 每条事实附来源链接。
