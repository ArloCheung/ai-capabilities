"""节点（Node）：图里的每个方框就是一个普通 Python 函数。

签名约定：def node(state) -> dict | Command
- 读 state，干活，返回"要更新的字段"。不要原地修改 state。
- 业务逻辑全部在 gvcore 包里（通过 legacy.M[...] 取用），这里只做编排和状态读写。
- 节点内部保留 gvcore "文件已存在就跳过"的缓存逻辑：checkpointer 负责"图走到哪一步"，
  文件缓存负责"某个镜头已经花钱生成过"，两者互补。
"""
import json
import os
import shutil
import threading
from pathlib import Path

from langgraph.types import Command, Send, interrupt

from .legacy import ensure
from .state import ChainTask, GenState

VIDEO_ROUNDS = 2   # 视频失败后最多重新派发几轮（每轮内部 step3 还会换 seed 重试 VIDEO_RETRIES 次）


def _day(state: GenState) -> Path:
    m = ensure(state["env"])
    return m["config"].DAILY_DIR / state["date"]


# ---------------------------------------------------------------- 每日模式专用
def fetch_trends(state: GenState) -> dict:
    m = ensure(state["env"])
    f = _day(state) / "0_trends" / "trends.json"
    if not f.exists():
        try:
            m["trends"].main(["--date", state["date"]])
        except SystemExit as e:          # 全部来源失败时 trends 会 SystemExit
            if not state.get("mock"):
                raise RuntimeError(str(e)) from None
            m["utils"].log(f"[热榜] mock 模式忽略：{e}")
            m["utils"].save_json({"items": [], "stats": {}}, f)
    return {"trends_count": len(m["utils"].load_json(f)["items"])}


MOCK_STORY = {"topic": "（mock）打工人周一综合征", "source": "mock", "reason": "离线测试",
              "title": "周一的闹钟", "logline": "闹钟和主人互相较劲的早晨",
              "story": "清晨七点，闹钟第三次响起。小林把它塞进枕头底下。"
                       "“再五分钟。”闹钟却开口了：“你昨天也这么说。”小林愣住，坐了起来。"}


def write_story(state: GenState) -> dict:
    m = ensure(state["env"])
    out = _day(state) / "0_story"
    txt, meta_f = out / "story.txt", out / "story.json"
    if not txt.exists():
        if state.get("mock"):
            meta = {**MOCK_STORY, "date": state["date"]}
            m["utils"].save_json(meta, meta_f)
            txt.write_text(f"{meta['title']}\n{meta['story']}", encoding="utf-8")
        else:
            m["story"].main(["--date", state["date"]])   # 调豆包：选题 + 写故事 + 记 history.json
    meta = m["utils"].load_json(meta_f)
    return {"story": {k: meta.get(k) for k in ("topic", "source", "title", "logline")},
            "story_path": str(txt), "input_path": str(txt), "chars": 0}


# ---------------------------------------------------------------- 公共步骤 1~2
def storyboard(state: GenState) -> dict:
    m = ensure(state["env"])
    cfg, s1, utils = m["config"], m["step1_storyboard"], m["utils"]
    path = utils.storyboard_path()
    if not path.exists():
        paras = s1.read_novel(Path(state["input_path"]), state.get("chars", 0))
        if state.get("storyboard_file"):                       # 对应 run_pipeline.py 的 --storyboard
            sb = s1.normalize(utils.load_json(state["storyboard_file"]))
            utils.save_json(sb, path)
            (cfg.STORYBOARD_DIR / "source_text.txt").write_text("\n".join(paras), encoding="utf-8")
            s1.export_markdown(sb, cfg.STORYBOARD_DIR / "分镜脚本.md")
        elif state.get("mock"):
            raise ValueError("mock 模式不调用大模型，请用 --storyboard 指定分镜 JSON")
        else:
            if state.get("feedback"):   # 人工审核给的修改意见
                cfg.STORYBOARD_HINT = (cfg.STORYBOARD_HINT + "；" if cfg.STORYBOARD_HINT else "") + state["feedback"]
            s1.main(["--input", state["input_path"], "--chars", str(state.get("chars", 0))])
    sb = utils.load_json(path)
    return {"storyboard_path": str(path), "shot_count": len(sb["shots"]),
            "total_seconds": sum(s["duration"] for s in sb["shots"])}


def assets(state: GenState) -> dict:
    m = ensure(state["env"])
    m["step2_assets"].main(["--mock"] if state.get("mock") else [])
    return {"assets": sorted(p.name for p in m["config"].ASSETS_DIR.glob("*.jpg"))}


# ---------------------------------------------------------------- 人工审核（interrupt）
def human_review(state: GenState) -> Command:
    """interrupt() 会把整张图挂起，checkpoint 落盘，进程可以直接退出。
    之后用 Command(resume=...) 继续时，本节点会【从头重新执行】，这一次 interrupt()
    直接返回 resume 的值。所以 interrupt 之前不要放有副作用的代码。

    返回 Command(goto=...) 是另一种路由方式：节点自己决定下一步去哪，
    同时还能顺带更新 state（update=...）。"""
    m = ensure(state["env"])
    cfg = m["config"]
    decision = interrupt({
        "question": "请检查分镜和定妆图，决定下一步",
        "storyboard_md": str(cfg.STORYBOARD_DIR / "分镜脚本.md"),
        "assets_dir": str(cfg.ASSETS_DIR),
        "shots": state.get("shot_count"), "seconds": state.get("total_seconds"),
        "options": ["approve", "redo_storyboard"] + (["redo_story"] if state["mode"] == "daily" else []),
    })
    action = (decision or {}).get("action", "approve")
    feedback = (decision or {}).get("feedback", "")
    if action == "approve":
        return Command(goto="plan_videos")
    dirs = [cfg.STORYBOARD_DIR, cfg.ASSETS_DIR]
    if action == "redo_story":
        dirs.append(_day(state) / "0_story")
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)
    m["utils"].log(f"[审核] {action}，意见：{feedback or '无'}")
    return Command(update={"feedback": feedback},
                   goto="write_story" if action == "redo_story" else "storyboard")


