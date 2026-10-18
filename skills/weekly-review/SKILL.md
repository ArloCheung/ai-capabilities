---
name: weekly-review
description: 清理个人知识库的 inbox，把笔记归类到对应目录，补 frontmatter、标签和双链，并列出过期的工具卡片。用户说"周回顾""清理 inbox""weekly review"时使用。
---

# weekly-review

## 步骤
1. 读取 `$BRAIN_DIR/CLAUDE.md`，了解目录结构和写作规范。
2. 列出 `$BRAIN_DIR/00-inbox/` 下除 README 外的所有文件。
3. 对每个文件提出处理建议：目标目录、新文件名、标签、建议添加的双链。工具类内容转成 `20-tools/` 卡片格式。
4. **先把建议表给用户确认**，确认后再移动和修改。
5. 扫描 `20-tools/` 中 `last_verified` 超过 90 天的卡片，列出来提醒复核。
6. 最后汇报：处理了几篇、移到哪里、哪些需要用户补充。

## 规则
- 不删除任何文件；无价值的内容移到 `90-archive/`。
- 不大段改写用户原文，只补结构和链接。
