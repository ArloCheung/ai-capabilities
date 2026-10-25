"""第4步：旁白/对白配音（默认免费的 edge-tts，每个角色固定音色）。

输出：work/4_audio/<镜头id>/NN.wav 以及 manifest.json（每句台词的文本、说话人、时长）。
"""
import argparse
import asyncio
import shutil

from . import config
from .utils import load_json, log, probe_duration, run, save_json, storyboard_path

AUDIO_DIR = config.AUDIO_DIR
SR = 24000


def shot_lines(sb, shot):
    names = {c["id"]: c for c in sb["characters"]}
    lines = []
    if shot.get("narration"):
        lines.append({"speaker": "narrator", "name": "旁白", "text": shot["narration"],
                      "voice": config.NARRATOR_VOICE, "pitch": "+0Hz"})
    if config.DIALOGUE_MODE != "native":
        for d in shot["dialogue"]:
            c = names.get(d["speaker"], {})
            lines.append({"speaker": d["speaker"], "name": c.get("name", d["speaker"]), "text": d["text"],
                          "voice": c.get("voice") or "zh-CN-YunxiNeural", "pitch": c.get("pitch") or "+0Hz"})
    return lines


async def _edge(text, voice, pitch, mp3):
    import edge_tts
    await edge_tts.Communicate(text, voice, pitch=pitch, rate="+0%").save(str(mp3))


def synth(line, wav, engine):
    if engine == "edge":
        mp3 = wav.with_suffix(".mp3")
        asyncio.run(_edge(line["text"], line["voice"], line["pitch"], mp3))
        run(["ffmpeg", "-y", "-i", str(mp3), "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16", str(wav)])
        mp3.unlink(missing_ok=True)
    else:  # none：按字数估算时长的静音，用于离线测试
        dur = max(1.0, len(line["text"]) / 4.5)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono", "-t", f"{dur:.2f}",
             "-sample_fmt", "s16", str(wav)])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default=config.TTS_ENGINE, choices=["edge", "none"])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    sb = load_json(storyboard_path())
    engine = a.engine
    for shot in sb["shots"]:
        d = AUDIO_DIR / shot["id"]
        mf = d / "manifest.json"
        if mf.exists() and not a.force and load_json(mf).get("engine") == engine:
            continue
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        items = []
        for i, line in enumerate(shot_lines(sb, shot), 1):
            wav = d / f"{i:02d}.wav"
            try:
                synth(line, wav, engine)
            except Exception as e:
                if engine == "edge":
                    log(f"[配音] edge-tts 不可用（{e.__class__.__name__}: {e}），改用静音占位")
                    engine = "none"
                    synth(line, wav, engine)
                else:
                    raise
            items.append({**line, "file": wav.name, "duration": round(probe_duration(wav), 3)})
        save_json({"shot": shot["id"], "engine": engine, "lines": items}, mf)
        log(f"[配音] {shot['id']}：{len(items)} 句，{sum(x['duration'] for x in items):.1f}s")
    log(f"[配音] 完成 -> {AUDIO_DIR}")


if __name__ == "__main__":
    main()
