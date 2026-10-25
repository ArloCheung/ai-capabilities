"""第3步：逐镜头调用 Seedance 2.0 生成视频。

- 普通镜头：多模态参考模式，传入出场角色设定图 + 场景图（最多 9 张）。
- continue_from_prev 镜头：用上一镜头的末帧作为首帧（first_frame），动作无缝衔接。
- 互相接续的镜头组成一条“链”顺序生成；不同链并发生成（VIDEO_CONCURRENCY）。
- 支持断点续跑：已下载的镜头自动跳过；失败会换 seed 重试。

用法：
  python step3_videos.py            # 全部镜头
  python step3_videos.py --only s003 s007 --force   # 重跑指定镜头
"""
import argparse
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config
from .step2_assets import char_path, scene_path
from .utils import extract_last_frame, load_json, log, run, save_json, storyboard_path

VIDEO_DIR = config.VIDEOS_DIR
_state_lock = threading.Lock()


def video_path(sid):
    return VIDEO_DIR / f"{sid}.mp4"


def last_frame_path(sid):
    return VIDEO_DIR / f"{sid}_last.jpg"


def build_chains(shots):
    chains = []
    for s in shots:
        if s.get("continue_from_prev") and chains:
            chains[-1].append(s)
        else:
            chains.append([s])
    return chains


def build_prompt(sb, shot, ref_desc):
    names = {c["id"]: c for c in sb["characters"]}
    scenes = {s["id"]: s for s in sb["scenes"]}
    parts = [sb.get("style", "")]
    if ref_desc:
        parts.append("参考图说明：" + "；".join(ref_desc) + "。人物外貌、服装须与参考图保持一致")
    if shot.get("scene") in scenes:
        parts.append(f"场景：{scenes[shot['scene']]['name']}")
    for cid in shot["characters"]:
        c = names[cid]
        parts.append(f"{c['name']}：{c['appearance']}")
    parts.append(f"{shot.get('shot_type', '')}，{shot.get('camera', '')}")
    parts.append(shot["visual_prompt"])
    if config.DIALOGUE_MODE == "native" and shot["dialogue"]:
        lines = [f"{names[d['speaker']]['name'] if d['speaker'] in names else d['speaker']}说：“{d['text']}”"
                 for d in shot["dialogue"]]
        parts.append("对白（普通话）：" + " ".join(lines))
    else:
        parts.append("只生成环境音和动作音效，人物不说话，不要人声对白，不要背景音乐，不要字幕")
    return "。".join(p for p in parts if p)


def build_content(sb, shot, prev_last_frame):
    from .ark_client import image_data_uri
    content = []
    ref_desc = []
    if shot.get("continue_from_prev") and prev_last_frame and prev_last_frame.exists():
        # 首帧接续模式：只给首帧 + 文本
        content.append({"type": "image_url", "image_url": {"url": image_data_uri(prev_last_frame)},
                        "role": "first_frame"})
        mode = "首帧接续"
    else:
        names = {c["id"]: c["name"] for c in sb["characters"]}
        refs = [(char_path(cid), f"角色「{names[cid]}」的设定图") for cid in shot["characters"]]
        if shot.get("scene"):
            sname = next(s["name"] for s in sb["scenes"] if s["id"] == shot["scene"])
            refs.append((scene_path(shot["scene"]), f"场景「{sname}」的环境参考"))
        refs = [r for r in refs if r[0].exists()][:9]
        for i, (p, desc) in enumerate(refs, 1):
            content.append({"type": "image_url", "image_url": {"url": image_data_uri(p)},
                            "role": "reference_image"})
            ref_desc.append(f"图{i}是{desc}")
        mode = f"参考图×{len(refs)}"
    content.insert(0, {"type": "text", "text": build_prompt(sb, shot, ref_desc)})
    return content, mode


