"""指定热梗 + 原内容 → 豆包写原创小故事（补原 story.py 只能"让豆包自己挑题"的空缺）。

  uv run story_from_source.py --topic "原来学霸是这样背书的" --source samples/xueba/source.md --out samples/xueba

输出 story.json（标题、梗概、用到的原内容）和 story.txt（标题 + 正文，可直接交给 run.py novel 做分镜）。
"""
import argparse
import json
import sys
from pathlib import Path

from gvgraph import legacy

SYSTEM = """你是短视频编剧，擅长把网络热梗写成 60 秒左右、有反转或笑点的原创小故事。

给你一个热搜话题和它的原始内容（网友帖子、评论）。要求：
- 故事必须建立在原始内容上：至少用上原内容里 3 个具体的点（方法、细节或网友的原话梗），让看过热搜的人一眼认出来
- 原创虚构，不出现任何真实人名、真实品牌名、真实机构名，不照搬网友原话超过一句
- 正文 {chars} 字左右（这决定视频长度，不要超），2~3 个角色，1~2 个场景
- 结构：开头 1 句抓人 → 冲突/铺垫 → 结尾反转或笑点；以对白为主，少量旁白
- 对白用中文引号“”，写清楚是谁说的
- 轻松有趣，不写血腥、暴力、低俗内容，不说教

只输出 JSON：
{{"title":"故事标题（10字内）","logline":"一句话梗概","used_points":["用到的原内容要点"],"story":"故事正文"}}"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--source", required=True, help="原内容整理（md/txt）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--chars", type=int, default=280)
    a = ap.parse_args()
    m = legacy.ensure(legacy.novel_env("story_from_source"))
    ark = m["ark_client"].Ark()
    user = f"热搜话题：{a.topic}\n\n原始内容：\n{Path(a.source).read_text(encoding='utf-8')}"
    res = ark.chat_json(SYSTEM.format(chars=a.chars), user, temperature=0.9)
    for k in ("title", "story"):
        if not res.get(k):
            raise SystemExit(f"豆包返回缺少 {k}: {res}")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"topic": a.topic, "model": m["config"].LLM_MODEL, **res}
    (out / "story.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "story.txt").write_text(f"{res['title']}\n{res['story']}\n", encoding="utf-8")
    print(f"《{res['title']}》{len(res['story'])} 字 -> {out / 'story.txt'}\n")
    print("用到的原内容：" + "；".join(res.get("used_points", [])) + "\n")
    print(res["story"])


if __name__ == "__main__":
    main()
