#!/usr/bin/env python3
"""short-video 流水线的离线回归测试。

用 samples/crab 的故事和分镜，以 --mock 模式跑完整张图（不调用火山方舟，不花钱）：
占位画面 + 真实 edge-tts 配音 + 字幕 + 拼接。检查成片存在、时长合理、带音轨。
需要 FFmpeg 和网络（edge-tts 在线合成语音）。

运行:
    uv run --project skills/short-video python evals/short-video/run_evals.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "skills" / "short-video"
THREAD = "eval-crab"
WORK = ROOT / "work" / "novel" / THREAD


def probe(path, args):
    return subprocess.run(["ffprobe", "-v", "error", *args, str(path)],
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    shutil.rmtree(WORK, ignore_errors=True)
    cmd = [sys.executable, "run.py", "novel", "--mock", "--portrait", "--fresh",
           "--input", "samples/crab/story.txt", "--storyboard", "samples/crab/storyboard.json",
           "--workdir", THREAD, "--thread", THREAD]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout[-2000:])
    failures = []
    if r.returncode != 0:
        failures.append(f"run.py 退出码 {r.returncode}: {r.stderr[-1500:]}")

    sb = json.loads((WORK / "1_storyboard" / "storyboard.json").read_text(encoding="utf-8"))   # 已编号、已校正时长
    final = WORK / "5_final" / "final.mp4"
    if not final.exists():
        failures.append(f"没有生成成片 {final}")
    else:
        dur = float(probe(final, ["-show_entries", "format=duration", "-of", "default=nw=1:nk=1"]) or 0)
        expect = sum(s["duration"] for s in sb["shots"])
        if dur < expect * 0.8:
            failures.append(f"成片时长 {dur:.1f}s，少于分镜总时长 {expect}s 的 80%")
        if not probe(final, ["-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0"]):
            failures.append("成片没有音轨")
        size = probe(final, ["-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0"])
        if size != "720,1280":
            failures.append(f"竖屏尺寸应为 720x1280，实际 {size}")
    for sid in (s["id"] for s in sb["shots"]):
        if not (WORK / "3_videos" / f"{sid}.mp4").exists():
            failures.append(f"缺少镜头 {sid}")

    if failures:
        print("FAIL\n- " + "\n- ".join(failures))
        sys.exit(1)
    print(f"PASS：{len(sb['shots'])} 个镜头，成片 {final.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
