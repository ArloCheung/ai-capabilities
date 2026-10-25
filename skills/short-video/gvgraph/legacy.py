"""加载 gvcore 业务模块（分镜、定妆图、视频、配音、合成、热榜、故事）。

gvcore/config.py 在 import 时就从环境变量读取 WORK_DIR、VIDEO_RATIO 等配置，
step2/3/4/5 也在 import 时把目录记成模块常量。所以必须"先设环境变量，再 import"：
ensure(env) 第一次调用时设置 os.environ 并 import 模块，之后同一进程内复用。

一个进程只跑一条 LangGraph 线程（thread_id），env 存在 State 里，
断点续跑时从 checkpoint 取回同一份 env，保证路径一致。
"""
import importlib
import os
import shutil
from pathlib import Path

LG_ROOT = Path(__file__).resolve().parent.parent   # 项目根目录：.env、work/ 都在这里

_loaded_env: dict | None = None
M = {}   # 模块名 -> gvcore 模块，如 M["step3_videos"]

MODULES = ["config", "utils", "ark_client", "step1_storyboard", "step2_assets",
           "step3_videos", "step4_audio", "step5_compose", "trends", "story"]


def ensure(env: dict):
    global _loaded_env
    if _loaded_env is not None:
        if env != _loaded_env:
            raise RuntimeError("同一进程只能处理一条线程：env 与已加载的不一致，请换个进程运行")
        return M
    os.environ.update(env)
    for name in MODULES:
        M[name] = importlib.import_module(f"gvcore.{name}")
    _loaded_env = dict(env)
    return M


def novel_env(name: str = "", portrait: bool = False) -> dict:
    """name：输出子目录（work/novel/<name>），不同故事各用各的目录；portrait：竖屏短视频参数。"""
    env = {"WORK_DIR": str(LG_ROOT / "work" / "novel" / name) if name else str(LG_ROOT / "work" / "novel")}
    if portrait:
        env.update({"VIDEO_RATIO": "9:16", "OUT_W": "720", "OUT_H": "1280",
                    "SUB_FONTSIZE": "11", "SUB_MAX_CHARS": "12", "AIGC_LABEL": "AI生成"})
    return env


def daily_env(date: str) -> dict:
    """每日热点模式的输出目录和竖屏参数。"""
    # 这里要先读一次 .env 才知道 DAILY_RATIO 等设置；只读不 import
    vals = _peek_dotenv()
    ratio = os.environ.get("DAILY_RATIO") or vals.get("DAILY_RATIO") or "9:16"
    max_sec = os.environ.get("DAILY_MAX_SECONDS") or vals.get("DAILY_MAX_SECONDS") or "60"
    portrait = ratio in ("9:16", "3:4")
    w, h = (720, 1280) if portrait else (1280, 720)
    daily_dir = LG_ROOT / "work" / "daily"
    return {
        "DAILY_DIR": str(daily_dir),
        "WORK_DIR": str(daily_dir / date),
        "VIDEO_RATIO": ratio,
        "OUT_W": str(w), "OUT_H": str(h),
        "SUB_FONTSIZE": "11" if portrait else "18",
        "SUB_MAX_CHARS": "12" if portrait else "18",
        "AIGC_LABEL": os.environ.get("AIGC_LABEL") or vals.get("AIGC_LABEL") or "AI生成",
        "STORYBOARD_HINT": (f"这是{ratio}{'竖屏' if portrait else ''}短视频，镜头总时长不超过{max_sec}秒，"
                            "5~8个镜头，人物尽量居中构图，节奏轻快；保留故事里的全部对白"),
    }


def daily_review_default() -> bool:
    v = os.environ.get("DAILY_REVIEW") or _peek_dotenv().get("DAILY_REVIEW") or "0"
    return v == "1"


def _peek_dotenv() -> dict:
    p = LG_ROOT / ".env"
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def need_ffmpeg():
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            raise SystemExit(f"找不到 {exe}，请先安装 FFmpeg（Windows: winget install Gyan.FFmpeg）")
