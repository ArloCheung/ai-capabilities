"""genvideo 的 LangGraph 版命令行。

  # 小说流水线（离线 mock，不花钱）
  uv run run.py novel --input samples/crab/story.txt --storyboard samples/crab/storyboard.json --mock --portrait --workdir crab
  # 加 --review：分镜+定妆图后暂停，等你审核
  uv run run.py review --thread novel-story --approve
  uv run run.py review --thread novel-story --redo storyboard --feedback "镜头再少一点"
  # 每日热点短视频
  uv run run.py daily [--date 2026-10-18]
  # 中途失败/被 --stop-before 停下：原地续跑
  uv run run.py resume --thread daily-2026-10-18
  # 查看线程状态 / 每一步的快照历史 / 导出图结构
  uv run run.py status --thread ...
  uv run run.py history --thread ...
  uv run run.py graph
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from langgraph.types import Command

from gvgraph import legacy
from gvgraph.graph import compile_graph

DB = legacy.LG_ROOT / "work" / "checkpoints.sqlite"


def _summ(v):
    s = json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= 160 else s[:157] + "..."


def stream(graph, inp, cfg, **kw):
    """stream_mode="updates"：每个节点跑完就吐出它返回的那部分 state 更新。"""
    for chunk in graph.stream(inp, cfg, stream_mode="updates", **kw):
        for node, upd in chunk.items():
            if node == "__interrupt__":
                for it in upd:
                    print(f"\n⏸  图已暂停，等待人工审核：\n{json.dumps(it.value, ensure_ascii=False, indent=2)}")
                    print(f"\n继续：uv run run.py review --thread {cfg['configurable']['thread_id']} --approve"
                          f"\n重做：uv run run.py review --thread {cfg['configurable']['thread_id']} "
                          f"--redo storyboard --feedback \"...\"")
            else:
                keys = {k: v for k, v in (upd or {}).items() if k != "env"}
                print(f"✓ {node:<15} {_summ(keys)}", flush=True)
    snap = graph.get_state(cfg)
    if snap.next and not snap.interrupts:
        print(f"\n⏹  停在 {snap.next} 之前；继续：uv run run.py resume --thread {cfg['configurable']['thread_id']}")
    elif not snap.next:
        v = snap.values
        if v.get("error"):
            print(f"\n✗ {v['error']}")
            sys.exit(1)
        print(f"\n完成：{v.get('final_path')}" + (f"\n成片副本：{v['outbox_path']}" if v.get("outbox_path") else ""))


def run_config(thread, env):
    m = legacy.ensure(env)
    return {"configurable": {"thread_id": thread},
            "max_concurrency": m["config"].VIDEO_CONCURRENCY,   # 并行 render_chain 的上限
            "recursion_limit": 100}


def start(graph, thread, inp, fresh, stop_before):
    cfg0 = {"configurable": {"thread_id": thread}}
    snap = graph.get_state(cfg0)
    if snap.values:
        if fresh:
            graph.checkpointer.delete_thread(thread)
            print(f"[线程] 已清除 {thread} 的旧快照（磁盘上已生成的文件仍会复用）")
        elif snap.next:
            raise SystemExit(f"线程 {thread} 还没跑完（停在 {snap.next}），请用 resume / review 继续，或加 --fresh 重来")
        else:
            raise SystemExit(f"线程 {thread} 已完成。要重跑请加 --fresh，或换 --thread")
    stream(graph, inp, run_config(thread, inp["env"]), interrupt_before=stop_before or None)


def existing(graph, thread):
    snap = graph.get_state({"configurable": {"thread_id": thread}})
    if not snap.values:
        raise SystemExit(f"没有线程 {thread}")
    return snap


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="genvideo LangGraph 版")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--mock", action="store_true", help="离线模式：不调用火山方舟")
        p.add_argument("--storyboard", help="直接用已有分镜 JSON")
        p.add_argument("--thread", help="线程 id（默认按输入自动生成）")
        p.add_argument("--fresh", action="store_true", help="清掉该线程的旧快照重新开始")
        p.add_argument("--stop-before", nargs="*", metavar="NODE", help="在这些节点前停下，如 plan_videos")

    p = sub.add_parser("novel"); common(p)
    p.add_argument("--input", required=True)
    p.add_argument("--chars", type=int, default=0)
    p.add_argument("--review", action="store_true", help="分镜+定妆图后暂停审核")
    p.add_argument("--workdir", default="", help="输出到 work/novel/<名字>，多个故事互不覆盖")
    p.add_argument("--portrait", action="store_true", help="竖屏 9:16 短视频")

    p = sub.add_parser("daily"); common(p)
    p.add_argument("--date", default=str(dt.date.today()))
    p.add_argument("--review", choices=["on", "off"], help="默认跟随 .env 的 DAILY_REVIEW")

    for name in ("resume", "status", "history"):
        sub.add_parser(name).add_argument("--thread", required=True)
    p = sub.add_parser("review")
    p.add_argument("--thread", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", action="store_true")
    g.add_argument("--redo", choices=["storyboard", "story"])
    p.add_argument("--feedback", default="")
    sub.add_parser("graph")
    a = ap.parse_args()

    graph = compile_graph(DB)
    if a.cmd in ("novel", "daily", "resume", "review"):
        legacy.need_ffmpeg()

    if a.cmd == "graph":
        mmd = graph.get_graph().draw_mermaid()
        out = legacy.LG_ROOT / "docs" / "graph.mmd"
        out.parent.mkdir(exist_ok=True)
        out.write_text(mmd, encoding="utf-8")
        print(mmd + f"\n-> {out}")
        return

    sb = str(Path(a.storyboard).resolve()) if getattr(a, "storyboard", None) else None
    if a.cmd == "novel":
        inp = {"mode": "novel", "mock": a.mock, "review": a.review, "env": legacy.novel_env(a.workdir, a.portrait),
               "input_path": str(Path(a.input).resolve()), "chars": a.chars, "storyboard_file": sb}
        start(graph, a.thread or f"novel-{Path(a.input).stem}", inp, a.fresh, a.stop_before)
    elif a.cmd == "daily":
        review = legacy.daily_review_default() if a.review is None else a.review == "on"
        inp = {"mode": "daily", "mock": a.mock, "review": review, "env": legacy.daily_env(a.date),
               "date": a.date, "storyboard_file": sb}
        start(graph, a.thread or f"daily-{a.date}", inp, a.fresh, a.stop_before)
    elif a.cmd == "resume":
        snap = existing(graph, a.thread)
        if snap.interrupts:
            raise SystemExit("该线程在等人工审核，请用 review 命令")
        stream(graph, None, run_config(a.thread, snap.values["env"]))   # 输入 None = 从最后一个快照继续
    elif a.cmd == "review":
        snap = existing(graph, a.thread)
        if not snap.interrupts:
            raise SystemExit(f"线程 {a.thread} 没有在等审核（下一步：{snap.next}）")
        decision = {"action": "approve"} if a.approve else {"action": f"redo_{a.redo}", "feedback": a.feedback}
        stream(graph, Command(resume=decision), run_config(a.thread, snap.values["env"]))
    elif a.cmd == "status":
        snap = existing(graph, a.thread)
        print(f"下一步：{snap.next or '（已结束）'}")
        for it in snap.interrupts:
            print("等待审核：", _summ(it.value))
        print(json.dumps({k: v for k, v in snap.values.items() if k != "env"}, ensure_ascii=False, indent=2))
    elif a.cmd == "history":
        # 每个 super-step 一个快照，最新的在前；checkpoint_id 可用于 time travel（从某个快照分叉重跑）
        for s in graph.get_state_history({"configurable": {"thread_id": a.thread}}):
            print(f"step={s.metadata.get('step'):>3}  next={s.next!s:<35} "
                  f"checkpoint_id={s.config['configurable']['checkpoint_id']}")


if __name__ == "__main__":
    main()
