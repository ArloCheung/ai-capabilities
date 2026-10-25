# 发布到抖音（social-auto-upload）

成片发布用开源项目 [social-auto-upload](https://github.com/dreammis/social-auto-upload)（`sau` 命令行，基于 Playwright 驱动抖音创作者中心网页）。本仓库不包含它的代码，也不包含任何登录 cookie。

## 安装

按它的 [docs/install.md](https://github.com/dreammis/social-auto-upload/blob/main/docs/install.md)：

```powershell
git clone https://github.com/dreammis/social-auto-upload.git
cd social-auto-upload
uv venv
uv pip install -e .
patchright install chromium
```

## 登录（一次）

```powershell
sau douyin login --account <账号名>      # 弹出浏览器扫码登录，cookie 存在 social-auto-upload/cookies/ 下
sau douyin check --account <账号名>      # 检查登录是否还有效
```

`<账号名>` 是你自己起的本地名字，用来区分多个账号。cookie 文件等同于账号登录态，**不要提交到任何仓库**。

## 上传

```powershell
sau douyin upload-video --account <账号名> `
  --file "<本项目>/work/daily/outbox/2026-10-19_一只蟹的两种吃法.mp4" `
  --title "一只蟹的两种吃法" `
  --desc "南方人拆蟹 vs 东北人吃蟹" `
  --tags 生活,搞笑,AI短剧 `
  --declaration "内容由AI生成"
```

- `--declaration` 填抖音「自主声明」弹窗里的选项原文，AI 生成的片子选 **内容由AI生成**。不传就不设声明，所以 AI 短剧一定要带上。
- `--schedule "2026-10-20 18:00"` 定时发布；`--thumbnail` 指定 3:4 竖版封面。
- 想用本机已安装的 Chrome 而不是 Playwright 自带的 Chromium，可以设置浏览器 channel（取决于你用的 social-auto-upload 版本是否支持，例如环境变量 `SAU_BROWSER_CHANNEL=chrome`）。

## 发布前检查

1. 成片看过一遍：字幕、配音、AI 标识都在。
2. 标题、简介、标签由人确认。发布是公开动作，Agent 不应自行决定发布。
3. 带上 `--declaration "内容由AI生成"`。
