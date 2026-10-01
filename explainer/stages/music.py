from __future__ import annotations

import numpy as np

from ..audio import synth
from ..pipeline import Stage
from ..util import read_json, write_wav


class Music(Stage):
    name = "music"
    deps = ("timeline",)
    description = "generate procedural score and sound-design cues"
    extra_code = ("audio",)

    def inputs(self, ctx):
        a = ctx.cfg["audio"]
        return {k: a[k] for k in ("sample_rate", "music", "music_bpm", "music_key", "sfx")}

    def outputs(self, ctx):
        return [ctx.vdir / "audio" / "music.wav", ctx.vdir / "audio" / "sfx.wav"]

    def run(self, ctx):
        a = ctx.cfg["audio"]
        tl = read_json(ctx.vdir / "timeline.json")
        sr, dur = a["sample_rate"], tl["total"]
        n = int(dur * sr)
        m = synth.music(dur, sr, a["music_bpm"], a["music_key"]) if a["music"] else np.zeros((n, 2), np.float32)
        s = synth.sfx(tl["events"], dur, sr) if a["sfx"] else np.zeros((n, 2), np.float32)
        write_wav(ctx.vdir / "audio" / "music.wav", m, sr)
        write_wav(ctx.vdir / "audio" / "sfx.wav", s, sr)