# ---------------------------------------------------------------- 步骤 3：Send 扇出 / 汇总
def plan_videos(state: GenState) -> dict:
    m = ensure(state["env"])
    m["config"].VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    return {"video_round": state.get("video_round", 0) + 1, "failed_chains": None}


def dispatch_videos(state: GenState):
    """条件边函数：返回 Send 列表 = 动态扇出（map）。
    每条"镜头链"（互相接续末帧的镜头必须串行）变成一个并行的 render_chain 任务。
    并发数由 invoke 时的 config["max_concurrency"] 限制。"""
    m = ensure(state["env"])
    s3 = m["step3_videos"]
    sb = m["utils"].load_json(state["storyboard_path"])
    todo = [c for c in s3.build_chains(sb["shots"])
            if not all(s3.video_path(s["id"]).exists() for s in c)]
    if not todo:
        return "collect_videos"
    m["utils"].log(f"[视频] 第 {state.get('video_round')} 轮派发 {len(todo)} 条链")
    return [Send("render_chain", ChainTask(env=state["env"], mock=state.get("mock", False),
                                           chain_ids=[s["id"] for s in c])) for c in todo]


_task_log, _task_log_lock = None, threading.Lock()


def _video_task_log(m):
    """step3 用一个共享 dict 记录提交过的任务（state.json），并行分支共用同一个。"""
    global _task_log
    with _task_log_lock:
        if _task_log is None:
            f = m["config"].VIDEOS_DIR / "state.json"
            _task_log = m["utils"].load_json(f) if f.exists() else {}
    return _task_log


_injected = set()


def _maybe_inject_failure(ids):
    """故障注入（学习用）：GV_FAIL_SHOTS=s005,s009 让这些镜头所在的链在本进程第一次执行时失败，
    用来观察 collect_videos -> plan_videos 的重试环。"""
    want = {x.strip() for x in os.environ.get("GV_FAIL_SHOTS", "").split(",") if x.strip()}
    hit = (want & set(ids)) - _injected
    if hit:
        _injected.update(hit)
        raise RuntimeError(f"注入的故障 {sorted(hit)}")


def render_chain(task: ChainTask) -> dict:
    """被 Send 调用的节点：输入是 ChainTask（私有小 state），输出仍写回 GenState。
    捕获异常、把失败写进 failed_chains，这样一条链失败不会让其他并行分支白跑。"""
    m = ensure(task["env"])
    s3 = m["step3_videos"]
    sb = m["utils"].load_json(m["utils"].storyboard_path())
    chain = [s for s in sb["shots"] if s["id"] in task["chain_ids"]]
    ark = None
    try:
        _maybe_inject_failure(task["chain_ids"])
        if not task["mock"]:
            ark = m["ark_client"].Ark()
        s3.run_chain(ark, sb, chain, _video_task_log(m), False, task["mock"])
    except Exception as e:
        m["utils"].log(f"[视频] 链 {task['chain_ids']} 失败：{e}")
        return {"failed_chains": [{"ids": task["chain_ids"], "error": str(e)[:300]}]}
    return {"videos": {sid: str(s3.video_path(sid)) for sid in task["chain_ids"]}}


def collect_videos(state: GenState) -> dict:
    """汇总（reduce）：所有 render_chain 跑完、reducer 合并好之后才会执行。"""
    m = ensure(state["env"])
    failed = state.get("failed_chains") or []
    m["utils"].log(f"[视频] 第 {state.get('video_round')} 轮结束：成功 {len(state.get('videos') or {})} 个镜头，"
                   f"失败 {len(failed)} 条链")
    if failed and state.get("video_round", 0) >= VIDEO_ROUNDS:
        return {"error": "视频生成失败：" + json.dumps(failed, ensure_ascii=False)[:800]}
    return {}


# ---------------------------------------------------------------- 步骤 4~5 与发布
def audio(state: GenState) -> dict:
    m = ensure(state["env"])
    m["step4_audio"].main([])
    n = sum(len(m["utils"].load_json(f)["lines"]) for f in m["config"].AUDIO_DIR.glob("*/manifest.json"))
    return {"audio_lines": n}


def compose(state: GenState) -> dict:
    m = ensure(state["env"])
    m["step5_compose"].main([])
    return {"final_path": str(m["config"].FINAL_DIR / "final.mp4")}


def publish(state: GenState) -> dict:
    """每日模式：成片复制到 outbox，等待人工发布（见 references/douyin-publish.md）。"""
    import re
    m = ensure(state["env"])
    title = re.sub(r'[\\/:*?"<>|\s]', "", (state.get("story") or {}).get("title", "untitled"))[:20]
    outbox = m["config"].DAILY_DIR / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    dst = outbox / f"{state['date']}_{title}.mp4"
    shutil.copy(state["final_path"], dst)
    return {"outbox_path": str(dst)}


# ---------------------------------------------------------------- 路由函数（条件边）
def route_start(state: GenState) -> str:
    return "fetch_trends" if state["mode"] == "daily" else "storyboard"


def route_after_assets(state: GenState) -> str:
    return "human_review" if state.get("review") else "plan_videos"


def route_after_collect(state: GenState) -> str:
    if state.get("error"):
        return "__end__"
    if state.get("failed_chains"):
        return "plan_videos"          # 形成环：失败的链再派发一轮
    return "audio"


def route_after_compose(state: GenState) -> str:
    return "publish" if state["mode"] == "daily" else "__end__"
