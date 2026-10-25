import json
import shutil
import subprocess
from pathlib import Path

from . import config


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save_json(obj, p):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def storyboard_path():
    return config.STORYBOARD_DIR / "storyboard.json"


def need_ffmpeg():
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            raise SystemExit(f"找不到 {exe}，请先安装 FFmpeg 并加入 PATH（Windows: winget install Gyan.FFmpeg）")


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("命令失败:\n" + " ".join(map(str, cmd)) + "\n" + r.stderr[-2000:])
    return r.stdout


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


def has_audio(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
               "stream=index", "-of", "csv=p=0", str(path)])
    return bool(out.strip())


def extract_last_frame(video, out_jpg):
    run(["ffmpeg", "-y", "-sseof", "-0.15", "-i", str(video), "-frames:v", "1",
         "-q:v", "2", "-update", "1", str(out_jpg)])
    return out_jpg


def log(*a):
    print(*a, flush=True)