def mock_video(shot, out):
    """离线占位视频：彩色背景 + 镜头编号与画面描述。"""
    colors = ["0x2b3a55", "0x553b2b", "0x2b5540", "0x4a2b55", "0x55502b"]
    color = colors[hash(shot.get("scene") or "") % len(colors)]
    desc = shot["visual_prompt"]
    lines = [f"{shot['id']}  {shot.get('shot_type', '')}  {shot['duration']}s  [MOCK]"]
    n = 30 if config.OUT_W >= config.OUT_H else 16
    lines += [desc[i:i + n] for i in range(0, min(len(desc), 120), n)]
    txt = out.with_suffix(".mock.txt")
    txt.write_text("\n".join(lines), encoding="utf-8")
    font = config.MOCK_FONTFILE.replace("\\", "/").replace(":", r"\:")
    vf = (f"drawtext=fontfile='{font}':textfile='{txt.name}':fontcolor=white:fontsize=30:"
          f"line_spacing=14:x=60:y=60")
    d = shot["duration"]
    # cwd=视频目录，textfile 用相对路径，避开 Windows 盘符冒号的转义问题
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={config.OUT_W}x{config.OUT_H}:r=24:d={d}",
         "-f", "lavfi", "-i", f"anoisesrc=d={d}:c=brown:a=0.02",
         "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out.name],
        cwd=out.parent)
    txt.unlink(missing_ok=True)


def gen_shot(ark, sb, shot, prev_last, state, mock):
    sid = shot["id"]
    out = video_path(sid)
    if mock:
        mock_video(shot, out)
        return "mock"
    from .ark_client import ArkError, download
    content, mode = build_content(sb, shot, prev_last)
    last_err = None
    for attempt in range(config.VIDEO_RETRIES + 1):
        seed = random.randint(1, 2**31 - 1)
        try:
            tid = ark.video_create(content, shot["duration"],
                                   generate_audio=True, seed=seed)
            with _state_lock:
                state[sid] = {"task_id": tid, "seed": seed, "mode": mode, "prompt": content[0]["text"]}
                save_json(state, VIDEO_DIR / "state.json")
            log(f"[视频] {sid} 已提交 ({mode}, {shot['duration']}s) task={tid}")
            url = ark.video_wait(tid)
            download(url, out)
            return mode
        except ArkError as e:
            last_err = e
            log(f"[视频] {sid} 第 {attempt + 1} 次失败：{e}")
    raise last_err


def run_chain(ark, sb, chain, state, force, mock):
    prev_last = None
    for shot in chain:
        sid = shot["id"]
        out = video_path(sid)
        if out.exists() and not force:
            log(f"[视频] {sid} 已存在，跳过")
        else:
            mode = gen_shot(ark, sb, shot, prev_last, state, mock)
            log(f"[视频] {sid} 完成 ({mode})")
        prev_last = extract_last_frame(out, last_frame_path(sid))
    return [s["id"] for s in chain]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="不调用 API，生成占位视频")
    ap.add_argument("--only", nargs="*", help="只生成这些镜头 id")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="只输出每个镜头的提示词和参考图，不调用 API")
    a = ap.parse_args(argv)
    sb = load_json(storyboard_path())
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    if a.dry_run:
        out = VIDEO_DIR / "prompts_preview.txt"
        blocks = []
        for s in sb["shots"]:
            fake_prev = last_frame_path("__prev__") if s.get("continue_from_prev") else None
            if fake_prev:
                blocks.append(f"## {s['id']} ({s['duration']}s, 首帧接续上一镜头末帧)\n{build_prompt(sb, s, [])}")
                continue
            content, mode = build_content(sb, s, None)
            blocks.append(f"## {s['id']} ({s['duration']}s, {mode})\n{content[0]['text']}")
        out.write_text("\n\n".join(blocks), encoding="utf-8")
        log(f"[视频] 提示词预览 -> {out}")
        return
    state_file = VIDEO_DIR / "state.json"
    state = load_json(state_file) if state_file.exists() else {}
    ark = None
    if not a.mock:
        from .ark_client import Ark
        ark = Ark()

    chains = build_chains(sb["shots"])
    if a.only:
        chains = [c for c in chains if any(s["id"] in a.only for s in c)]
    log(f"[视频] {sum(map(len, chains))} 个镜头，{len(chains)} 条链，并发 {config.VIDEO_CONCURRENCY}")
    errors = []
    with ThreadPoolExecutor(max_workers=config.VIDEO_CONCURRENCY) as pool:
        futs = {pool.submit(run_chain, ark, sb, c, state, a.force, a.mock): c for c in chains}
        for f in as_completed(futs):
            try:
                f.result()
            except Exception as e:  # 一条链失败不影响其他链
                ids = [s["id"] for s in futs[f]]
                errors.append(ids)
                log(f"[视频] 链 {ids} 失败：{e}")
    if errors:
        raise SystemExit(f"[视频] 有 {len(errors)} 条链失败，修正后重跑本步骤即可续跑：{errors}")
    log(f"[视频] 全部完成 -> {VIDEO_DIR}")


if __name__ == "__main__":
    main()
