"""抓取各平台热榜（微博 / 百度 / 抖音 / 知乎），合并去重并过滤敏感词。

这些都是网页公开使用的非官方接口，平台随时可能改版或要求登录；
某个源失败只会跳过，不影响其他源。

用法：python trends.py            # 输出到 daily/<今天>/0_trends/
"""
import argparse
import datetime as dt
import re

import requests

from . import config
from .utils import log, save_json

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*"}


def _get(url, **kw):
    r = requests.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=15, **kw)
    r.raise_for_status()
    return r.json()


def parse_weibo(d):
    out = []
    for it in d.get("data", {}).get("realtime", []):
        if it.get("is_ad") or not it.get("word"):
            continue
        out.append({"title": it["word"], "desc": it.get("note", ""), "hot": it.get("num", 0),
                    "tag": it.get("label_name", "") or it.get("category", "")})
    return out


def parse_baidu(d):
    out = []
    for card in d.get("data", {}).get("cards", []):
        for it in card.get("content", []):
            if "word" in it:
                out.append({"title": it["word"], "desc": it.get("desc", ""),
                            "hot": int(it.get("hotScore", 0) or 0), "tag": it.get("labelTagName", "")})
    return out


def parse_douyin(d):
    return [{"title": it["word"], "desc": "", "hot": it.get("hot_value", 0), "tag": ""}
            for it in d.get("word_list", []) if it.get("word")]


def parse_zhihu(d):
    out = []
    for it in d.get("data", []):
        t = it.get("target", {})
        title = t.get("title") or t.get("title_area", {}).get("text")
        if not title:
            continue
        m = re.search(r"([\d.]+)\s*万", it.get("detail_text", ""))
        out.append({"title": title, "desc": (t.get("excerpt") or "")[:120],
                    "hot": int(float(m.group(1)) * 10000) if m else 0, "tag": ""})
    return out


SOURCES = {
    "微博": ("https://weibo.com/ajax/side/hotSearch", parse_weibo, {"Referer": "https://weibo.com/"}),
    "百度": ("https://top.baidu.com/api/board?platform=pc&tab=realtime", parse_baidu, {}),
    "抖音": ("https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/", parse_douyin, {}),
    "知乎": ("https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50", parse_zhihu, {}),
}


def blocked(text):
    return any(w and w in text for w in config.DAILY_BLOCKWORDS)


def fetch_all(limit_per_source=30):
    items, seen, stats = [], set(), {}
    for name, (url, parser, headers) in SOURCES.items():
        try:
            got = parser(_get(url, headers=headers))[:limit_per_source]
        except Exception as e:
            stats[name] = f"失败：{e.__class__.__name__} {str(e)[:80]}"
            continue
        kept = 0
        for rank, it in enumerate(got, 1):
            key = re.sub(r"\W", "", it["title"])[:12]
            if key in seen or blocked(it["title"] + it["desc"]):
                continue
            seen.add(key)
            items.append({**it, "source": name, "rank": rank})
            kept += 1
        stats[name] = f"{len(got)} 条，保留 {kept}"
    return items, stats


def save_trends(items, stats, out_dir):
    save_json({"time": dt.datetime.now().isoformat(timespec="seconds"), "stats": stats, "items": items},
              out_dir / "trends.json")
    lines = [f"# 热榜 {dt.date.today()}", ""] + [f"- {k}：{v}" for k, v in stats.items()] + [""]
    lines += [f"{i}. [{x['source']}#{x['rank']}] {x['title']}" + (f" —— {x['desc']}" if x["desc"] else "")
              for i, x in enumerate(items, 1)]
    (out_dir / "trends.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(dt.date.today()))
    a = ap.parse_args(argv)
    out = config.DAILY_DIR / a.date / "0_trends"
    items, stats = fetch_all()
    for k, v in stats.items():
        log(f"[热榜] {k}：{v}")
    if not items:
        raise SystemExit("[热榜] 所有来源都失败了，检查网络或接口是否改版")
    save_trends(items, stats, out)
    log(f"[热榜] 共 {len(items)} 条 -> {out}")


if __name__ == "__main__":
    main()
