from __future__ import annotations

import re

from ..config import frame_size
from ..gfx.theme import Theme
from ..pipeline import Stage
from ..util import log, read_json
from ..wordtime import align, find_binary, find_model, whisper_words


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


def build_cues(tl: dict, max_chars: int, max_lines: int, words: dict | None = None) -> list[dict]:
    """Caption cues. With `words` ({scene id: [{text, start, end}]} heard in that scene's narration), each cue
    starts on the word it opens with; otherwise a sentence's span is shared out by character count."""
    cues = []
    for sc in tl["scenes"]:
        heard = (words or {}).get(sc["id"])
        for s in sc["sentences"]:
            blocks = chunk_sentence(s["text"], max_chars, max_lines)
            total_chars = sum(len(" ".join(b)) for b in blocks) or 1
            t = sc["start"] + s["start"]
            span = s["end"] - s["start"]
            starts, hits = None, []
            if heard:
                window = [h for h in heard if s["start"] - 0.4 <= h["start"] <= s["end"] + 0.4]
                hits = align([w for b in blocks for ln in b for w in ln.split()], window) if window else []
                if hits:
                    starts, i = [], 0
                    for b in blocks:
                        first = next((h for h in hits[i:i + 2] if h), None)
                        starts.append(sc["start"] + first[0] if first else None)
                        i += sum(len(ln.split()) for ln in b)
            est = []
            for b in blocks:
                d = span * len(" ".join(b)) / total_chars
                est.append((t, t + d))
                t += d
            wi = 0
            for k, b in enumerate(blocks):
                n_words = sum(len(ln.split()) for ln in b)
                times = [sc["start"] + h[0] if h else None for h in hits[wi:wi + n_words]] if hits else []
                wi += n_words
                start, end = est[k]
                timed = False
                # sentence starts are exact (TTS is timed per sentence); word timing places the splits inside one
                if k and starts and starts[k] is not None and est[k][0] - 0.6 <= starts[k] <= est[k][1]:
                    start, timed = max(starts[k], sc["start"] + s["start"] - 0.1), True
                cues.append({"start": start, "end": end, "lines": b, "est": not timed, "times": times})
    for a, b in zip(cues, cues[1:]):
        if b["start"] - a["end"] < 0.25 or not b["est"]:
            a["end"] = b["start"] - 0.02
        else:
            a["end"] += 0.2
    for c in cues:
        c.pop("est")
        if not any(c["times"]):
            c.pop("times")
    return cues


def karaoke(cue: dict) -> str:
    """ASS text where each word lights (secondary -> primary colour) as it is spoken. Words whisper did not catch
    are spread evenly between their heard neighbours."""
    words = [w for ln in cue["lines"] for w in ln.split()]
    breaks = {sum(len(ln.split()) for ln in cue["lines"][:i]) for i in range(1, len(cue["lines"]))}
    times = list(cue["times"]) + [None] * (len(words) - len(cue["times"]))
    times[0] = cue["start"] if times[0] is None else max(times[0], cue["start"])
    known = [i for i, t in enumerate(times) if t is not None]
    for i in range(len(times)):
        if times[i] is None:
            lo = max(k for k in known if k < i)
            hi = next((k for k in known if k > i), None)
            t_hi, i_hi = (times[hi], hi) if hi is not None else (cue["end"] - 0.2, len(times))
            times[i] = times[lo] + (t_hi - times[lo]) * (i - lo) / (i_hi - lo)
    for i in range(1, len(times)):
        times[i] = min(max(times[i], times[i - 1]), cue["end"])
    out = [r"{\k%d}" % round((times[0] - cue["start"]) * 100)] if times[0] > cue["start"] else []
    for i, w in enumerate(words):
        nxt = times[i + 1] if i + 1 < len(words) else min(cue["end"], times[i] + 0.6)
        out.append((r"\N" if i in breaks else (" " if i else "")) + r"{\kf%d}" % max(1, round((nxt - times[i]) * 100))
                   + w.replace("{", "(").replace("}", ")"))
    return "".join(out)


def word_timings(ctx, tl: dict) -> dict | None:
    """Heard words per scene, or None when word timing is off or whisper.cpp / its model is missing."""
    c = ctx.cfg["captions"]
    if str(c.get("word_timing", "auto")).lower() in ("off", "false", "none", ""):
        return None
    model, binary = find_model(c.get("whisper_model", "")), find_binary(c.get("whisper_bin", ""))
    if not (model and binary):
        log("    word timing: whisper-cli or its model not found; captions use estimated timing")
        return None
    out = {}
    for sc in tl["scenes"]:
        wav = ctx.common / "voice" / f"{sc['id']}.wav"
        if wav.exists() and (w := whisper_words(wav, model, binary)):
            out[sc["id"]] = w
    log(f"    word timing: {len(out)}/{len(tl['scenes'])} scene(s) aligned with whisper.cpp ({model.name})")
    return out or None


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
        cues = build_cues(tl, max_chars, c["max_lines"], word_timings(ctx, tl))
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
Style: Caption,{fam},{size},&H00FFFFFF,{"&H55FFFFFF" if c.get("highlight_words") else "&H00FFFFFF"},&H50140A05,&H00000000,0,0,0,0,100,100,0,0,3,14,0,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        hl = bool(c.get("highlight_words"))
        events = [f"Dialogue: 0,{ass_ts(cu['start'])},{ass_ts(cu['end'])},Caption,,0,0,0,,"
                  + r"{\fad(160,140)}"
                  + (karaoke(cu) if hl and cu.get("times") else
                     r"\N".join(ln.replace("{", "(").replace("}", ")") for ln in cu["lines"]))
                  for cu in cues]
        (ctx.vdir / "captions.ass").write_text(header + "\n".join(events) + "\n")
