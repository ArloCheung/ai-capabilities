"""第1步：小说原文 -> 结构化分镜 storyboard.json

用法：
  python step1_storyboard.py --input 小说.txt --chars 500
长篇会按 --chunk 字数分段，逐段改编；已出现的角色/场景表会带入下一段，保证前后一致。
"""
import argparse
import json
from pathlib import Path

from . import config
from .utils import log, save_json, storyboard_path

VOICES = {
    "zh-CN-YunjianNeural": "成熟男声，低沉有力（中年男性）",
    "zh-CN-YunxiNeural": "青年男声，阳光自然",
    "zh-CN-YunyangNeural": "男播音腔，沉稳（适合旁白）",
    "zh-CN-YunxiaNeural": "少年男声",
    "zh-CN-XiaoxiaoNeural": "青年女声，温暖",
    "zh-CN-XiaoyiNeural": "少女声，活泼",
}

SYSTEM = f"""你是资深影视分镜师，负责把中文小说改编成可直接用于 AI 视频模型（Seedance 2.0）的分镜脚本。

规则：
1. 忠实原文情节与对白，不添加原文没有的剧情；对白可略微口语化精简，但保留原意。
2. 每个镜头 4~15 秒。按台词估算时长：中文配音约每秒 4.5 字，镜头时长 ≥ (旁白+对白字数)/4.5 + 1，最多 15 秒；台词太长就拆成多个镜头。
3. 镜头语言要有变化（远景/中景/近景/特写/过肩/反打），每个镜头只描述一个连贯动作。
4. visual_prompt 只描述画面：人物外观动作表情、环境、光线、镜头运动。不要写人物名字以外的抽象心理活动，不要写台词。
5. 如果某镜头与上一镜头机位相同、动作直接延续，continue_from_prev 设为 true（会用上一镜头末帧作为首帧），否则 false。
6. 角色 appearance 要具体稳定（年龄、发型、脸型、服装颜色款式、体型），后续所有镜头都靠它保持一致。
7. 为每个角色从下列音色中选一个 voice（可用 pitch 如 "-8Hz" 区分相同音色的角色）：
{json.dumps(VOICES, ensure_ascii=False, indent=1)}
8. 旁白（narration）只保留推动剧情必要的叙述，没有就留空字符串。
9. 只输出 JSON，不要任何解释。

输出 JSON 格式：
{{
  "style": "全片统一画风描述（只在第一段需要给出；已有则原样返回）",
  "characters": [{{"id":"英文小写id","name":"名字","appearance":"外观","voice":"音色","pitch":"+0Hz"}}],
  "scenes": [{{"id":"英文小写id","name":"场景名","description":"环境、时代、陈设、光线"}}],
  "shots": [{{
    "scene":"场景id","characters":["出镜角色id"],"duration":6,
    "shot_type":"中景","camera":"镜头运动",
    "visual_prompt":"画面描述",
    "narration":"旁白",
    "dialogue":[{{"speaker":"角色id","text":"台词"}}],
    "continue_from_prev":false
  }}]
}}
characters 和 scenes 只需列出本段新出现的；已有的直接用已有 id 引用。"""


def read_novel(path: Path, max_chars: int):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    paras = [p.strip() for p in text.replace("\r\n", "\n").split("\n") if p.strip()]
    if max_chars > 0:
        out, n = [], 0
        for p in paras:
            out.append(p)
            n += len(p)
            if n >= max_chars:   # 按段落取整，不截断半句话
                break
        paras = out
    return paras


def chunk_paras(paras, chunk_chars):
    chunks, cur, n = [], [], 0
    for p in paras:
        if cur and n + len(p) > chunk_chars:
            chunks.append("\n".join(cur))
            cur, n = [], 0
        cur.append(p)
        n += len(p)
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def normalize(sb):
    """校验与修正 LLM 输出：编号、时长范围、未知角色。"""
    char_ids = {c["id"] for c in sb["characters"]}
    scene_ids = {s["id"] for s in sb["scenes"]}
    for i, s in enumerate(sb["shots"], 1):
        s["id"] = f"s{i:03d}"
        s["duration"] = max(config.VIDEO_MIN_SEC, min(config.VIDEO_MAX_SEC, int(round(float(s.get("duration", 6))))))
        s["characters"] = [c for c in s.get("characters", []) if c in char_ids]
        if s.get("scene") not in scene_ids:
            s["scene"] = None
        s.setdefault("narration", "")
        s.setdefault("dialogue", [])
        s["dialogue"] = [d for d in s["dialogue"] if d.get("text")]
        if i == 1:
            s["continue_from_prev"] = False
        s.setdefault("continue_from_prev", False)
    return sb


