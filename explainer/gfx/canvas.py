from __future__ import annotations

import math

import cairo

from .theme import Theme


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def out_cubic(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def in_out_cubic(t):
    t = clamp(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class Motion:
    """Global animation feel, set once per renderer from `style.motion` / `style.overshoot`."""
    pace = 1.0
    overshoot = 1.4

    @classmethod
    def configure(cls, style: dict) -> None:
        cls.pace = max(0.25, float(style.get("motion", 1.0)))
        cls.overshoot = max(0.0, float(style.get("overshoot", 1.4)))


def out_back(t, s=None):
    t = clamp(t)
    s = Motion.overshoot if s is None else s
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


def out_expo(t):
    t = clamp(t)
    return 1 if t >= 1 else 1 - 2 ** (-10 * t)


def prog(t, start, dur=0.6, paced=True):
    """0..1 progress of an animation starting at `start`; durations stretch with Motion.pace."""
    if start is None:
        return 1.0
    if paced:
        dur *= Motion.pace
    return clamp((t - start) / dur) if dur > 0 else float(t >= start)


def mix(c1, c2, t):
    return tuple(lerp(a, b, t) for a, b in zip(c1, c2))


class Layout:
    """Frame regions. Sizes are in pixels; `u` scales design units (1.0 at 1080 short side)."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.portrait = h > w
        self.u = min(w, h) / 1080
        if self.portrait:
            self.mx = 80
            self.header = (self.mx, 150, w - 2 * self.mx, 300)
            self.stage = (self.mx, 490, w - 2 * self.mx, 850)
            self.caption_top = 1380
        else:
            self.mx = 110
            self.header = (self.mx, 64, w - 2 * self.mx, 150)
            self.stage = (self.mx, 236, w - 2 * self.mx, 614)
            self.caption_top = 876

    def stage_point(self, x, y):
        sx, sy, sw, sh = self.stage
        return sx + x * sw, sy + y * sh


class Painter:
    def __init__(self, ctx: cairo.Context, layout: Layout, theme: Theme):
        self.ctx, self.L, self.T = ctx, layout, theme
        self.alpha = 1.0  # global multiplier (scene enter/exit)
        self.boxes: list[tuple[str, tuple[float, float, float, float]]] = []
        self.warnings: list[str] = []
        self.record = False

    # ---- colour -------------------------------------------------------
    def rgba(self, color, a=1.0):
        r, g, b = self.T.color(color)
        self.ctx.set_source_rgba(r, g, b, clamp(a * self.alpha))

    # ---- shapes -------------------------------------------------------
    def rrect_path(self, x, y, w, h, r):
        c = self.ctx
        r = max(0, min(r, w / 2, h / 2))
        c.new_sub_path()
        c.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        c.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        c.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        c.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        c.close_path()

    def rrect(self, x, y, w, h, r, fill=None, fill_a=1.0, stroke=None, stroke_a=1.0, lw=2.0):
        self.rrect_path(x, y, w, h, r)
        self._paint(fill, fill_a, stroke, stroke_a, lw)

    def circle(self, cx, cy, r, fill=None, fill_a=1.0, stroke=None, stroke_a=1.0, lw=2.0):
        self.ctx.new_path()
        self.ctx.arc(cx, cy, max(0.1, r), 0, 2 * math.pi)
        self._paint(fill, fill_a, stroke, stroke_a, lw)

    def _paint(self, fill, fill_a, stroke, stroke_a, lw):
        c = self.ctx
        if fill is not None:
            self.rgba(fill, fill_a)
            c.fill_preserve() if stroke is not None else c.fill()
        if stroke is not None:
            self.rgba(stroke, stroke_a)
            c.set_line_width(lw)
            c.stroke()
        c.new_path()

    def glow(self, cx, cy, r, color, a=0.35):
        rr, gg, bb = self.T.color(color)
        g = cairo.RadialGradient(cx, cy, 0, cx, cy, r)
        g.add_color_stop_rgba(0, rr, gg, bb, a * self.alpha)
        g.add_color_stop_rgba(1, rr, gg, bb, 0)
        self.ctx.set_source(g)
        self.ctx.arc(cx, cy, r, 0, 2 * math.pi)
        self.ctx.fill()

    def line(self, x1, y1, x2, y2, color, a=1.0, lw=3.0, dash=None, progress=1.0):
        if progress <= 0:
            return
        c = self.ctx
        x2, y2 = lerp(x1, x2, progress), lerp(y1, y2, progress)
        c.new_path()
        c.move_to(x1, y1)
        c.line_to(x2, y2)
        c.set_line_cap(cairo.LINE_CAP_ROUND)
        if dash:
            c.set_dash(dash)
        self.rgba(color, a)
        c.set_line_width(lw)
        c.stroke()
        c.set_dash([])

    def polyline(self, pts, color, a=1.0, lw=3.0, progress=1.0, dash=None):
        """Draws the first `progress` fraction (by arc length) of a polyline."""
        if progress <= 0 or len(pts) < 2:
            return None
        seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        total = sum(seg) * clamp(progress)
        c = self.ctx
        c.new_path()
        c.move_to(*pts[0])
        end = pts[0]
        acc = 0.0
        for i, s in enumerate(seg):
            if acc + s >= total:
                f = (total - acc) / s if s else 0
                end = (lerp(pts[i][0], pts[i + 1][0], f), lerp(pts[i][1], pts[i + 1][1], f))
                c.line_to(*end)
                break
            c.line_to(*pts[i + 1])
            end = pts[i + 1]
            acc += s
        c.set_line_cap(cairo.LINE_CAP_ROUND)
        c.set_line_join(cairo.LINE_JOIN_ROUND)
        if dash:
            c.set_dash(dash)
        self.rgba(color, a)
        c.set_line_width(lw)
        c.stroke()
        c.set_dash([])
        return end

    def arrow(self, x1, y1, x2, y2, color, a=1.0, lw=4.0, progress=1.0, head=18.0, dash=None, shrink=0.0):
        if progress <= 0:
            return
        d = math.dist((x1, y1), (x2, y2))
        if d < 1:
            return
        ux, uy = (x2 - x1) / d, (y2 - y1) / d
        x1, y1 = x1 + ux * shrink, y1 + uy * shrink
        x2, y2 = x2 - ux * shrink, y2 - uy * shrink
        ex, ey = lerp(x1, x2, progress), lerp(y1, y2, progress)
        self.line(x1, y1, ex - ux * head * 0.6, ey - uy * head * 0.6, color, a, lw, dash)
        self.arrow_head(ex, ey, math.atan2(uy, ux), color, a, head)

    def arrow_head(self, x, y, ang, color, a=1.0, head=18.0):
        c = self.ctx
        c.new_path()
        c.move_to(x, y)
        c.line_to(x - head * math.cos(ang - 0.45), y - head * math.sin(ang - 0.45))
        c.line_to(x - head * 0.62 * math.cos(ang), y - head * 0.62 * math.sin(ang))
        c.line_to(x - head * math.cos(ang + 0.45), y - head * math.sin(ang + 0.45))
        c.close_path()
        self.rgba(color, a)
        c.fill()

    # ---- text ---------------------------------------------------------
    def font(self, size, weight="regular"):
        fam, bold = self.T.face(weight)
        self.ctx.select_font_face(fam, cairo.FONT_SLANT_NORMAL,
                                  cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        self.ctx.set_font_size(size)

    def text_w(self, s, size, weight="regular", tracking=0.0):
        self.font(size, weight)
        return self.ctx.text_extents(s).x_advance + tracking * size * max(0, len(s) - 1)

    def wrap(self, text, size, weight, max_w):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if not cur or self.text_w(trial, size, weight) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def fit(self, text, max_w, max_h, size, min_size=None, weight="regular", lh=1.18, max_lines=3):
        """Largest font size (<= size) whose wrapped text fits the box. Never clips: ellipsizes as last resort."""
        min_size = min_size or max(14, size * 0.5)
        s = size
        while True:
            lines = self.wrap(text, s, weight, max_w)
            widest = max((self.text_w(ln, s, weight) for ln in lines), default=0)
            if len(lines) <= max_lines and len(lines) * s * lh <= max_h + 0.5 and widest <= max_w + 0.5:
                return s, lines
            if s <= min_size:
                break
            s = max(min_size, s - max(1.0, s * 0.06))
        lines = lines[:max_lines]
        while lines and self.text_w(lines[-1] + "…", s, weight) > max_w and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        if lines:
            lines[-1] = lines[-1].rstrip(",.;:") + "…"
        self.warnings.append(f"text ellipsized: {text[:40]!r}")
        return s, lines

    def text(self, s, x, y, size, color="text", a=1.0, weight="regular", align="left", tracking=0.0,
             baseline=False, tag=None):
        """Draw one line. (x, y) is the top of the line box unless baseline=True."""
        self.font(size, weight)
        w = self.text_w(s, size, weight, tracking)
        if align == "center":
            x -= w / 2
        elif align == "right":
            x -= w
        by = y if baseline else y + size * 0.80
        self.rgba(color, a)
        c = self.ctx
        if tracking:
            cx = x
            for ch in s:
                c.move_to(cx, by)
                c.show_text(ch)
                cx += c.text_extents(ch).x_advance + tracking * size
        else:
            c.move_to(x, by)
            c.show_text(s)
        c.new_path()
        if tag and self.record and a * self.alpha > 0.9:
            x0, y0 = c.user_to_device(x, by - size * 0.80)
            x1, y1 = c.user_to_device(x + w, by + size * 0.20)
            self.boxes.append((tag, (x0, y0, x1 - x0, y1 - y0)))
        return w

    def text_block(self, text, x, y, max_w, max_h, size, color="text", a=1.0, weight="regular",
                   align="left", lh=1.18, max_lines=3, valign="top", min_size=None, tag=None):
        s, lines = self.fit(text, max_w, max_h, size, min_size, weight, lh, max_lines)
        total = len(lines) * s * lh
        oy = y + (max_h - total) / 2 if valign == "middle" else (y + max_h - total if valign == "bottom" else y)
        ax = x + max_w / 2 if align == "center" else (x + max_w if align == "right" else x)
        for i, ln in enumerate(lines):
            self.text(ln, ax, oy + i * s * lh + (lh - 1) * s * 0.5, s, color, a, weight, align, tag=tag)
        return s, total, lines

    def pill(self, text, cx, cy, size, color="accent", a=1.0, fg="bg0", weight="semibold", tag=None, pad=0.6):
        w = self.text_w(text, size, weight) + size * pad * 2
        h = size * 1.7
        self.rrect(cx - w / 2, cy - h / 2, w, h, h / 2, fill=color, fill_a=a)
        self.text(text, cx, cy - size * 0.5, size, fg, a, weight, "center", tag=tag)
        return w, h
