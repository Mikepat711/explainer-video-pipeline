"""Still frames and a contact sheet straight from a visual plan: a quick look at the animation design
without synthesising the narration or rendering video. Uses the real voice timing when it exists and
estimates it from word counts otherwise."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .gfx.render import render_png
from .stages.timeline import plan_timeline
from .util import log


def estimate_timing(script: dict, wpm: float = 160, gap: float = 0.4, lead: float = 0.35) -> dict:
    out = {}
    for sc in script["scenes"]:
        t, sents = lead, []
        for s in sc["sentences"]:
            d = len(s.split()) / wpm * 60
            sents.append({"text": s, "start": round(t, 3), "end": round(t + d, 3)})
            t += d + gap
        out[sc["id"]] = {"id": sc["id"], "duration": round(t - gap + 0.35, 3), "sentences": sents}
    return out


def key_times(sc: dict, per_scene: int) -> list[float]:
    """Moments worth seeing: just after each sentence's changes have played out, plus the final state."""
    dur = sc["duration"]
    marks = [min(dur - 0.15, s["end"] - 0.1) for s in sc["sentences"]]
    if len(marks) > per_scene:
        step = len(marks) / per_scene
        marks = [marks[min(len(marks) - 1, round((i + 1) * step) - 1)] for i in range(per_scene)]
    marks[-1] = dur - 0.15
    return sorted({round(max(0.2, m), 2) for m in marks})


def render_frames(plan: dict, script: dict, cfg: dict, out: Path, size: tuple[int, int], per_scene: int = 4,
                  timing: dict | None = None, scenes: list[str] | None = None) -> list[tuple[str, float, Path]]:
    out.mkdir(parents=True, exist_ok=True)
    full = plan_timeline(plan, timing or estimate_timing(script), cfg["length"], cfg["video"]["fps"])
    shots = []
    for i, sc in enumerate(full, 1):
        if scenes and sc["id"] not in scenes:
            continue
        for t in key_times(sc, per_scene):
            path = out / f"{i:02d}_{sc['id']}_{t:05.1f}s.png"
            render_png(sc["spec"], sc["duration"], {"index": i, "tail": 0.0}, cfg, size, t, path)
            shots.append((sc["id"], t, path))
            log(f"    {path.name}")
    return shots


def _font(size: int):
    for name in ("Inter-SemiBold.ttf", "Inter.ttf", "DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def contact_sheet(shots: list[tuple[str, float, Path]], out: Path, cols: int = 4, thumb_w: int = 480,
                  title: str = "") -> Path:
    if not shots:
        raise SystemExit("no frames to put on a contact sheet")
    with Image.open(shots[0][2]) as first:
        fw, fh = first.size
    tw = thumb_w
    th = round(fh * tw / fw)
    pad, cap, head = 14, 30, 56 if title else 0
    rows = -(-len(shots) // cols)
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, head + rows * (th + cap + pad) + pad), (14, 18, 28))
    dr = ImageDraw.Draw(sheet)
    if title:
        dr.text((pad, 14), title, fill=(232, 238, 247), font=_font(26))
    f = _font(17)
    for i, (sid, t, path) in enumerate(shots):
        r, c = divmod(i, cols)
        x, y = pad + c * (tw + pad), head + pad + r * (th + cap + pad)
        with Image.open(path) as im:
            sheet.paste(im.convert("RGB").resize((tw, th), Image.LANCZOS), (x, y))
        dr.text((x + 2, y + th + 6), f"{sid}  {t:.1f}s", fill=(160, 172, 196), font=f)
    sheet.save(out, quality=90)
    return out
