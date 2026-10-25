"""从热榜里挑一个适合改编的话题，写成原创小故事（豆包大模型）。

输出：daily/<日期>/0_story/story.json（选题、理由、标题）和 story.txt（故事正文，交给分镜步骤）
"""
import argparse
import datetime as dt
import json

from . import config
from .utils import load_json, log, save_json

SYSTEM = """你是短视频编剧，擅长把当天的网络热梗、趣闻写成 60 秒左右、有反转或笑点的原创小故事。

第一步：选题。从给出的热榜条目中选 1 个最适合的，标准：
- 轻松、有趣、有画面感，适合拍成短剧（生活趣事、热梗、反差萌、职场/校园/家庭日常、动物、科技新奇事等）
- 必须能从标题和简介看懂它在说什么；看不懂、需要背景知识才能理解的梗不要选
- 不选：时政、军事、外交、灾难事故、伤亡、刑事案件、疾病、宗教民族、涉及未成年人、明星或真实个人的隐私与争议
- 避开“最近已用过的话题”

第二步：写故事。要求：
- 原创虚构，只借用热点的“梗”或情境；不出现任何真实人名、真实品牌名、真实机构名，人物全部虚构
- 正文 {chars} 字左右（这决定视频长度，不要超），2~3 个角色，1~2 个场景
- 结构：开头 1 句抓人 → 冲突/铺垫 → 结尾反转或笑点；以对白为主，少量旁白
- 对白用中文引号“”，写清楚是谁说的
- 不写血腥、暴力、低俗内容

只输出 JSON：
{{"topic":"选中的热榜标题","source":"来源平台","reason":"为什么选它（一句话）",
  "title":"故事标题（10字内）","logline":"一句话梗概","story":"故事正文"}}"""


def pick_and_write(items, history, ark=None):
    from .ark_client import Ark
    ark = ark or Ark()
    brief = [{"source": x["source"], "title": x["title"], "desc": x.get("desc", "")} for x in items[:80]]
    user = ("最近已用过的话题：" + json.dumps(history[-30:], ensure_ascii=False)
            + "\n\n今日热榜：\n" + json.dumps(brief, ensure_ascii=False))
    res = ark.chat_json(SYSTEM.format(chars=config.DAILY_STORY_CHARS), user, temperature=0.9)
    for k in ("topic", "title", "story"):
        if not res.get(k):
            raise ValueError(f"大模型返回缺少 {k}: {res}")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(dt.date.today()))
    a = ap.parse_args(argv)
    day = config.DAILY_DIR / a.date
    trends = load_json(day / "0_trends" / "trends.json")["items"]
    hist_file = config.DAILY_DIR / "history.json"
    history = load_json(hist_file) if hist_file.exists() else []
    res = pick_and_write(trends, [h["topic"] for h in history])
    out = day / "0_story"
    save_json({**res, "date": a.date}, out / "story.json")
    (out / "story.txt").write_text(f"{res['title']}\n{res['story']}", encoding="utf-8")
    history.append({"date": a.date, "topic": res["topic"], "title": res["title"]})
    save_json(history[-200:], hist_file)
    log(f"[故事] 选题：{res['topic']}（{res.get('source', '')}）→《{res['title']}》{len(res['story'])} 字")


if __name__ == "__main__":
    main()
