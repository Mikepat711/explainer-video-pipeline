from __future__ import annotations

import json
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..gfx.theme import Theme
from ..pipeline import Stage
from ..util import log, read_json, run, write_json
from ..writer import banner, read_metas, writer_name


def loudness(path) -> dict:
    res = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
               "-af", "ebur128=peak=true", "-f", "null", "-"])
    summ = res.stderr[res.stderr.rfind("Summary:"):]
    def grab(label):
        m = re.search(label + r":\s*(-?[\d.]+|-inf)", summ)
        return float(m.group(1)) if m and m.group(1) != "-inf" else None
    return {"integrated_lufs": grab(r"I"), "lra_lu": grab(r"LRA"), "true_peak_dbtp": grab(r"Peak")}


def probe(path) -> dict:
    res = run(["ffprobe", "-v", "error", "-show_entries",
               "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels,profile,pix_fmt:"
               "format=duration,bit_rate:format_tags", "-of", "json", str(path)])
    return json.loads(res.stdout)


def blackdetect(path) -> list[str]:
    res = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vf",
               "blackdetect=d=0.08:pix_th=0.04", "-an", "-f", "null", "-"])
    return re.findall(r"black_start:\S+ black_end:\S+ black_duration:\S+", res.stderr)


def frame_stats(img: Image.Image) -> dict:
    g = np.asarray(img.convert("L"), dtype=np.float32)
    edges = np.abs(np.diff(g, axis=1)).mean() + np.abs(np.diff(g, axis=0)).mean()
    return {"mean": round(float(g.mean()), 1), "std": round(float(g.std()), 2), "edge": round(float(edges), 3)}


def writer_report(writers: list[dict]) -> list[str]:
    """qa.md lines naming who wrote research/script/plan, led by a warning if the fallback was used."""
    fallbacks = [m for m in writers if m.get("fallback")]
    md = []
    if fallbacks:
        md += [f"> **WARNING: FALLBACK WRITER USED for {', '.join(m['stage'] for m in fallbacks)}.** "
               f"Claude was unavailable ({fallbacks[0].get('reason') or 'unknown reason'}), so this video's "
               "research, script and visual plan are extractive placeholders. Fix the Claude Code CLI and "
               "re-run; the pipeline retries the writer automatically.", ""]
    md.append("- Written by: " + (", ".join(f"{m['stage']} = {m['writer']}" + (" (FALLBACK)" if m.get("fallback")
                                                                                 else "") for m in writers) or "?"))
    return md


