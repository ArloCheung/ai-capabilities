"""第2步：用 Seedream 为每个角色生成定妆设定图、为每个场景生成概念图。

已存在的图片会跳过（可手动替换成你满意的图，再继续后续步骤）。
"""
import argparse

from . import config
from .utils import load_json, log, storyboard_path

ASSET_DIR = config.ASSETS_DIR


def char_path(cid):
    return ASSET_DIR / f"char_{cid}.jpg"


def scene_path(sid):
    return ASSET_DIR / f"scene_{sid}.jpg"


def char_prompt(sb, c):
    return (f"{sb['style']}。角色设定图，同一人物的正面、侧面、背面全身三视图并排，纯浅灰背景，"
            f"均匀柔光，人物：{c['name']}，{c['appearance']}。画面中不要出现任何文字。")


def scene_prompt(sb, s):
    return f"{sb['style']}。电影场景概念图，空镜无人物，{s['name']}：{s['description']}。画面中不要出现任何文字。"


def mock_image(path, title, sub, size):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", size, (40, 44, 60))
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype(config.MOCK_FONTFILE, 64)
        small = ImageFont.truetype(config.MOCK_FONTFILE, 32)
    except OSError:
        font = small = ImageFont.load_default()
    d.text((60, 60), title, fill=(230, 230, 230), font=font)
    d.text((60, 160), sub[:60], fill=(170, 170, 190), font=small)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "JPEG", quality=90)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="不调用 API，生成占位图")
    ap.add_argument("--force", action="store_true", help="重新生成已存在的图片")
    a = ap.parse_args(argv)
    sb = load_json(storyboard_path())
    ark = None
    if not a.mock:
        from .ark_client import Ark
        ark = Ark()
    from .ark_client import download

    jobs = [(char_path(c["id"]), char_prompt(sb, c), "2560x1440", c["name"]) for c in sb["characters"]]
    scene_size = "1440x2560" if config.VIDEO_RATIO in ("9:16", "3:4") else "2560x1440"
    jobs += [(scene_path(s["id"]), scene_prompt(sb, s), scene_size, s["name"]) for s in sb["scenes"]]
    for path, prompt, size, name in jobs:
        if path.exists() and not a.force:
            log(f"[资产] 跳过已存在 {path.name}")
            continue
        log(f"[资产] 生成 {name} -> {path.name}")
        if a.mock:
            mock_image(path, name, prompt.split("。", 1)[-1], (1280, 720))
        else:
            url = ark.image(prompt, size=size)
            download(url, path)
        path.with_suffix(".prompt.txt").write_text(prompt, encoding="utf-8")
    log(f"[资产] 完成，目录：{ASSET_DIR}")


if __name__ == "__main__":
    main()
