from __future__ import annotations

import numpy as np

from ..audio import samples, synth
from ..pipeline import Stage
from ..util import log, read_json, write_wav


def _stat(file: str) -> tuple:
    p = samples.resolve_path(file)
    return (p.stat().st_size, int(p.stat().st_mtime)) if p.exists() else (0, 0)


class Music(Stage):
    name = "music"
    deps = ("timeline",)
    description = "generate procedural score and sound-design cues"
    extra_code = ("audio",)

    def inputs(self, ctx):
        a = ctx.cfg["audio"]
        out = {k: a[k] for k in ("sample_rate", "music", "music_bpm", "music_key", "sfx")}
        if a.get("samples"):  # sample files are fingerprinted by size+mtime so a regenerated sound re-runs this
            out["samples"] = [dict(x, stat=list(_stat(x["file"]))) for x in a["samples"]]
        return out

    def outputs(self, ctx):
        return [ctx.vdir / "audio" / "music.wav", ctx.vdir / "audio" / "sfx.wav"]

    def run(self, ctx):
        a = ctx.cfg["audio"]
        tl = read_json(ctx.vdir / "timeline.json")
        sr, dur = a["sample_rate"], tl["total"]
        n = int(dur * sr)
        m = synth.music(dur, sr, a["music_bpm"], a["music_key"]) if a["music"] else np.zeros((n, 2), np.float32)
        s = synth.sfx(tl["events"], dur, sr) if a["sfx"] else np.zeros((n, 2), np.float32)
        if a.get("samples"):
            for note in samples.place(s, a["samples"], tl["scenes"], sr):
                log(f"    sample: {note}")
        write_wav(ctx.vdir / "audio" / "music.wav", m, sr)
        write_wav(ctx.vdir / "audio" / "sfx.wav", s, sr)