class QA(Stage):
    name = "qa"
    deps = ("assemble",)
    description = "loudness stats, sampled frames, blank/layout checks"

    def outputs(self, ctx):
        return [ctx.out_dir / "qa.json", ctx.out_dir / "qa.md", ctx.out_dir / "contact_sheet.jpg"]

    def run(self, ctx):
        tl = read_json(ctx.vdir / "timeline.json")
        mp4 = (ctx.out_dir / ctx.slug).with_suffix(".mp4")
        info = probe(mp4)
        loud = loudness(mp4)
        blacks = blackdetect(mp4)
        fdir = ctx.out_dir / "frames"
        fdir.mkdir(exist_ok=True)
        for old in fdir.glob("*.png"):
            old.unlink()
        times = []
        for i, sc in enumerate(tl["scenes"]):
            times += [(sc["id"], sc["start"] + sc["duration"] * 0.5),
                      (sc["id"], sc["start"] + max(0.2, sc["duration"] - 0.7))]
            if i:
                times += [(f"cut-{sc['id']}", sc["start"] + 0.05), (f"cut-{sc['id']}", sc["start"] + 0.3)]
        times.sort(key=lambda x: x[1])
        frames = []
        for sid, t in times:
            p = fdir / f"t{t:07.2f}_{sid}.png"
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1", str(p)])
            st = frame_stats(Image.open(p))
            flags = []
            if st["std"] < 4 or st["edge"] < 0.6:
                flags.append("blank-or-near-empty")
            frames.append({"t": round(t, 2), "scene": sid, "file": f"frames/{p.name}", **st, "flags": flags})
        layout = read_json(ctx.vdir / "layout_report.json")
        mix = read_json(ctx.vdir / "audio" / "mix_report.json")
        writers = read_metas(ctx.common)
        fallbacks = [m for m in writers if m.get("fallback")]
        timing = read_json(ctx.common / "voice" / "timing.json")
        pace = {k: timing.get(k) for k in ("engine", "wpm", "speaking_wpm", "target_wpm", "speed", "tempo")}
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
        checks = {
            "video_h264": v["codec_name"] == "h264",
            "resolution_ok": (v["width"], v["height"]) in ((1920, 1080), (1080, 1920)),
            "audio_aac": bool(a and a["codec_name"] == "aac"),
            "audible": loud["integrated_lufs"] is not None and loud["integrated_lufs"] > -30,
            "true_peak_ok": loud["true_peak_dbtp"] is not None and loud["true_peak_dbtp"] <= -0.5,
            "no_black_segments": not blacks,
            "no_blank_frames": not any(f["flags"] for f in frames),
            "no_layout_issues": not any(r["issues"] for r in layout),
            "no_fallback_writer": not fallbacks,
        }
        report = {"file": mp4.name, "duration_s": round(float(info["format"]["duration"]), 2),
                  "video": {k: v.get(k) for k in ("codec_name", "profile", "width", "height", "r_frame_rate",
                                                  "pix_fmt")},
                  "audio": {k: a.get(k) for k in ("codec_name", "sample_rate", "channels")} if a else None,
                  "container_tags": info["format"].get("tags", {}),
                  "loudness": loud, "mix": mix, "black_segments": blacks, "frames": frames,
                  "layout": layout, "writer": writers, "fallback_writer": bool(fallbacks), "narration": pace,
                  "checks": checks, "passed": all(checks.values())}
        write_json(ctx.out_dir / "qa.json", report)
        self.contact_sheet(ctx, frames)
        md = [f"# QA — {tl['title']} ({ctx.variant})", ""] + writer_report(writers)
        md += [f"- Narration: {pace['engine']}, {pace['wpm']} wpm (target {pace['target_wpm']}), speed "
              f"{pace['speed']}, tempo {pace['tempo']}",
              f"- Duration: {report['duration_s']} s, {v['width']}x{v['height']} {v['codec_name']} "
              f"{v.get('profile')}, audio {a['codec_name'] if a else 'none'}",
              f"- Integrated loudness: {loud['integrated_lufs']} LUFS; true peak: {loud['true_peak_dbtp']} dBTP; "
              f"LRA: {loud['lra_lu']} LU", f"- Black segments: {len(blacks)}",
              f"- Frames sampled: {len(frames)}; flagged: {sum(1 for f in frames if f['flags'])}",
              f"- Layout issues: {sum(len(r['issues']) for r in layout)}", "", "## Checks", ""]
        md += [f"- [{'x' if ok else ' '}] {k}" for k, ok in checks.items()]
        issues = [f"- `{r['id']}`: {m}" for r in layout for m in r["issues"]]
        if issues:
            md += ["", "## Layout issues", ""] + issues
        (ctx.out_dir / "qa.md").write_text("\n".join(md) + "\n")
        log(f"    QA {'PASSED' if report['passed'] else 'has findings'}: {loud['integrated_lufs']} LUFS, "
            f"TP {loud['true_peak_dbtp']} dBTP, {len(frames)} frames checked")
        for k, ok in checks.items():
            if not ok:
                log(f"      failed: {k}")
        if fallbacks:
            banner(", ".join(m["stage"] for m in fallbacks), fallbacks[0].get("reason") or "see qa.md",
                   writer_name(ctx.cfg))

    def contact_sheet(self, ctx, frames):
        thumbs = [Image.open(ctx.out_dir / f["file"]).convert("RGB") for f in frames]
        if not thumbs:
            return
        w0, h0 = thumbs[0].size
        tw = 384 if w0 > h0 else 216
        th = int(tw * h0 / w0)
        cols = 6 if w0 > h0 else 8
        rows = -(-len(thumbs) // cols)
        sheet = Image.new("RGB", (cols * (tw + 8) + 8, rows * (th + 30) + 8), (12, 14, 22))
        d = ImageDraw.Draw(sheet)
        try:
            path = subprocess.run(["fc-match", "-f", "%{file}", Theme({}).family], capture_output=True,
                                  text=True).stdout.strip()
            font = ImageFont.truetype(path, 16)
        except (OSError, FileNotFoundError):
            font = ImageFont.load_default()
        for i, (im, f) in enumerate(zip(thumbs, frames)):
            x, y = 8 + (i % cols) * (tw + 8), 8 + (i // cols) * (th + 30)
            sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
            d.text((x, y + th + 5), f"{f['t']:.1f}s {f['scene']}" + (" ⚠" if f["flags"] else ""),
                   fill=(200, 205, 220), font=font)
        sheet.save(ctx.out_dir / "contact_sheet.jpg", quality=88)
