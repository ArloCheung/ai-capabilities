"""小图练手：并行抓抖音、微博热搜，各取前 N 条。

  uv run trends_graph.py            # 默认前 5
  uv run trends_graph.py --top 10

图结构（静态并行扇出 + 汇总）：
  START ─┬─▶ fetch_douyin ─┐
         └─▶ fetch_weibo  ─┴─▶ merge ─▶ END
START 连出两条固定边 = 同一个 super-step 里并行执行；两个节点都往 items 写，
所以 items 需要 reducer（operator.add 拼接列表）。merge 等两边都结束才运行。
抓取和解析复用 gvcore/trends.py，敏感词过滤用 config.DAILY_BLOCKWORDS（只标记，不删除）。
"""
import argparse
import json
import operator
import sys
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from gvgraph import legacy


class TrendState(TypedDict, total=False):
    top: int
    items: Annotated[list, operator.add]     # 两个并行节点的结果拼起来
    errors: Annotated[list, operator.add]
    report: str


def _fetch(source: str):
    def node(state: TrendState) -> dict:
        m = legacy.ensure(legacy.novel_env())
        t = m["trends"]
        url, parser, headers = t.SOURCES[source]
        try:
            got = parser(t._get(url, headers=headers))[: state["top"]]
        except Exception as e:
            return {"errors": [f"{source}：{e.__class__.__name__} {str(e)[:100]}"]}
        return {"items": [{**it, "source": source, "rank": i, "blocked": t.blocked(it["title"] + it["desc"])}
                          for i, it in enumerate(got, 1)]}
    node.__name__ = f"fetch_{source}"
    return node


def merge(state: TrendState) -> dict:
    lines = []
    for src in ("抖音", "微博"):
        lines.append(f"## {src}")
        for it in [x for x in state.get("items", []) if x["source"] == src]:
            hot = f"{it['hot']:,}" if isinstance(it["hot"], int) else it["hot"]
            tag = f" [{it['tag']}]" if it.get("tag") else ""
            flag = "  ⚠ 命中敏感词，选题时会被过滤" if it["blocked"] else ""
            lines.append(f"{it['rank']}. {it['title']}{tag}  热度 {hot}{flag}")
    lines += [f"✗ {e}" for e in state.get("errors", [])]
    return {"report": "\n".join(lines)}


def build():
    g = StateGraph(TrendState)
    g.add_node("fetch_douyin", _fetch("抖音"))
    g.add_node("fetch_weibo", _fetch("微博"))
    g.add_node("merge", merge)
    g.add_edge(START, "fetch_douyin")
    g.add_edge(START, "fetch_weibo")
    g.add_edge(["fetch_douyin", "fetch_weibo"], "merge")   # 等两个都完成
    g.add_edge("merge", END)
    return g.compile()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--json", action="store_true", help="输出原始 items")
    a = ap.parse_args()
    out = build().invoke({"top": a.top})
    print(json.dumps(out["items"], ensure_ascii=False, indent=2) if a.json else out["report"])