def export_markdown(sb, path):
    """把 storyboard.json 导出成便于阅读/审稿的分镜脚本表格。"""
    cell = lambda s: str(s).replace("|", "｜").replace("\n", " ")
    names = {c["id"]: c["name"] for c in sb["characters"]}
    scenes = {s["id"]: s["name"] for s in sb["scenes"]}
    total = sum(s["duration"] for s in sb["shots"])
    md = [f"# 分镜脚本：{sb.get('title', '')}".rstrip("："), "",
          f"镜头数：{len(sb['shots'])}　｜　画面总时长：约 {total} 秒（配音较长的镜头合成时会自动延长）", "",
          f"**整体风格**：{sb.get('style', '')}", "", "## 角色", "",
          "| 角色 | 外观设定 | 配音音色 |", "|---|---|---|"]
    md += [f"| {cell(c['name'])} | {cell(c['appearance'])} | {c.get('voice', '')} {c.get('pitch', '')} |"
           for c in sb["characters"]]
    md += ["", "## 场景", "", "| 场景 | 描述 |", "|---|---|"]
    md += [f"| {cell(s['name'])} | {cell(s['description'])} |" for s in sb["scenes"]]
    md += ["", "## 分镜", "",
           "| 镜号 | 时长 | 场景 | 景别 / 运镜 | 出镜角色 | 画面内容 | 旁白 / 台词 | 衔接 |",
           "|---|---|---|---|---|---|---|---|"]
    t = 0
    for s in sb["shots"]:
        audio = []
        if s.get("narration"):
            audio.append(f"【旁白】{s['narration']}")
        audio += [f"【{names.get(d['speaker'], d['speaker'])}】{d['text']}" for d in s.get("dialogue", [])]
        md.append("| {} | {}s<br>({}–{}s) | {} | {}<br>{} | {} | {} | {} | {} |".format(
            s["id"], s["duration"], t, t + s["duration"], scenes.get(s.get("scene"), "—"),
            cell(s.get("shot_type", "")), cell(s.get("camera", "")),
            "、".join(names.get(c, c) for c in s["characters"]) or "—",
            cell(s["visual_prompt"]), cell("<br>".join(audio)) or "—",
            "接上镜末帧" if s.get("continue_from_prev") else ""))
        t += s["duration"]
    Path(path).write_text("\n".join(md) + "\n", encoding="utf-8")
    return path


def build_storyboard(paras, chunk_chars=2500, ark=None):
    from .ark_client import Ark
    ark = ark or Ark()
    sb = {"style": "", "characters": [], "scenes": [], "shots": []}
    chunks = chunk_paras(paras, chunk_chars)
    for idx, chunk in enumerate(chunks, 1):
        log(f"[分镜] 第 {idx}/{len(chunks)} 段，{len(chunk)} 字 ...")
        known = {"style": sb["style"],
                 "characters": sb["characters"],
                 "scenes": sb["scenes"],
                 "previous_shot": sb["shots"][-1] if sb["shots"] else None}
        user = ("已有设定（保持一致，直接引用 id）：\n" + json.dumps(known, ensure_ascii=False)
                + (f"\n\n额外要求：{config.STORYBOARD_HINT}" if config.STORYBOARD_HINT else "")
                + "\n\n请改编以下原文：\n" + chunk)
        res = ark.chat_json(SYSTEM, user)
        if not sb["style"]:
            sb["style"] = res.get("style", "")
        have_c = {c["id"] for c in sb["characters"]}
        have_s = {s["id"] for s in sb["scenes"]}
        sb["characters"] += [c for c in res.get("characters", []) if c["id"] not in have_c]
        sb["scenes"] += [s for s in res.get("scenes", []) if s["id"] not in have_s]
        sb["shots"] += res.get("shots", [])
    return normalize(sb)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input")
    ap.add_argument("--chars", type=int, default=0, help="只取前 N 字（按段落取整），0=全文")
    ap.add_argument("--chunk", type=int, default=2500, help="每次送给大模型的字数")
    ap.add_argument("--out", default=str(storyboard_path()))
    ap.add_argument("--export-md", action="store_true",
                    help="不调用大模型，只把现有 storyboard.json（如手改后）重新导出为 分镜脚本.md")
    a = ap.parse_args(argv)
    if a.export_md:
        from .utils import load_json
        sb = normalize(load_json(a.out))
        save_json(sb, a.out)
        log(f"[分镜] 已导出 {export_markdown(sb, Path(a.out).with_name('分镜脚本.md'))}")
        return
    if not a.input:
        ap.error("需要 --input")
    paras = read_novel(Path(a.input), a.chars)
    log(f"[分镜] 读取 {sum(map(len, paras))} 字，{len(paras)} 段")
    sb = build_storyboard(paras, a.chunk)
    sb.setdefault("title", Path(a.input).stem)
    save_json(sb, a.out)
    (config.STORYBOARD_DIR / "source_text.txt").write_text("\n".join(paras), encoding="utf-8")
    export_markdown(sb, Path(a.out).with_name("分镜脚本.md"))
    total = sum(s["duration"] for s in sb["shots"])
    log(f"[分镜] 完成：{len(sb['shots'])} 个镜头，约 {total} 秒 -> {a.out}")


if __name__ == "__main__":
    main()
