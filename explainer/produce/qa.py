"""QA for a bundle build: loudness, black frames, contact sheet, optional ASR."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..pipeline import Stage
from ..stages.qa import blackdetect, frame_stats, loudness, probe
from ..util import log, read_json, run, write_json
from .asr import asr_check
from .render import _timing_map


class QA(Stage):
    name = "qa"
    scope = "variant"
    deps = ("assemble",)
    description = "loudness, black-frame detection, contact sheet, optional ASR"

    def outputs(self, ctx):
        return [ctx.out_dir / "qa.json", ctx.out_dir / "qa.md", ctx.out_dir / "contact_sheet.jpg"]

    def run(self, ctx):
        name = Path(ctx.bundle.manifest.output_name).stem
        mp4 = ctx.out_dir / f"{name}.mp4"
        timing = read_json(ctx.common / "voice" / "timing.json")
        mix = read_json(ctx.vdir / "audio" / "mix_report.json") if (ctx.vdir / "audio" / "mix_report.json").exists() else {}
        info = probe(mp4)
        loud = loudness(mp4)
        blacks = blackdetect(mp4)
        tm = _timing_map(timing)
        fdir = ctx.out_dir / "frames"
        fdir.mkdir(exist_ok=True)
        for old in fdir.glob("*.png"):
            old.unlink()
        start, acc = {}, 0.0
        fps = ctx.fps
        import math
        for sid, row in sorted(tm.items(), key=lambda kv: kv[1].get("index", 0)):
            start[sid] = acc
            acc += math.ceil(row["duration"] * fps) / fps
        frames = []
        for sid, row in sorted(tm.items(), key=lambda kv: kv[1].get("index", 0)):
            if ctx.scenes_filter and sid not in ctx.scenes_filter:
                continue
            for frac, tag in ((0.5, sid), (0.85, sid)):
                t = start[sid] + row["duration"] * frac
                p = fdir / f"t{t:07.2f}_{tag}.png"
                run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1", str(p)])
                if not p.is_file():
                    continue
                st = frame_stats(Image.open(p))
                flags = []
                if st["std"] < 4 or st["edge"] < 0.6:
                    flags.append("blank-or-near-empty")
                frames.append({"t": round(t, 2), "scene": sid, "file": f"frames/{p.name}", **st, "flags": flags})
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
        captions = [c for sc in ctx.bundle.scenes for c in sc.captions]
        asr = asr_check(mp4, captions, ctx.cfg, ctx.asr)
        tp = loud.get("true_peak_dbtp")
        checks = {
            "video_h264": v["codec_name"] == "h264",
            "resolution_ok": True,
            "audio_aac": bool(a and a["codec_name"] == "aac"),
            "audible": loud["integrated_lufs"] is not None and loud["integrated_lufs"] > -30,
            "true_peak_ok": tp is None or tp <= -1.0,
            "no_black_segments": not blacks,
            "no_blank_frames": not any(f["flags"] for f in frames),
        }
        if asr and not asr.get("skipped"):
            checks["asr_ok"] = bool(asr.get("passed"))
        report = {
            "file": mp4.name,
            "title": ctx.bundle.title,
            "duration_s": round(float(info["format"]["duration"]), 2),
            "video": {k: v.get(k) for k in ("codec_name", "profile", "width", "height", "r_frame_rate", "pix_fmt")},
            "audio": {k: a.get(k) for k in ("codec_name", "sample_rate", "channels")} if a else None,
            "loudness": loud, "mix": mix, "black_segments": blacks, "frames": frames,
            "narration": {k: timing.get(k) for k in ("engine", "voice", "total")},
            "asr": asr, "checks": checks, "passed": all(checks.values()),
        }
        write_json(ctx.out_dir / "qa.json", report)
        self.contact_sheet(ctx, frames)
        md = [f"# QA — {ctx.bundle.title}", "",
              f"- Duration: {report['duration_s']} s, {v['width']}x{v['height']} {v['codec_name']}",
              f"- Integrated loudness: {loud['integrated_lufs']} LUFS; true peak: {loud['true_peak_dbtp']} dBTP",
              f"- Black segments: {len(blacks)}",
              f"- Frames sampled: {len(frames)}; flagged: {sum(1 for f in frames if f['flags'])}"]
        if asr:
            md.append(f"- ASR: {asr}")
        md += ["", "## Checks", ""]
        md += [f"- [{'x' if ok else ' '}] {k}" for k, ok in checks.items()]
        (ctx.out_dir / "qa.md").write_text("\n".join(md) + "\n")
        log(f"    QA {'PASSED' if report['passed'] else 'has findings'}: "
            f"{loud['integrated_lufs']} LUFS, TP {loud['true_peak_dbtp']} dBTP")
        for k, ok in checks.items():
            if not ok:
                log(f"      failed: {k}")

    def contact_sheet(self, ctx, frames):
        thumbs = []
        for f in frames:
            p = ctx.out_dir / f["file"]
            if p.is_file():
                thumbs.append(Image.open(p).convert("RGB"))
        if not thumbs:
            Image.new("RGB", (64, 64), (12, 14, 22)).save(ctx.out_dir / "contact_sheet.jpg")
            return
        w0, h0 = thumbs[0].size
        tw = 384 if w0 > h0 else 216
        th = int(tw * h0 / w0)
        cols = 6 if w0 > h0 else 8
        rows = -(-len(thumbs) // cols)
        sheet = Image.new("RGB", (cols * (tw + 8) + 8, rows * (th + 30) + 8), (12, 14, 22))
        from PIL import ImageDraw, ImageFont
        d = ImageDraw.Draw(sheet)
        try:
            from ..draw.lib import find_font_file
            font = ImageFont.truetype(str(find_font_file("Poppins-SemiBold.ttf")), 16)
        except Exception:
            font = ImageFont.load_default()
        for i, (im, f) in enumerate(zip(thumbs, frames)):
            x, y = 8 + (i % cols) * (tw + 8), 8 + (i // cols) * (th + 30)
            sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
            d.text((x, y + th + 5), f"{f['t']:.1f}s {f['scene']}" + (" ⚠" if f["flags"] else ""),
                   fill=(200, 205, 220), font=font)
        sheet.save(ctx.out_dir / "contact_sheet.jpg", quality=88)
