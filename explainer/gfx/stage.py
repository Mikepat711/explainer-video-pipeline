"""Renders one visual-plan scene: theme from the plan's style, camera, actors drawn from their live state."""
from __future__ import annotations

import math
import sys

import cairo

from ..plan.vocab import CAPTION_TOP, DESIGN_H, DESIGN_W
from .canvas import Layout, Painter
from .kit import DRAWERS, WORLD_KINDS, Draw, rnd
from .model import FULL, SceneModel, clamp, lerp, local_box
from .theme import SEMANTIC, _families, hex_rgb

DARK = {"accent2": "#3FD0FF", "accent3": "#B388FF", "warn": "#FF5D5D", "good": "#4BE08A", "hot": "#FF7A2F",
        "cold": "#5AA9FF"}
LIGHT = {"accent2": "#0077B6", "accent3": "#6D3FC0", "warn": "#D62828", "good": "#2A9D5B", "hot": "#E85D04",
         "cold": "#1D6FD8"}
TYPEFACES = {
    "geometric": ("Inter", "Avenir Next", "Helvetica Neue", "Arial", "DejaVu Sans"),
    "humanist": ("Noto Sans", "Gill Sans", "Segoe UI", "Open Sans", "DejaVu Sans"),
    "rounded": ("Nunito", "Varela Round", "Arial Rounded MT Bold", "Inter", "DejaVu Sans"),
    "mono": ("JetBrains Mono", "Menlo", "DejaVu Sans Mono", "Liberation Mono"),
    "serif": ("Georgia", "Noto Serif", "DejaVu Serif", "Liberation Serif"),
}
RISE_KINDS = {"tower", "pole", "plant", "substation", "house", "city", "factory", "generator", "transformer",
              "battery", "bars"}
READOUT_KINDS = {"meter", "text", "badge"}
READOUT_MARGIN = 18.0


def _mix(a, b, f):
    return tuple(lerp(x, y, f) for x, y in zip(a, b))


def _lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


class PlanTheme:
    """Colours, type and line feel from the plan's `style` (duck-types gfx.theme.Theme for Painter)."""

    def __init__(self, style: dict):
        pal = {k: hex_rgb(v) for k, v in (style.get("palette") or {}).items() if isinstance(v, str)}
        bg, ink = pal.get("bg", hex_rgb("#0B1220")), pal.get("ink", hex_rgb("#E8EEF7"))
        self.dark = _lum(bg) < 0.45
        extra = {k: hex_rgb(v) for k, v in (DARK if self.dark else LIGHT).items()}
        c = {**extra, "bg": bg, "ink": ink, "accent": pal.get("accent", hex_rgb("#FFB627")),
             "surface": _mix(bg, ink, 0.09), "muted": _mix(ink, bg, 0.45)}
        c.update(pal)
        c.update({"text": c["ink"], "bg0": c["bg"], "bg1": _mix(c["bg"], c["ink"], 0.05), "panel": c["surface"],
                  "stroke": _mix(c["ink"], c["bg"], 0.7), "dim": _mix(c["ink"], c["bg"], 0.6),
                  "grid": _mix(c["bg"], c["ink"], 0.1), "white": c["ink"]})
        self.c = c
        self.name = "plan"
        self.line = {"thin": 0.75, "regular": 1.0, "bold": 1.35}.get(style.get("line", "regular"), 1.0)
        self.corner = {"sharp": 0.2, "soft": 1.0, "round": 1.8}.get(style.get("corners", "soft"), 1.0)
        fams = _families()
        cands = TYPEFACES.get(style.get("typeface", "geometric"), TYPEFACES["geometric"])
        found = next((f for f in cands if f in fams), None)
        if found is None:
            found = cands[1] if sys.platform == "darwin" else cands[-1]
        self.family = found
        self.has_weights = found == "Inter" and "Inter SemiBold" in fams

    def color(self, name):
        if name is None:
            return self.c["accent"]
        if isinstance(name, (list, tuple)):
            return tuple(name)
        if name in self.c:
            return self.c[name]
        if isinstance(name, str) and name.startswith("#") and len(name) == 7:
            return hex_rgb(name)
        if name in SEMANTIC:
            return hex_rgb(SEMANTIC[name])
        return self.c["accent"]

    def face(self, weight: str):
        if self.has_weights:
            return {"regular": ("Inter", False), "medium": ("Inter Medium", False),
                    "semibold": ("Inter SemiBold", False), "bold": ("Inter", True)}.get(weight, ("Inter", False))
        return self.family, weight in ("semibold", "bold")


