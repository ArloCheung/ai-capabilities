"""全局配置：从项目根目录的 .env 文件或环境变量读取（环境变量优先）。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # 项目根目录（gvcore 的上一级）


def _load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


def env(key, default=None, cast=str):
    v = os.environ.get(key)
    if v is None or v == "":
        return default
    return cast(v)


# ---------- 火山方舟 ----------
ARK_API_KEY = env("ARK_API_KEY", "")
ARK_BASE_URL = env("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
LLM_MODEL = env("LLM_MODEL", "doubao-seed-1-6-250615")          # 分镜改编用的大模型（也可填推理接入点 ep-xxx）
IMAGE_MODEL = env("IMAGE_MODEL", "doubao-seedream-5-0-260128")  # 定妆图/场景图
VIDEO_MODEL = env("VIDEO_MODEL", "doubao-seedance-2-0-260128")  # 视频；草稿可用 doubao-seedance-2-0-fast-260128

# ---------- 视频参数 ----------
VIDEO_RATIO = env("VIDEO_RATIO", "16:9")
VIDEO_RESOLUTION = env("VIDEO_RESOLUTION", "720p")
VIDEO_MIN_SEC = env("VIDEO_MIN_SEC", 4, int)
VIDEO_MAX_SEC = env("VIDEO_MAX_SEC", 15, int)                   # Seedance 2.0 上限 15 秒（2.5 可到 30）
VIDEO_CONCURRENCY = env("VIDEO_CONCURRENCY", 3, int)
VIDEO_RETRIES = env("VIDEO_RETRIES", 2, int)
# tts   = 对白由 TTS 配音，Seedance 只出环境音（角色音色全片统一）
# native = 对白写进提示词由 Seedance 直接生成口型+人声（口型对得上，但音色可能不统一）
DIALOGUE_MODE = env("DIALOGUE_MODE", "tts")

# ---------- 配音 ----------
TTS_ENGINE = env("TTS_ENGINE", "edge")                          # edge = 免费的 edge-tts；none = 静音占位
NARRATOR_VOICE = env("NARRATOR_VOICE", "zh-CN-YunyangNeural")

# ---------- 合成 ----------
OUT_W = env("OUT_W", 1280, int)
OUT_H = env("OUT_H", 720, int)
OUT_FPS = env("OUT_FPS", 24, int)
AMBIENT_VOLUME = env("AMBIENT_VOLUME", 0.35, float)            # Seedance 原声（环境音）音量
BGM_PATH = env("BGM_PATH", "")                                  # 可选背景音乐文件
BGM_VOLUME = env("BGM_VOLUME", 0.12, float)
SUB_FONT = env("SUB_FONT", "Microsoft YaHei")                   # 字幕字体（Windows 默认微软雅黑）
SUB_FONTSIZE = env("SUB_FONTSIZE", 18, int)
SUB_MAX_CHARS = env("SUB_MAX_CHARS", 18, int)                  # 每行字幕最多字数（竖屏建议 12）
MOCK_FONTFILE = env("MOCK_FONTFILE", "C:/Windows/Fonts/msyh.ttc")  # mock 占位视频上写字用的字体文件

STORYBOARD_HINT = env("STORYBOARD_HINT", "")                  # 追加给分镜大模型的要求（每日短视频会自动设置）
AIGC_LABEL = env("AIGC_LABEL", "")                              # 成片右上角的 AI 生成标识文字，如 “AI生成”；空=不加
LABEL_FONTFILE = env("LABEL_FONTFILE", "C:/Windows/Fonts/msyh.ttc")

# ---------- 每日热点短视频 ----------
DAILY_DIR = Path(env("DAILY_DIR", str(ROOT / "work" / "daily")))
DAILY_STORY_CHARS = env("DAILY_STORY_CHARS", 280, int)        # 故事字数，约等于 60 秒配音
DAILY_MAX_SECONDS = env("DAILY_MAX_SECONDS", 60, int)
DAILY_RATIO = env("DAILY_RATIO", "9:16")                        # 竖屏
DAILY_REVIEW = env("DAILY_REVIEW", "0") == "1"                 # 1 = 生成分镜和定妆图后暂停，人工确认后再出视频
# 热榜里含这些词的条目直接丢弃（可自行增删）
DAILY_BLOCKWORDS = env("DAILY_BLOCKWORDS",
    "去世,逝世,身亡,遇难,死亡,丧生,事故,地震,洪水,火灾,爆炸,坠亡,坠毁,枪击,杀人,命案,案件,判决,判处,被捕,警方,通报,"
    "战争,冲突,导弹,袭击,总统,主席,总理,外交,制裁,选举,政府,疫情,癌,自杀,性侵,猥亵,未成年,儿童,宗教,民族").split(",")

WORK_DIR = Path(env("WORK_DIR", str(ROOT / "work")))

# ---------- 每个步骤的输出目录 ----------
STORYBOARD_DIR = WORK_DIR / "1_storyboard"   # storyboard.json、source_text.txt
ASSETS_DIR = WORK_DIR / "2_assets"           # 角色设定图、场景图及其提示词
VIDEOS_DIR = WORK_DIR / "3_videos"           # 每个镜头的视频、末帧、任务状态、提示词预览
AUDIO_DIR = WORK_DIR / "4_audio"             # 每个镜头的配音 wav 与 manifest.json
FINAL_DIR = WORK_DIR / "5_final"             # final.mp4、subs.srt（_segments 子目录为中间文件）
