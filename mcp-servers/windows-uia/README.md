# windows-uia MCP Server 🚧

让 LLM Agent 通过 Windows UI Automation（UIA）**结构化地**读取和操作桌面应用，而不是依赖截图识别。

## 为什么
- 企业软件（SAP GUI、Office、ERP 客户端）集中在 Windows 桌面。
- UIA 控件树能给出控件名称、类型、状态，比纯截图式 Computer Use 更稳定、成本更低。
- 这是传统 RPA 选择器思路和 LLM 决策的结合。

## 当前工具
| 工具 | 说明 |
|---|---|
| `list_windows` | 列出桌面顶层窗口 |
| `get_window_tree` | 获取指定窗口的控件树（可限制深度） |

## 计划
- [ ] `click_element`：按名称 / 类型定位并点击
- [ ] `set_text`：输入文本
- [ ] `read_table`：读取表格 / 列表控件
- [ ] 操作前确认与操作日志
- [ ] 演示 GIF

## 运行（Windows 原生）

```powershell
uv sync
uv run python server.py
```

在 Claude Code 中注册：

```powershell
claude mcp add windows-uia -- uv --directory <本目录绝对路径> run python server.py
```

## 限制
- 只能在 Windows 原生运行。
- 部分应用（自绘界面、部分 Java / Electron 应用）UIA 信息不完整。
