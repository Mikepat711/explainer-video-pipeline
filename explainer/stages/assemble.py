from __future__ import annotations

import shutil

from PIL import Image

from ..pipeline import Stage
from ..util import LIBASS_HELP, ffmpeg_with_libass, log, read_json, run


XFADE = {"fade": "fade", "slide_left": "slideleft", "slide_up": "slideup", "zoom_in": "zoomin",
         "zoom_out": "circleopen"}  # never dip to black: QA flags it as a black/blank segment


def transition(scene: dict, crossfade: float, fps: int) -> tuple[str, float]:
    """xfade transition and duration into this scene. Cuts and continuous shots switch on one frame: every
    scene video carries `crossfade` seconds of tail, and xfade drops whatever tail the transition does not use."""
    kind = scene.get("transition", "fade")
    if kind in ("cut", "continue"):
        return "fade", round(1 / fps, 4)
    return XFADE.get(kind, "fade"), crossfade


class Assemble(Stage):
    name = "assemble"
    deps = ("render", "mix", "captions")
    description = "concat scenes, burn captions, mux AAC -> final MP4 + poster"

    def inputs(self, ctx):
        return {"video": ctx.cfg["video"], "burn": ctx.cfg["captions"]["burn_in"], "slug": ctx.slug}

    def outputs(self, ctx):
        base = ctx.out_dir / ctx.slug
        return [base.with_suffix(".mp4"), base.with_suffix(".srt"), ctx.out_dir / "poster.png",
                ctx.out_dir / "poster.jpg"]

    def run(self, ctx):
        v = ctx.cfg["video"]
        tl = read_json(ctx.vdir / "timeline.json")
        ctx.out_dir.mkdir(parents=True, exist_ok=True)
        out = (ctx.out_dir / ctx.slug).with_suffix(".mp4")
        scenes = tl["scenes"]
        inputs, chain, prev = [], [], "0:v"
        for i, s in enumerate(scenes):
            inputs += ["-i", f"scenes/{s['id']}.mp4"]
            if i:
                label = f"x{i}"
                kind, dur = transition(s, tl["crossfade"], v["fps"])
                chain.append(f"[{prev}][{i}:v]xfade=transition={kind}:duration={dur}:"
                             f"offset={s['start']:.4f}[{label}]")
                prev = label
        ffmpeg = "ffmpeg"
        if ctx.cfg["captions"]["burn_in"]:
            ffmpeg = ffmpeg_with_libass()
            if not ffmpeg:
                raise SystemExit(LIBASS_HELP)
        post = ["ass=captions.ass"] if ctx.cfg["captions"]["burn_in"] else []
        chain.append(f"[{prev}]" + ",".join(post + ["format=yuv420p"]) + "[vout]")
        cmd = [ffmpeg, "-y", "-v", "error", *inputs, "-i", "audio/mix.wav",
               "-filter_complex", ";".join(chain), "-map", "[vout]", "-map", f"{len(scenes)}:a:0",
               "-c:v", "libx264", "-preset", v["preset"], "-crf", str(v["crf"]), "-profile:v", "high",
               "-level", "4.2", "-r", str(v["fps"]), "-g", str(v["fps"] * 2),
               "-c:a", "aac", "-b:a", v["audio_bitrate"], "-ar", str(ctx.cfg["audio"]["sample_rate"]), "-ac", "2",
               "-t", f"{tl['total']:.3f}", "-movflags", "+faststart",
               "-map_metadata", "-1", "-map_chapters", "-1", "-fflags", "+bitexact",
               "-flags:v", "+bitexact", "-flags:a", "+bitexact",
               "-metadata", f"title={tl['title']}", str(out.resolve())]
        log(f"    encoding {out.name} ({tl['total']:.1f}s)")
        run(cmd, cwd=ctx.vdir)
        shutil.copyfile(ctx.vdir / "captions.srt", out.with_suffix(".srt"))
        shutil.copyfile(ctx.vdir / "poster.png", ctx.out_dir / "poster.png")
        Image.open(ctx.vdir / "poster.png").convert("RGB").save(ctx.out_dir / "poster.jpg", quality=92)
