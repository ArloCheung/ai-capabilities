"""把节点和边组装成图（StateGraph）并编译。

  START ─┬─(daily)─▶ fetch_trends ─▶ write_story ─┐
         └─(novel)────────────────────────────────┴─▶ storyboard ─▶ assets ─┬─(review)─▶ human_review ──┐
                                                       ▲   ▲                 │                ⟲ 重做分镜/故事 │
                                                       └───┴─────────────────┼────────────────────────────┘
                                                                             ▼ (approve / 无需审核)
            ┌──────────────── 有失败且未超轮数 ◀──────────┐                plan_videos
            ▼                                              │                    │ Send × N（动态扇出）
        plan_videos ─▶ render_chain ×N（并行）─▶ collect_videos ─▶ audio ─▶ compose ─┬─(daily)─▶ publish ─▶ END
                                                                                      └─(novel)─▶ END

三种"边"：
- add_edge(a, b)                    固定边：a 完成后一定走 b
- add_conditional_edges(a, fn, ...) 条件边：fn(state) 返回下一个节点名，或 Send 列表（扇出）
- 节点返回 Command(goto=...)        节点内部决定去向（human_review 用这个）
"""
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from . import nodes as n
from .state import GenState


def _retryable(e: Exception) -> bool:
    # 火山方舟接口错误 / 网络错误才整节点重试；参数错误（ValueError 等）重试也没用
    return type(e).__name__ == "ArkError" or isinstance(e, OSError)


LLM_RETRY = RetryPolicy(max_attempts=3, initial_interval=5.0, backoff_factor=2.0, retry_on=_retryable)


def build_graph() -> StateGraph:
    g = StateGraph(GenState)

    g.add_node("fetch_trends", n.fetch_trends)
    g.add_node("write_story", n.write_story, retry_policy=LLM_RETRY)
    g.add_node("storyboard", n.storyboard, retry_policy=LLM_RETRY)
    g.add_node("assets", n.assets, retry_policy=LLM_RETRY)
    # destinations 只用于画图：告诉 LangGraph 这个节点的 Command(goto) 可能去哪
    g.add_node("human_review", n.human_review, destinations=("plan_videos", "storyboard", "write_story"))
    g.add_node("plan_videos", n.plan_videos)
    g.add_node("render_chain", n.render_chain)
    g.add_node("collect_videos", n.collect_videos)
    g.add_node("audio", n.audio)
    g.add_node("compose", n.compose)
    g.add_node("publish", n.publish)

    g.add_conditional_edges(START, n.route_start, ["fetch_trends", "storyboard"])
    g.add_edge("fetch_trends", "write_story")
    g.add_edge("write_story", "storyboard")
    g.add_edge("storyboard", "assets")
    g.add_conditional_edges("assets", n.route_after_assets, ["human_review", "plan_videos"])
    g.add_conditional_edges("plan_videos", n.dispatch_videos, ["render_chain", "collect_videos"])
    g.add_edge("render_chain", "collect_videos")
    g.add_conditional_edges("collect_videos", n.route_after_collect, ["plan_videos", "audio", END])
    g.add_edge("audio", "compose")
    g.add_conditional_edges("compose", n.route_after_compose, ["publish", END])
    g.add_edge("publish", END)
    return g


def open_checkpointer(db_path: Path) -> SqliteSaver:
    """checkpointer：每个 super-step 结束都把 State 存一份快照，按 thread_id 区分不同的运行。
    有了它才能 interrupt 暂停、进程崩了续跑、回看历史（time travel）。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)


def compile_graph(db_path: Path):
    return build_graph().compile(checkpointer=open_checkpointer(db_path))