def _backdrop(L: Layout, T: PlanTheme, kind: str) -> cairo.ImageSurface:
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, L.w, L.h)
    c = cairo.Context(surf)
    bg = T.c["bg"]
    c.set_source_rgb(*bg)
    c.paint()
    if kind in ("gradient", "night", "blueprint", "dots"):
        top = _mix(bg, T.c["ink"], 0.06 if kind == "gradient" else 0.03)
        g = cairo.LinearGradient(0, 0, 0, L.h)
        g.add_color_stop_rgb(0, *top)
        g.add_color_stop_rgb(1, *bg)
        c.set_source(g)
        c.paint()
    if kind == "night":
        glow = _mix(bg, T.c.get("accent2", T.c["accent"]), 0.10)
        r = cairo.RadialGradient(L.w * 0.5, L.h * 0.42, 0, L.w * 0.5, L.h * 0.42, max(L.w, L.h) * 0.7)
        r.add_color_stop_rgba(0, *glow, 1)
        r.add_color_stop_rgba(1, *glow, 0)
        c.set_source(r)
        c.paint()
        for i in range(70):
            x, y = rnd("star", i) * L.w, rnd("star", i + 999) * L.h * 0.8
            c.arc(x, y, 0.6 + 1.1 * rnd("s", i), 0, 2 * math.pi)
            c.set_source_rgba(*T.c["ink"], 0.05 + 0.12 * rnd("a", i))
            c.fill()
    if kind == "paper":
        for i in range(2400):
            x, y = rnd("p", i) * L.w, rnd("q", i) * L.h
            c.rectangle(x, y, 1.5, 1.5)
            c.set_source_rgba(*T.c["ink"], 0.025 + 0.03 * rnd("r", i))
            c.fill()
    v = cairo.RadialGradient(L.w / 2, L.h / 2, min(L.w, L.h) * 0.45, L.w / 2, L.h / 2, max(L.w, L.h) * 0.8)
    v.add_color_stop_rgba(0, 0, 0, 0, 0)
    v.add_color_stop_rgba(1, 0, 0, 0, 0.38 if T.dark else 0.07)
    c.set_source(v)
    c.paint()
    return surf


def _world_pattern(T: PlanTheme, kind: str):
    if kind not in ("blueprint", "dots", "night"):
        return None
    step = 200 if kind == "blueprint" else 40
    tile = cairo.ImageSurface(cairo.FORMAT_ARGB32, step, step)
    c = cairo.Context(tile)
    g = T.c["grid"]
    if kind == "blueprint":
        c.set_source_rgba(*g, 0.55)
        for k in range(0, step, 40):
            c.rectangle(k, 0, 1, step)
            c.rectangle(0, k, step, 1)
        c.fill()
        c.set_source_rgba(*_mix(T.c["bg"], T.c["ink"], 0.2), 0.7)
        c.rectangle(0, 0, 1.6, step)
        c.rectangle(0, 0, step, 1.6)
        c.fill()
    else:
        c.set_source_rgba(*g, 0.9 if kind == "dots" else 0.45)
        c.arc(step / 2, step / 2, 1.6, 0, 2 * math.pi)
        c.fill()
    pat = cairo.SurfacePattern(tile)
    pat.set_extend(cairo.EXTEND_REPEAT)
    return pat


