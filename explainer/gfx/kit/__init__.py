"""Drawers for the plan vocabulary. Each kind is drawn from its live parameters at time t, so the motion
(rotors turning at their rpm, current moving at the line's flow, needles following values) is the mechanism
itself rather than a canned animation."""
from __future__ import annotations

import math
import zlib

import cairo

from ..model import Actor, Presence, SceneModel, clamp, lerp


def rnd(seed: str, i: int) -> float:
    """Deterministic 0..1 noise (stable across frames and machines)."""
    return (zlib.crc32(f"{seed}:{i}".encode()) % 10007) / 10007


class Draw:
    def __init__(self, painter, theme, model: SceneModel, t: float, fps: int = 30):
        self.p, self.c, self.th, self.m, self.t, self.fps = painter, painter.ctx, theme, model, t, fps
        self.lw = theme.line

    # ---- colour ----------------------------------------------------------------------------------
    def rgb(self, color) -> tuple[float, float, float]:
        return self.th.color(color)

    def src(self, color, a: float = 1.0) -> None:
        r, g, b = self.rgb(color)
        self.c.set_source_rgba(r, g, b, clamp(a * self.p.alpha))

    def mixc(self, c1, c2, f: float) -> tuple[float, float, float]:
        a, b = self.rgb(c1), self.rgb(c2)
        return tuple(lerp(x, y, clamp(f)) for x, y in zip(a, b))

    # ---- strokes and fills -----------------------------------------------------------------------
    def stroke(self, color, a: float = 1.0, lw: float = 3.0, dash=None, cap=cairo.LINE_CAP_ROUND) -> None:
        c = self.c
        c.set_line_cap(cap)
        c.set_line_join(cairo.LINE_JOIN_ROUND)
        c.set_line_width(lw * self.lw)
        if dash:
            c.set_dash([v * self.lw for v in dash[0]], dash[1] if len(dash) > 1 else 0)
        self.src(color, a)
        c.stroke()
        c.set_dash([])

    def fill(self, color, a: float = 1.0, keep: bool = False) -> None:
        self.src(color, a)
        self.c.fill_preserve() if keep else self.c.fill()

    def poly(self, pts, close: bool = False) -> None:
        c = self.c
        c.new_path()
        if not pts:
            return
        c.move_to(*pts[0])
        for q in pts[1:]:
            c.line_to(*q)
        if close:
            c.close_path()

    def partial(self, pts, u: float) -> list:
        """The first u (0..1, by length) of a polyline."""
        if u >= 1 or len(pts) < 2:
            return list(pts)
        seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        goal, acc, out = sum(seg) * clamp(u), 0.0, [pts[0]]
        for i, s in enumerate(seg):
            if acc + s >= goal:
                f = (goal - acc) / s if s else 0
                out.append((lerp(pts[i][0], pts[i + 1][0], f), lerp(pts[i][1], pts[i + 1][1], f)))
                return out
            out.append(pts[i + 1])
            acc += s
        return out

    def line(self, pts, color, a=1.0, lw=3.0, dash=None, glow=0.0, progress=1.0) -> None:
        pts = self.partial(pts, progress)
        if len(pts) < 2:
            return
        if glow > 0:
            self.poly(pts)
            self.stroke(color, a * 0.18 * glow, lw * 3.2)
        self.poly(pts)
        self.stroke(color, a, lw, dash)

    def rrect(self, x, y, w, h, r) -> None:
        self.p.rrect_path(x, y, w, h, r * self.th.corner)

    def circle(self, x, y, r) -> None:
        self.c.new_path()
        self.c.arc(x, y, max(0.1, r), 0, 2 * math.pi)

    def glow(self, x, y, r, color, a=0.35) -> None:
        if a <= 0.003 or r <= 0:
            return
        rr, gg, bb = self.rgb(color)
        g = cairo.RadialGradient(x, y, 0, x, y, r)
        g.add_color_stop_rgba(0, rr, gg, bb, clamp(a * self.p.alpha))
        g.add_color_stop_rgba(1, rr, gg, bb, 0)
        self.c.set_source(g)
        self.circle(x, y, r)
        self.c.fill()

    def arrow_head(self, x, y, ang, color, a=1.0, size=16.0) -> None:
        self.p.arrow_head(x, y, ang, color, a, size)

    def ghosts(self, rpm: float) -> list[tuple[float, float]]:
        """(angle offset, alpha) copies that motion-blur a fast rotor instead of letting it strobe."""
        step = math.radians(abs(rpm) * 6.0 / self.fps)
        if step < math.radians(14):
            return [(0.0, 1.0)]
        n = min(7, int(step / math.radians(9)) + 1)
        sgn = 1 if rpm >= 0 else -1
        return [(-sgn * step * k / n, 1.0 if k == 0 else 0.42 * (1 - k / n)) for k in range(n)]

    def spin_angle(self, a, param: str = "rpm") -> float:
        return math.radians(a.phase(param, self.t) * 6.0 * self.m.spin)

    # ---- text --------------------------------------------------------------------------------------
    def text(self, s, x, y, size, color="ink", a=1.0, weight="medium", align="center", tag=None) -> float:
        """One line of text vertically centred on y."""
        return self.p.text(str(s), x, y - size * 0.52, size, color, a, weight, align, tag=tag)

    def tw(self, s, size, weight="medium") -> float:
        return self.p.text_w(str(s), size, weight)

    def pill(self, s, x, y, size, fg="ink", bg="surface", a=1.0, weight="semibold", tag=None, stroke=None) -> tuple:
        w = self.tw(s, size, weight) + size * 1.1
        h = size * 1.75
        self.rrect(x - w / 2, y - h / 2, w, h, h / 2)
        self.fill(bg, 0.92 * a, keep=stroke is not None)
        if stroke is not None:
            self.stroke(stroke, 0.8 * a, 1.5)
        self.text(s, x, y, size, fg, a, weight, tag=tag)
        return w, h

    def ground(self, x0, x1, y, a=0.5) -> None:
        self.poly([(x0, y), (x1, y)])
        self.stroke("muted", a, 2)


DRAWERS: dict = {}


def drawer(*kinds):
    def deco(fn):
        for k in kinds:
            DRAWERS[k] = fn
        return fn
    return deco


def fmt_value(v, decimals: int = 0) -> str:
    v = float(v or 0)
    s = f"{v:,.{int(decimals)}f}"
    return "0" if s in ("-0", "-0.0") and not decimals else s


WORLD_KINDS = {"label", "dimension", "path", "arrow", "flow", "field", "chain", "spring", "cable", "network",
               "powerline"}

from . import basic, grid, mech  # noqa: E402,F401  (registers drawers)

__all__ = ["DRAWERS", "WORLD_KINDS", "Draw", "Actor", "Presence", "rnd", "fmt_value", "drawer"]
