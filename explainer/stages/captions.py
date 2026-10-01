from __future__ import annotations

import re

from ..config import frame_size
from ..gfx.theme import Theme
from ..pipeline import Stage
from ..util import read_json


def _balanced_split(words: list[str], parts: int) -> list[list[str]]:
    """Split words into `parts` groups of similar character length, preferring clause punctuation."""
    if parts <= 1:
        return [words]
    total = len(" ".join(words))
    groups, cur, acc = [], [], 0
    for i, w in enumerate(words):
        cur.append(w)
        acc += len(w) + 1
        remaining = parts - len(groups) - 1
        if remaining <= 0 or i == len(words) - 1:
            continue
        target = total * (len(groups) + 1) / parts
        near = abs(acc - target) <= total / parts * 0.3
        if acc >= target or (near and re.search(r"[,;:]$", w)):
            groups.append(cur)
            cur = []
    groups.append(cur)
    return [g for g in groups if g]


def _wrap(words: list[str], max_chars: int) -> list[str]:
    text = " ".join(words)
    if len(text) <= max_chars:
        return [text]
    return [" ".join(g) for g in _balanced_split(words, 2)]


def chunk_sentence(text: str, max_chars: int, max_lines: int) -> list[list[str]]:
    """Split a sentence into cues of <= max_lines balanced lines, avoiding one-word orphan cues."""
    words = text.split()
    n_lines = -(-len(text) // max_chars)
    n_cues = max(1, -(-n_lines // max_lines))
    while True:
        cues = [_wrap(g, max_chars) for g in _balanced_split(words, n_cues)]
        if all(len(c) <= max_lines and all(len(ln) <= max_chars + 4 for ln in c) for c in cues) \
                or n_cues >= len(words):
            return cues
        n_cues += 1


def ts(t: float, sep: str = ",") -> str:
    t = max(0.0, t)
    h, rem = divmod(int(round(t * 1000)), 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def ass_ts(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def build_cues(tl: dict, max_chars: int, max_lines: int) -> list[dict]:
    cues = []
    for sc in tl["scenes"]:
        for s in sc["sentences"]:
            blocks = chunk_sentence(s["text"], max_chars, max_lines)
            total_chars = sum(len(" ".join(b)) for b in blocks) or 1
            t = sc["start"] + s["start"]
            span = s["end"] - s["start"]
            for b in blocks:
                d = span * len(" ".join(b)) / total_chars
                cues.append({"start": t, "end": t + d, "lines": b})
                t += d
    for a, b in zip(cues, cues[1:]):
        if b["start"] - a["end"] < 0.25:
            a["end"] = b["start"] - 0.02
        else:
            a["end"] += 0.2
    return cues


class Captions(Stage):
    name = "captions"
    deps = ("timeline",)
    description = "build SRT + styled ASS captions from narration timing"

    def inputs(self, ctx):
        return {"captions": ctx.cfg["captions"], "aspect": ctx.cfg["video"]["aspect"], "font": ctx.cfg["style"]}

    def outputs(self, ctx):
        return [ctx.vdir / "captions.srt", ctx.vdir / "captions.ass"]

    def run(self, ctx):
        c = ctx.cfg["captions"]
        tl = read_json(ctx.vdir / "timeline.json")
        w, h = frame_size(ctx.cfg)
        portrait = h > w
        max_chars = c["max_chars_9x16"] if portrait else c["max_chars_16x9"]
        cues = build_cues(tl, max_chars, c["max_lines"])
        srt = []
        for i, cue in enumerate(cues, 1):
            srt += [str(i), f"{ts(cue['start'])} --> {ts(cue['end'])}", *cue["lines"], ""]
        (ctx.vdir / "captions.srt").write_text("\n".join(srt))
        theme = Theme(ctx.cfg["style"])
        fam, _ = theme.face("semibold")
        size = 58 if portrait else 46
        margin_v = (h - 1640) if portrait else 44
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{fam},{size},&H00FFFFFF,&H00FFFFFF,&H50140A05,&H00000000,0,0,0,0,100,100,0,0,3,14,0,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = [f"Dialogue: 0,{ass_ts(cu['start'])},{ass_ts(cu['end'])},Caption,,0,0,0,,"
                  + r"{\fad(160,140)}" + r"\N".join(ln.replace("{", "(").replace("}", ")") for ln in cu["lines"])
                  for cu in cues]
        (ctx.vdir / "captions.ass").write_text(header + "\n".join(events) + "\n")
