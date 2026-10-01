from __future__ import annotations

import math
import subprocess
from pathlib import Path

import cairo

from .canvas import Layout, Motion, Painter
from .scenes import TEMPLATES
from .theme import Theme


def make_background(L: Layout, T: Theme) -> cairo.ImageSurface:
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, L.w, L.h)
    c = cairo.Context(surf)
    g = cairo.LinearGradient(0, 0, L.w * 0.3, L.h)
    g.add_color_stop_rgb(0, *T.c["bg1"])
    g.add_color_stop_rgb(1, *T.c["bg0"])
    c.set_source(g)
    c.paint()
    if T.grid:
        step = 48
        c.set_source_rgba(*T.c["grid"], 0.55)
        for y in range(step // 2, L.h, step):
            for x in range(step // 2, L.w, step):
                c.arc(x, y, 1.6, 0, 2 * math.pi)
                c.fill()
    v = cairo.RadialGradient(L.w / 2, L.h / 2, min(L.w, L.h) * 0.35, L.w / 2, L.h / 2, max(L.w, L.h) * 0.75)
    v.add_color_stop_rgba(0, 0, 0, 0, 0)
    v.add_color_stop_rgba(1, 0, 0, 0, 0.35 if T.name == "midnight" else 0.08)
    c.set_source(v)
    c.paint()
    return surf


class SceneRenderer:
    def __init__(self, spec: dict, dur: float, meta: dict, cfg: dict, size: tuple[int, int]):
        self.L = Layout(*size)
        self.T = Theme(cfg["style"])
        Motion.configure(cfg["style"])
        meta = dict(meta, progress_bar=self.T.progress_bar and meta.get("progress_bar", True))
        cls = TEMPLATES.get(spec.get("template", "bullets"), TEMPLATES["bullets"])
        self.scene = cls(spec, dur, self.L, meta)
        self.bg = make_background(self.L, self.T)
        self.surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.L.w, self.L.h)
        self.ctx = cairo.Context(self.surf)
        self.ctx.set_antialias(cairo.ANTIALIAS_BEST)
        fo = cairo.FontOptions()
        fo.set_antialias(cairo.ANTIALIAS_GRAY)
        fo.set_hint_style(cairo.HINT_STYLE_SLIGHT)
        self.ctx.set_font_options(fo)
        self.painter = Painter(self.ctx, self.L, self.T)

    def frame(self, t: float) -> cairo.ImageSurface:
        c = self.ctx
        c.identity_matrix()
        c.set_source_surface(self.bg, 0, 0)
        c.paint()
        self.scene.draw(self.painter, t)
        self.surf.flush()
        return self.surf

    def probe(self, t: float) -> dict:
        self.painter.record = True
        self.painter.boxes = []
        self.painter.warnings = []
        self.frame(t)
        self.painter.record = False
        return {"boxes": list(self.painter.boxes), "warnings": list(dict.fromkeys(self.painter.warnings))}


def make_renderer(spec: dict, dur: float, meta: dict, cfg: dict, size: tuple[int, int]):
    """The visual-plan renderer for plan scenes, the legacy template renderer otherwise."""
    if spec.get("engine") == "plan":
        from .stage import PlanRenderer
        return PlanRenderer(spec, dur, meta, cfg, size)
    return SceneRenderer(spec, dur, meta, cfg, size)


def render_video(spec: dict, dur: float, meta: dict, cfg: dict, size: tuple[int, int], out: Path) -> None:
    r = make_renderer(spec, dur, meta, cfg, size)
    fps = cfg["video"]["fps"]
    n = max(1, round((dur + meta.get("tail", 0.0)) * fps))
    w, h = size
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{w}x{h}",
           "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "14",
           "-pix_fmt", "yuv420p", "-map_metadata", "-1", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(n):
            surf = r.frame(i / fps)
            proc.stdin.write(surf.get_data())
        proc.stdin.close()
        err = proc.stderr.read().decode()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg scene encode failed: {err[-800:]}")
    finally:
        if proc.poll() is None:
            proc.kill()


def render_png(spec: dict, dur: float, meta: dict, cfg: dict, size: tuple[int, int], t: float, out: Path) -> None:
    r = make_renderer(spec, dur, meta, cfg, size)
    r.frame(t).write_to_png(str(out))