class PlanRenderer:
    def __init__(self, spec: dict, dur: float, meta: dict, cfg: dict, size: tuple[int, int]):
        self.spec, self.dur, self.meta = spec, dur, meta
        self.L = Layout(*size)
        self.fps = int(cfg.get("video", {}).get("fps", 30))
        if self.L.portrait:
            self.L.caption_top = round(size[1] * 1380 / 1920)
        else:
            self.L.caption_top = round(size[1] * CAPTION_TOP / DESIGN_H)
        style = spec.get("style") or {}
        scene = spec["scene"]
        self.T = PlanTheme(style)
        self.model = SceneModel(scene, style, spec.get("base"), spec.get("camera0"), spec.get("spin"))
        bgk = scene.get("background") or style.get("background", "solid")
        bgk = "solid" if bgk == "none" else bgk
        self.bg = _backdrop(self.L, self.T, bgk)
        self.pattern = _world_pattern(self.T, bgk)
        self.focus = scene.get("portrait_focus")
        self.surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.L.w, self.L.h)
        self.ctx = cairo.Context(self.surf)
        self.ctx.set_antialias(cairo.ANTIALIAS_BEST)
        fo = cairo.FontOptions()
        fo.set_antialias(cairo.ANTIALIAS_GRAY)
        fo.set_hint_style(cairo.HINT_STYLE_SLIGHT)
        self.ctx.set_font_options(fo)
        self.painter = Painter(self.ctx, self.L, self.T)
        self.order = sorted(self.model.actors.values(), key=lambda a: (a.z, a.order))

    # ---- camera ----------------------------------------------------------------------------------
    def region(self, t: float):
        cam = self.model.camera(t)
        if self.L.portrait and self.focus:
            if cam[2] * cam[3] >= self.focus[2] * self.focus[3] or tuple(cam) == FULL:
                return tuple(self.focus)
        return cam

    def view(self, t: float):
        x, y, w, h = self.region(t)
        if self.L.portrait:
            u = self.L.u
            ax, ay, aw, ah = 40 * u, 150 * u, self.L.w - 80 * u, self.L.caption_top - 190 * u
        else:
            ax, ay, aw, ah = 0, 0, self.L.w, self.L.h
        k = min(aw / max(w, 1), ah / max(h, 1))
        return k, ax + (aw - w * k) / 2 - x * k, ay + (ah - h * k) / 2 - y * k

    # ---- frame -----------------------------------------------------------------------------------
    def frame(self, t: float) -> cairo.ImageSurface:
        c = self.ctx
        c.identity_matrix()
        c.set_source_surface(self.bg, 0, 0)
        c.paint()
        k, tx, ty = self.view(t)
        self.model.view = (-tx / k, -ty / k, (self.L.w - tx) / k, (self.L.caption_top - ty) / k)
        self.model.screen = (-tx / k, -ty / k, (self.L.w - tx) / k, (self.L.h - ty) / k)
        c.save()
        c.translate(tx, ty)
        c.scale(k, k)
        if self.pattern is not None:
            c.set_source(self.pattern)
            c.paint()
        for a in self.order:
            self._actor(a, t)
        c.restore()
        self.painter.alpha = 1.0
        self.surf.flush()
        return self.surf

    def _actor(self, a, t: float) -> None:
        drawer = DRAWERS.get(a.kind)
        if drawer is None:
            return
        pres = a.presence(t)
        alpha = pres.alpha * clamp(float(a.value("opacity", t) if a.value("opacity", t) is not None else 1.0))
        if alpha <= 0.004:
            return
        m, c, p = self.model, self.ctx, self.painter
        prm = a.params(t)
        emph, ecol = a.emphasis(t)
        p.alpha = alpha
        d = Draw(p, self.T, m, t, self.fps)
        c.save()
        if pres.wipe < 1:
            x0, y0, x1, y1 = m.bounds(a, t, prm)
            c.rectangle(x0 - 30, y0 - 60, (x1 - x0 + 60) * pres.wipe, y1 - y0 + 120)
            c.clip()
        try:
            if a.kind in WORLD_KINDS:
                c.translate(pres.dx, pres.dy)
                if emph > 0.01:
                    x0, y0, x1, y1 = m.bounds(a, t, prm)
                    d.glow((x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) * 0.6 + 40, ecol or "accent",
                           0.35 * emph)
                drawer(d, a, prm, pres)
            else:
                x, y = a.position(t)
                s = float(a.value("scale", t) or 1.0) * pres.scale * (1 + 0.06 * emph)
                if a.kind in READOUT_KINDS:
                    x, y, s = self._readout(a, prm, x, y, s, t)
                    bx0, by0, bx1, by1 = local_box(a, prm)
                    p.alpha *= m.edge_fade(x + bx0 * s, y + by0 * s, x + bx1 * s, y + by1 * s)
                c.translate(x + pres.dx, y + pres.dy)
                if emph > 0.01:
                    bx0, by0, bx1, by1 = local_box(a, prm)
                    r = max(bx1 - bx0, by1 - by0) * 0.62 * s + 30
                    d.glow((bx0 + bx1) / 2 * s, (by0 + by1) / 2 * s, r, ecol or "accent", 0.4 * emph)
                c.rotate(math.radians(float(a.value("rotate", t) or 0.0)))
                c.scale(s, s)
                if pres.entering and pres.anim == "build" and pres.p < 1 and a.kind in RISE_KINDS:
                    bx0, by0, bx1, by1 = local_box(a, prm)
                    hgt = (by1 - by0 + 80) * pres.reveal
                    c.rectangle(bx0 - 400, by1 + 40 - hgt, bx1 - bx0 + 800, hgt)
                    c.clip()
                drawer(d, a, prm, pres)
        finally:
            c.restore()
            p.alpha = 1.0

    def _readout(self, a, prm, x: float, y: float, s: float, t: float):
        """Meters and text grow less than the scenery when the camera zooms in, and are nudged back inside
        the visible frame (above the caption band) when a move or camera pan would crop them."""
        k = self.view(t)[0]
        if not self.L.portrait:
            zoom = k / (self.L.w / DESIGN_W)
            if zoom > 1.05:
                s *= zoom ** -0.45
        vx0, vy0, vx1, vy1 = self.model.view
        sx0, sy0, sx1, sy1 = self.model.screen
        if not (sx0 <= x <= sx1 and sy0 <= y <= sy1):
            return x, y, s
        bx0, by0, bx1, by1 = local_box(a, prm)
        pad = READOUT_MARGIN / k
        for lo, hi, v0, v1, axis in ((bx0, bx1, vx0, vx1, 0), (by0, by1, vy0, vy1, 1)):
            p = x if axis == 0 else y
            a0, a1 = p + lo * s, p + hi * s
            shift = 0.0
            if a1 - a0 <= (v1 - v0) - 2 * pad:
                if a0 < v0 + pad:
                    shift = v0 + pad - a0
                elif a1 > v1 - pad:
                    shift = v1 - pad - a1
            if axis == 0:
                x += shift
            else:
                y += shift
        return x, y, s

    def probe(self, t: float) -> dict:
        self.painter.record = True
        self.painter.boxes = []
        self.painter.warnings = []
        self.frame(t)
        self.painter.record = False
        return {"boxes": list(self.painter.boxes), "warnings": list(dict.fromkeys(self.painter.warnings))}


__all__ = ["PlanRenderer", "PlanTheme", "DESIGN_W", "DESIGN_H"]
