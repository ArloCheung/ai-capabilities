---
name: short-video
description: 用火山方舟（豆包 + Seedream + Seedance）把热榜话题或自己写的小故事做成竖屏 AI 短剧，并用 social-auto-upload 发布到抖音。在用户想抓热搜选题、写短视频剧本、出分镜、生成 AI 视频镜头、配音合成成片，或把成片发到抖音时使用。流水线用 LangGraph 编排，支持人工审核暂停、断点续跑、失败镜头单独重做。触发词：短视频、AI 短剧、热榜改编、分镜、Seedance、文生视频、配音合成、抖音发布。
---

# AI 短视频：从热榜到抖音

流水线代码就在本目录，安装和命令见 [README.md](README.md)。这里写的是**怎么用它做片子**：Agent 驱动这条流水线时要遵守的流程规则。

```
热榜(trends) ─▶ 豆包选题写故事(story) ─▶ 分镜(step1) ─▶ 定妆图/场景图(step2, Seedream)
   ─▶ 逐镜头视频(step3, Seedance) ─▶ 对白配音(step4, edge-tts) ─▶ 合成+字幕+AI 标识(step5, FFmpeg)
   ─▶ outbox ─▶ 抖音发布(social-auto-upload)
```

## 流程规则

视频生成按秒计费，一条 60 秒的片子重做几次就很贵。所以按下面的顺序来，每一步不满意就停在这一步改，不往下走。

1. **先定稿，再生成。** 故事和分镜（`work/.../1_storyboard/分镜脚本.md`）给用户看过、确认后，才能进入视频生成。用 `--review` 或 `--stop-before plan_videos` 让图在分镜和定妆图之后停下。
2. **生成前先报预估费用。** 按镜头数 × 秒数 × 当前模型单价估算，告诉用户再开始。没有用户明确同意，不调用 Seedance。
3. **先出低清样片，再出高清。** 样片用 `VIDEO_RESOLUTION=480p` 和 fast 模型（`VIDEO_MODEL=doubao-seedance-2-0-fast-260128`），整片看过节奏和表演，再换回正式参数重出。
4. **只重做不满意的镜头。** 删掉 `work/.../3_videos/s005.mp4` 后 `--fresh` 重跑，只会重新生成这一个镜头；其他镜头、配音、定妆图都复用。
5. **人物和音色固定复用。** 每个角色的定妆图（`2_assets/char_*.jpg`）和配音音色（分镜里的 `voice` + `pitch`）一旦定下，全片乃至同系列都不换。`DIALOGUE_MODE=tts` 时对白统一由 TTS 配，保证音色前后一致。
6. **不要旁白，纯对话推进。** 情节全部靠角色对白讲清楚，冲突点在开头一两句就交代明白。分镜的 `narration` 留空。
7. **真人质感。** 画风写成真人实拍质感、表演自然，不要漫画风（在分镜的 `style` 里写明）。
8. **不为省钱缩短时长，也不用静图冒充视频镜头。** 省钱靠定稿和样片，不靠砍内容。
9. **发布时勾选 AI 生成声明。** 成片右上角带 `AIGC_LABEL`（默认“AI生成”），上传抖音时 `--declaration "内容由AI生成"`。发布是对外动作，必须等用户确认标题、简介、标签后再执行。

## 内容红线

- 热榜条目先过 `DAILY_BLOCKWORDS` 敏感词过滤（时政、灾难、伤亡、刑案、未成年人等直接丢弃）。
- 故事原创虚构：不出现真实人名、品牌名、机构名，只借用热点的梗或情境。
- 不写血腥、暴力、低俗内容。

## 常用命令

```powershell
uv run trends_graph.py --top 10                       # 看今天抖音、微博热榜
uv run run.py daily --review on                       # 热榜 → 故事 → 分镜 → 定妆图，然后停下等审核
uv run run.py review --thread daily-<日期> --approve  # 确认后继续出视频、配音、合成
uv run run.py novel --input samples/crab/story.txt --storyboard samples/crab/storyboard.json --portrait --workdir crab --stop-before plan_videos
```

不花钱验证整条链路：任何命令加 `--mock`（占位画面 + 真实配音、字幕、拼接）。

## 发布到抖音

见 [references/douyin-publish.md](references/douyin-publish.md)。
