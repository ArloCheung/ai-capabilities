"""第5步：合成成片。

每个镜头：统一分辨率/帧率 -> 叠加配音（Seedance 环境音压低做底）-> 配音比画面长时冻结末帧补齐。
然后按顺序拼接、可选混入 BGM、烧录字幕，输出 work/5_final/final.mp4（另附 subs.srt；镜头片段在 work/5_final/_segments）。
"""
import argparse
import re
import wave

from . import config
from .step3_videos import video_path
from .step4_audio import AUDIO_DIR, SR
from .utils import has_audio, load_json, log, probe_duration, run, storyboard_path

OUT_DIR = config.FINAL_DIR
SEG_DIR = OUT_DIR / "_segments"       # 每个镜头标准化后的片段（中间文件）
LEAD, GAP, TAIL = 0.3, 0.25, 0.4      # 句首留白 / 句间停顿 / 句尾留白（秒）
SUB_MAX = config.SUB_MAX_CHARS        # 每行字幕最多字数


def build_voice_track(shot_id, out_wav):
    """把镜头内各句配音按顺序拼成一条 wav，返回 (总时长, 每句起止时间)。"""
    mf = AUDIO_DIR / shot_id / "manifest.json"
    lines = load_json(mf)["lines"] if mf.exists() else []
    silence = lambda sec: b"\x00\x00" * int(SR * sec)
    pcm, t, timeline = bytearray(silence(LEAD)), LEAD, []
    for i, ln in enumerate(lines):
        with wave.open(str(AUDIO_DIR / shot_id / ln["file"]), "rb") as w:
            frames = w.readframes(w.getnframes())
        pcm += frames
        dur = len(frames) / 2 / SR
        timeline.append((t, t + dur, ln))
        t += dur
        if i < len(lines) - 1:
            pcm += silence(GAP)
            t += GAP
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(pcm))
    return (t if lines else 0.0), timeline


def make_segment(shot, seg):
    src = video_path(shot["id"])
    vdur = probe_duration(src)
    vo = SEG_DIR / f"{shot['id']}_vo.wav"
    vo_dur, timeline = build_voice_track(shot["id"], vo)
    T = max(vdur, vo_dur + TAIL if vo_dur else 0)
    pad = max(0.0, T - vdur)
    W, H, FPS = config.OUT_W, config.OUT_H, config.OUT_FPS
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
          f"setsar=1,fps={FPS},tpad=stop_mode=clone:stop_duration={pad:.3f},trim=duration={T:.3f}[v]")
    if has_audio(src):
        amb = f"[0:a]aresample=48000,aformat=channel_layouts=stereo,volume={config.AMBIENT_VOLUME},apad,atrim=0:{T:.3f}[amb]"
    else:
        amb = f"anullsrc=r=48000:cl=stereo,atrim=0:{T:.3f}[amb]"
    voc = f"[1:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{T:.3f}[voc]"
    mix = "[amb][voc]amix=inputs=2:normalize=0:duration=longest[a]"
    run(["ffmpeg", "-y", "-i", str(src), "-i", str(vo), "-filter_complex", ";".join([vf, amb, voc, mix]),
         "-map", "[v]", "-map", "[a]", "-t", f"{T:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(seg)])
    return T, timeline


def split_sub(text):
    parts = [p for p in re.split(r"(?<=[，。！？；…—、,!?;])", text) if p.strip()]
    chunks, cur = [], ""
    for p in parts:
        while len(p) > SUB_MAX:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:SUB_MAX])
            p = p[SUB_MAX:]
        if cur and (len(cur) + len(p) > SUB_MAX or cur[-1] in "。！？…—"):
            chunks.append(cur)
            cur = ""
        cur += p
    if cur:
        chunks.append(cur)
    return [c.strip("，、 ") for c in chunks if c.strip("，、 ")]


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-subs", action="store_true", help="不烧录字幕（仍输出 srt）")
    ap.add_argument("--out", default="final.mp4")
    a = ap.parse_args(argv)
    sb = load_json(storyboard_path())
    SEG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    offset, subs, seg_list = 0.0, [], []
    for shot in sb["shots"]:
        seg = SEG_DIR / f"{shot['id']}.mp4"
        T, timeline = make_segment(shot, seg)
        for start, end, ln in timeline:
            pieces = split_sub(ln["text"])
            total = sum(len(p) for p in pieces) or 1
            t = start
            for p in pieces:
                d = (end - start) * len(p) / total
                subs.append((offset + t, offset + t + d, p))
                t += d
        seg_list.append(seg)
        log(f"[合成] {shot['id']} {T:.1f}s")
        offset += T

    srt = OUT_DIR / "subs.srt"
    srt.write_text("\n".join(f"{i}\n{srt_time(s)} --> {srt_time(e)}\n{txt}\n"
                             for i, (s, e, txt) in enumerate(subs, 1)), encoding="utf-8")
    lst = SEG_DIR / "concat.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in seg_list), encoding="utf-8")
    joined = OUT_DIR / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy",
         str(joined.resolve())], cwd=SEG_DIR)

    # 最终：字幕 + BGM + 首尾淡入淡出。cwd=OUT_DIR，字幕用相对路径，避开 Windows 路径转义
    fade_out = max(0.0, offset - 1.0)
    vf = f"fade=t=in:st=0:d=0.8,fade=t=out:st={fade_out:.2f}:d=1"
    if not a.no_subs:
        style = (f"FontName={config.SUB_FONT},FontSize={config.SUB_FONTSIZE},PrimaryColour=&H00FFFFFF,"
                 f"OutlineColour=&H00000000,BorderStyle=1,Outline=1.2,Shadow=0,MarginV=28")
        vf = f"subtitles=subs.srt:force_style='{style}'," + vf
    if config.AIGC_LABEL:
        # AI 生成内容显式标识（右上角半透明角标）
        (OUT_DIR / "label.txt").write_text(config.AIGC_LABEL, encoding="utf-8")
        font = config.LABEL_FONTFILE.replace("\\", "/").replace(":", r"\:")
        fs = max(16, int(config.OUT_H * 0.025))
        vf += (f",drawtext=fontfile='{font}':textfile=label.txt:fontsize={fs}:fontcolor=white@0.85:"
               f"box=1:boxcolor=black@0.35:boxborderw={fs // 3}:x=w-tw-{fs}:y={fs}")
    cmd = ["ffmpeg", "-y", "-i", joined.name]
    af = f"afade=t=in:st=0:d=0.8,afade=t=out:st={fade_out:.2f}:d=1"
    if config.BGM_PATH:
        cmd += ["-stream_loop", "-1", "-i", config.BGM_PATH]
        fc = (f"[0:v]{vf}[v];[1:a]volume={config.BGM_VOLUME},atrim=0:{offset:.3f}[bgm];"
              f"[0:a][bgm]amix=inputs=2:normalize=0:duration=first,{af}[a]")
        cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", vf, "-af", af]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", a.out]
    run(cmd, cwd=OUT_DIR)
    log(f"[合成] 完成：{OUT_DIR / a.out}（{offset:.1f} 秒，{len(seg_list)} 个镜头，{len(subs)} 条字幕）")


if __name__ == "__main__":
    main()
