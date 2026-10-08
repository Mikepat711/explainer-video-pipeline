"""Concat scene clips, mux the mix, write a share copy, optionally deliver."""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from ..pipeline import Stage
from ..share import share_copy
from ..util import log, read_json, run
from .render import _timing_map


def clip_paths(ctx) -> list[Path]:
    clips = ctx.vdir / "scenes"
    timing = read_json(ctx.common / "voice" / "timing.json")
    tm = _timing_map(timing)
    out = []
    for sc in ctx.selected_scenes():
        p = clips / f"{tm[sc.id].get('index', sc.index):02d}_{sc.id}.mp4"
        if p.is_file():
            out.append(p)
    return out


class Assemble(Stage):
    name = "assemble"
    scope = "variant"
    deps = ("render", "music")
    description = "concat clips, mux AAC, write poster"

    def inputs(self, ctx):
        return {"video": ctx.cfg["video"], "output": ctx.bundle.manifest.output_name}

    def outputs(self, ctx):
        name = Path(ctx.bundle.manifest.output_name).stem
        base = ctx.out_dir / name
        return [base.with_suffix(".mp4"), ctx.out_dir / "poster.png", ctx.out_dir / "poster.jpg"]

    def run(self, ctx):
        ctx.out_dir.mkdir(parents=True, exist_ok=True)
        name = Path(ctx.bundle.manifest.output_name).stem
        out = ctx.out_dir / f"{name}.mp4"
        clips = clip_paths(ctx)
        if not clips:
            raise RuntimeError("assemble: no scene clips")
        listing = ctx.vdir / "scenes" / "list.txt"
        listing.write_text("".join(f"file '{p.resolve()}'\n" for p in clips))
        mix = ctx.vdir / "audio" / "mix.wav"
        v = ctx.cfg["video"]
        run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-i", str(mix),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", str(v["audio_bitrate"]),
            "-ar", str(ctx.cfg["audio"]["sample_rate"]), "-ac", "2",
            "-movflags", "+faststart", "-shortest",
            "-map_metadata", "-1", "-map_chapters", "-1",
            "-metadata", f"title={ctx.bundle.title}",
            str(out),
        ])
        poster_src = ctx.vdir / "poster.png"
        if poster_src.is_file():
            shutil.copyfile(poster_src, ctx.out_dir / "poster.png")
            Image.open(poster_src).convert("RGB").save(ctx.out_dir / "poster.jpg", quality=92)
        log(f"    wrote {out}")


class Share(Stage):
    name = "share"
    scope = "variant"
    deps = ("assemble",)
    description = "size-capped share copy (under 25 MB by default)"

    def inputs(self, ctx):
        return {"max_mb": ctx.share_max_mb}

    def outputs(self, ctx):
        name = Path(ctx.bundle.manifest.output_name).stem
        return [ctx.out_dir / f"{name}-share.mp4"]

    def run(self, ctx):
        name = Path(ctx.bundle.manifest.output_name).stem
        src = ctx.out_dir / f"{name}.mp4"
        dest = ctx.out_dir / f"{name}-share.mp4"
        info = share_copy(src, dest, max_mb=float(ctx.share_max_mb))
        log(f"    share {info['file']}: {info['bytes'] / 1e6:.2f} MB")


def deliver_dir(cfg: dict) -> Path | None:
    from .. import localconf
    raw = (cfg.get("produce") or {}).get("deliver_dir") or localconf.get("EXPLAINER_DELIVER_DIR")
    if not raw:
        return None
    return Path(str(raw)).expanduser()


class Deliver(Stage):
    name = "deliver"
    scope = "variant"
    deps = ("assemble",)
    description = "copy the finished MP4 to the configured delivery folder"

    def inputs(self, ctx):
        d = deliver_dir(ctx.cfg)
        return {"dest": str(d) if d else "", "enabled": bool(ctx.deliver and d)}

    def outputs(self, ctx):
        # delivery is optional; stamp a receipt so the stage is cacheable
        return [ctx.out_dir / "delivered.json"]

    def run(self, ctx):
        from ..util import write_json
        dest_dir = deliver_dir(ctx.cfg) if ctx.deliver else None
        name = Path(ctx.bundle.manifest.output_name).stem
        src = ctx.out_dir / f"{name}.mp4"
        receipt = {"source": str(src), "dest": None, "copied": False}
        if not dest_dir:
            log("    deliver: no EXPLAINER_DELIVER_DIR configured; skipped")
            write_json(ctx.out_dir / "delivered.json", receipt)
            return
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        receipt.update({"dest": str(dest), "copied": True})
        write_json(ctx.out_dir / "delivered.json", receipt)
        log(f"    delivered {dest}")
