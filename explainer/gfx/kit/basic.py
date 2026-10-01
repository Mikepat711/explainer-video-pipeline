"""Words, geometry and instruments."""
from __future__ import annotations

import math

from ..model import (METER_SIZES, TEXT_SIZES, balance_dims, balance_tilt, clamp, ease, lerp, poly_angle, poly_at,
                     poly_len)
from ..icons import ICONS, draw_icon
from . import Draw, drawer, fmt_value


def traces(d: Draw, a, pts, part: str = "", lw: float = 6.0) -> None:
    """A single bright pulse running along a line (the `trace` action)."""
    if len(pts) < 2:
        return
    for t0, dur, color, sub in a.traces:
        if (sub or "") != part or not (t0 <= d.t <= t0 + dur + 0.25):
            continue
        u = ease("smooth", (d.t - t0) / max(dur, 1e-3))
        fade = 1.0 if d.t <= t0 + dur else 1 - (d.t - t0 - dur) / 0.25
        col = color or "accent"
        tail = 0.22
        n = 10
        for k in range(n):
            u0, u1 = max(0.0, u - tail * (k + 1) / n), max(0.0, u - tail * k / n)
            if u1 <= 0:
                continue
            seg = [poly_at(pts, u0), poly_at(pts, (u0 + u1) / 2), poly_at(pts, u1)]
            d.poly(seg)
            d.stroke(col, fade * (1 - k / n) * 0.9, lw * (1.4 - k / n * 0.8))
        hx, hy = poly_at(pts, u)
        d.glow(hx, hy, lw * 6, col, 0.55 * fade)
        d.circle(hx, hy, lw * 0.9)
        d.fill("ink", fade)


# ---- words ---------------------------------------------------------------------------------------
@drawer("text")
def text(d: Draw, a, prm, pres):
    size = TEXT_SIZES.get(prm.get("size", "m"), 36)
    weight = {"regular": "regular", "medium": "medium", "bold": "bold"}.get(prm.get("weight", "medium"), "medium")
    lines = d.p.wrap(str(prm.get("text", "")), size, weight, float(prm.get("max_width") or 1100))
    lh = size * 1.18
    y0 = -lh * (len(lines) - 1) / 2
    align = prm.get("align", "center")
    for i, ln in enumerate(lines):
        d.text(ln, 0, y0 + i * lh, size, prm.get("color") or "ink", 1.0, weight, align, tag=a.id)


@drawer("label")
def label(d: Draw, a, prm, pres):
    m, t = d.m, d.t
    cx, cy = m.label_center(a, t, prm)
    cx, cy = cx + pres.dx, cy + pres.dy
    size = 26
    txt = str(prm.get("text", ""))
    w = d.tw(txt, size, "semibold") + size * 1.1
    h = size * 1.75
    target = prm.get("target")
    cx, cy = m.fit_view(cx, cy, w, h, anchor=m.point(target, t) if target is not None else None)
    d.p.alpha *= m.edge_fade(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    if prm.get("leader", True) and target is not None:
        tid = str(target).partition(".")[0] if isinstance(target, str) else None
        ta = m.actors.get(tid) if tid else None
        if isinstance(target, str) and "." not in target and ta is not None:
            tp = m.edge_point(ta, ta.params(t), t, (cx, cy))
        else:
            tp = m.point(target, t)
        dx, dy = tp[0] - cx, tp[1] - cy
        dist = math.hypot(dx, dy)
        if dist > max(w, h) / 2 + 12:
            f = min((w / 2 + 4) / abs(dx) if dx else 1e9, (h / 2 + 4) / abs(dy) if dy else 1e9)
            sx, sy = cx + dx * f, cy + dy * f
            prog = pres.reveal
            ex, ey = lerp(sx, tp[0], prog), lerp(sy, tp[1], prog)
            d.poly([(sx, sy), (ex, ey)])
            d.stroke(prm.get("color") or "ink", 0.55, 2)
            d.circle(ex, ey, 4.5)
            d.fill(prm.get("color") or "ink", 0.9)
    d.pill(txt, cx, cy, size, prm.get("color") or "ink", "surface", 1.0, "semibold", tag=a.id, stroke="muted")


@drawer("badge")
def badge(d: Draw, a, prm, pres):
    s = float(prm.get("size") or 46)
    col = prm.get("color") or "accent"
    d.glow(0, 0, s, col, 0.25)
    d.circle(0, 0, s / 2)
    d.fill(col)
    d.text(prm.get("text", ""), 0, 1, s * 0.5, "bg", 1.0, "bold", tag=a.id)


@drawer("dimension")
def dimension(d: Draw, a, prm, pres):
    p0, p1 = d.m.point(prm.get("from"), d.t, "from"), d.m.point(prm.get("to"), d.t, "to")
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L, dx / L
    off = float(prm.get("offset", 40))
    q0, q1 = (p0[0] + nx * off, p0[1] + ny * off), (p1[0] + nx * off, p1[1] + ny * off)
    col = prm.get("color") or "muted"
    for p, q in ((p0, q0), (p1, q1)):
        d.poly([(p[0] + nx * 8 * (1 if off > 0 else -1), p[1] + ny * 8 * (1 if off > 0 else -1)),
                (q[0] + nx * 10 * (1 if off > 0 else -1), q[1] + ny * 10 * (1 if off > 0 else -1))])
        d.stroke(col, 0.7, 1.5)
    u = pres.reveal
    mx, my = (q0[0] + q1[0]) / 2, (q0[1] + q1[1]) / 2
    a0 = (lerp(mx, q0[0], u), lerp(my, q0[1], u))
    a1 = (lerp(mx, q1[0], u), lerp(my, q1[1], u))
    d.poly([a0, a1])
    d.stroke(col, 0.9, 2)
    ang = math.atan2(dy, dx)
    d.arrow_head(a1[0], a1[1], ang, col, 0.9, 13)
    d.arrow_head(a0[0], a0[1], ang + math.pi, col, 0.9, 13)
    d.pill(prm.get("text", ""), mx + nx * 2, my + ny * 2, 24, "ink", "bg", 1.0, "semibold", tag=a.id)


# ---- geometry ------------------------------------------------------------------------------------
@drawer("shape")
def shape(d: Draw, a, prm, pres):
    sh = prm.get("shape", "rect")
    w, h, r = float(prm.get("w") or 200), float(prm.get("h") or 120), float(prm.get("r") or 60)
    fill, stroke = prm.get("fill"), prm.get("stroke")
    if fill is None and stroke is None:
        stroke = "muted"

    def path():
        c = d.c
        c.new_path()
        if sh == "rect":
            c.rectangle(-w / 2, -h / 2, w, h)
        elif sh == "rounded":
            d.rrect(-w / 2, -h / 2, w, h, min(w, h) * 0.14)
        elif sh in ("circle", "ring"):
            c.arc(0, 0, r, 0, 2 * math.pi)
        elif sh == "ellipse":
            c.save()
            c.scale(w / 2, h / 2)
            c.arc(0, 0, 1, 0, 2 * math.pi)
            c.restore()
        elif sh == "polygon" and prm.get("points"):
            d.poly([tuple(p) for p in prm["points"]], close=True)

    lvl = clamp(float(prm.get("fill_level", 1.0) if prm.get("fill_level") is not None else 1.0))
    if fill is not None and sh != "ring":
        x0, y0, x1, y1 = (-r, -r, r, r) if sh in ("circle", "ring") else (-w / 2, -h / 2, w / 2, h / 2)
        if sh == "polygon" and prm.get("points"):
            ys = [p[1] for p in prm["points"]]
            y0, y1 = min(ys), max(ys)
        d.c.save()
        if lvl < 1:
            d.c.rectangle(-4000, y1 - (y1 - y0) * lvl, 8000, 4000)
            d.c.clip()
        path()
        d.fill(fill, 0.95 if lvl >= 1 else 1.0)
        d.c.restore()
        if lvl < 1:
            path()
            d.fill(fill, 0.12)
    if stroke is not None or sh == "ring":
        path()
        sw = float(prm.get("stroke_width") or 3)
        d.stroke(stroke or fill or "muted", 1.0, sw if sh != "ring" else max(sw, r * 0.18),
                 dash=([10, 8],) if prm.get("dashed") else None)


@drawer("path")
def path(d: Draw, a, prm, pres):
    pts = d.m.polyline(a, d.t, prm)
    if len(pts) < 2:
        return
    col, lw = prm.get("color") or "muted", float(prm.get("width") or 6)
    shown = d.partial(pts, pres.reveal)
    d.line(shown, col, 1.0, lw, dash=([lw * 2.2, lw * 1.6],) if prm.get("dashed") else None)
    arrow = prm.get("arrow", "none")
    if arrow in ("end", "both") and len(shown) >= 2:
        d.arrow_head(shown[-1][0], shown[-1][1], poly_angle(shown, 1.0), col, 1.0, 10 + lw * 2.2)
    if arrow in ("start", "both"):
        d.arrow_head(pts[0][0], pts[0][1], poly_angle(pts, 0.0) + math.pi, col, 1.0, 10 + lw * 2.2)
    traces(d, a, pts, lw=lw)


@drawer("arrow")
def arrow(d: Draw, a, prm, pres):
    pts = d.m.polyline(a, d.t, prm)
    if len(pts) < 2:
        return
    col, lw = prm.get("color") or "accent", float(prm.get("width") or 6)
    head = 12 + lw * 2.2
    full = poly_len(pts)
    shown = d.partial(pts, pres.reveal * max(0.0, 1 - head * 0.55 / max(full, 1)))
    d.line(shown, col, 1.0, lw, dash=([lw * 2.2, lw * 1.6],) if prm.get("dashed") else None)
    tip = poly_at(pts, pres.reveal)
    d.arrow_head(tip[0], tip[1], poly_angle(pts, max(0.02, pres.reveal)), col, 1.0, head)
    traces(d, a, pts, lw=lw)
    if prm.get("text") and pres.reveal > 0.6:
        mx, my = poly_at(pts, 0.5)
        ang = poly_angle(pts, 0.5)
        nx, ny = -math.sin(ang), math.cos(ang)
        side = -1 if ny > 0 else 1
        d.pill(prm["text"], mx + nx * 34 * side, my + ny * 34 * side, 24, "ink", "bg", clamp((pres.reveal - 0.6) / 0.4),
               "semibold", tag=a.id)


@drawer("icon")
def icon(d: Draw, a, prm, pres):
    name = prm.get("name", "spark")
    if name in ICONS:
        draw_icon(d.p, name, 0, 0, float(prm.get("size") or 72), prm.get("color") or "accent", 1.0, d.t)


# ---- instruments ---------------------------------------------------------------------------------
def _zone_color(prm, v):
    for z in prm.get("zones") or []:
        if float(z.get("from", -1e18)) <= v <= float(z.get("to", 1e18)):
            return z.get("color") or "accent"
    return "accent"


@drawer("gauge")
def gauge(d: Draw, a, prm, pres):
    lo, hi = float(prm.get("min", 0)), float(prm.get("max", 100))
    v = float(prm.get("value", lo) or lo)
    f = clamp((v - lo) / ((hi - lo) or 1))
    r = float(prm.get("radius") or 110)
    st = prm.get("style", "dial")
    unit, dec = prm.get("unit", ""), int(prm.get("decimals") or 0)
    col = _zone_color(prm, v)
    reading = fmt_value(v, dec) + (f" {unit}" if unit else "")
    if st == "vertical":
        w, h = r * 0.34, r * 1.9
        d.rrect(-w / 2, -h / 2, w, h, w / 2)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.7, 2)
        for z in prm.get("zones") or []:
            z0 = clamp((float(z.get("from", lo)) - lo) / ((hi - lo) or 1))
            z1 = clamp((float(z.get("to", hi)) - lo) / ((hi - lo) or 1))
            d.c.rectangle(w / 2 + 6, h / 2 - h * z1, 6, h * (z1 - z0))
            d.fill(z.get("color") or "accent", 0.8)
        fh = (h - 10) * f
        d.rrect(-w / 2 + 5, h / 2 - 5 - fh, w - 10, fh, (w - 10) / 2)
        d.fill(col)
        d.text(reading, 0, h / 2 + 30, 30, "ink", 1.0, "bold", tag=a.id)
        if prm.get("text"):
            d.text(prm["text"], 0, -h / 2 - 26, 24, "muted", 1.0, "semibold", tag=f"{a.id}.label")
        return
    if st == "arc":
        a0, a1 = math.pi, 2 * math.pi
    else:
        a0, a1 = math.radians(150), math.radians(390)
    c = d.c
    c.new_path()
    c.arc(0, 0, r, a0, a1)
    d.stroke("surface", 1.0, r * 0.16, cap=0)
    # arc gauges show the value as a filled track, so zones move to a thin outer rim to keep the fill readable
    zr, zw = (r * 1.08, r * 0.045) if st == "arc" else (r, r * 0.16)
    for z in prm.get("zones") or []:
        z0 = clamp((float(z.get("from", lo)) - lo) / ((hi - lo) or 1))
        z1 = clamp((float(z.get("to", hi)) - lo) / ((hi - lo) or 1))
        c.new_path()
        c.arc(0, 0, zr, lerp(a0, a1, z0), lerp(a0, a1, z1))
        d.stroke(z.get("color") or "accent", 0.85, zw, cap=0)
    if st == "arc":
        c.new_path()
        c.arc(0, 0, r, a0, lerp(a0, a1, f))
        d.stroke(col, 0.9, r * 0.16, cap=0)
        ang = lerp(a0, a1, f)
        d.poly([(math.cos(ang) * r * 0.88, math.sin(ang) * r * 0.88), (math.cos(ang) * r * 1.13, math.sin(ang) * r * 1.13)])
        d.stroke("ink", 1.0, max(3, r * 0.035))
        d.glow(math.cos(ang) * r, math.sin(ang) * r, r * 0.16, col, 0.4)
    for i in range(11):
        ang = lerp(a0, a1, i / 10)
        r0 = r * (0.74 if i % 5 == 0 else 0.8)
        d.poly([(math.cos(ang) * r0, math.sin(ang) * r0), (math.cos(ang) * r * 0.86, math.sin(ang) * r * 0.86)])
        d.stroke("muted", 0.8, 2 if i % 5 == 0 else 1.2)
    for frac, val in ((0, lo), (1, hi)):
        ang = lerp(a0, a1, frac)
        fs = max(15, r * 0.14)
        if st == "dial":
            x, y = math.cos(ang) * r, math.sin(ang) * r + r * 0.08 + fs * 0.7
        else:
            x, y = math.cos(ang) * r, fs * 0.52 + 6
        d.text(fmt_value(val, dec), x, y, fs, "muted", 1.0, "medium")
    if st == "dial":
        ang = lerp(a0, a1, f)
        d.poly([(math.cos(ang + math.pi) * r * 0.12, math.sin(ang + math.pi) * r * 0.12),
                (math.cos(ang) * r * 0.84, math.sin(ang) * r * 0.84)])
        d.stroke(col, 1.0, max(3, r * 0.04))
        d.glow(math.cos(ang) * r * 0.8, math.sin(ang) * r * 0.8, r * 0.18, col, 0.35)
        d.circle(0, 0, r * 0.07)
        d.fill("ink")
        d.text(reading, 0, r * 0.52, max(22, r * 0.24), "ink", 1.0, "bold", tag=a.id)
        if prm.get("text"):
            fs = max(18, r * 0.16)
            d.text(prm["text"], 0, r * 0.95 + fs / 2 + 8, fs, "muted", 1.0, "semibold", tag=f"{a.id}.label")
    else:
        d.text(reading, 0, -r * 0.28, max(22, r * 0.26), "ink", 1.0, "bold", tag=a.id)
        if prm.get("text"):
            d.text(prm["text"], 0, r * 0.2, max(16, r * 0.15), "muted", 1.0, "semibold", tag=f"{a.id}.label")


@drawer("meter")
def meter(d: Draw, a, prm, pres):
    w, h, fs = METER_SIZES.get(prm.get("size", "m"), METER_SIZES["m"])
    col = prm.get("color") or "accent"
    d.rrect(-w / 2, -h / 2, w, h, h * 0.18)
    d.fill("surface", 0.95, keep=True)
    d.stroke(col, 0.55, 2)
    val = fmt_value(prm.get("value", 0), int(prm.get("decimals") or 0))
    unit = prm.get("unit", "")
    us = fs * 0.46
    vw = d.tw(val, fs, "bold")
    uw = d.tw(unit, us, "semibold") + us * 0.35 if unit else 0
    fit = min(1.0, (w - 24) / max(1.0, vw + uw))
    fs2, us2 = fs * fit, us * fit
    x0 = -(vw + uw) * fit / 2
    d.text(val, x0, 2, fs2, "ink", 1.0, "bold", align="left", tag=a.id)
    if unit:
        d.text(unit, x0 + vw * fit + us2 * 0.35, 2 + fs2 * 0.18, us2, col, 1.0, "semibold", align="left",
               tag=a.id)
    if prm.get("text"):
        d.text(prm["text"], 0, h / 2 + 18, 22, "muted", 1.0, "semibold", tag=f"{a.id}.label")


@drawer("bars")
def bars(d: Draw, a, prm, pres):
    w, h = float(prm.get("w") or 520), float(prm.get("h") or 300)
    labels = prm.get("labels") or []
    vals = [float(v) for v in (prm.get("values") or [])]
    n = max(1, len(labels))
    top = float(prm.get("max") or max(vals + [1]))
    colors = prm.get("colors") or []
    unit = prm.get("unit", "")
    hor = prm.get("orientation") == "horizontal"
    d.poly([(-w / 2, -h / 2), (-w / 2, h / 2), (w / 2, h / 2)] if not hor else [(-w / 2 + 120, -h / 2), (-w / 2 + 120, h / 2)])
    d.stroke("muted", 0.6, 2)
    for i in range(n):
        v = vals[i] if i < len(vals) else 0
        f = clamp(v / top) * pres.reveal
        col = colors[i] if i < len(colors) else ("accent" if i % 2 == 0 else "accent2")
        if hor:
            slot = h / n
            bh = slot * 0.62
            y = -h / 2 + slot * i + (slot - bh) / 2
            bw = (w - 130) * f
            d.rrect(-w / 2 + 122, y, max(bw, 0.1), bh, bh * 0.2)
            d.fill(col)
            d.text(labels[i] if i < len(labels) else "", -w / 2 + 110, y + bh / 2, 22, "ink", 1.0, "semibold", "right",
                   tag=f"{a.id}.l{i}")
            d.text(fmt_value(v) + (f" {unit}" if unit else ""), -w / 2 + 132 + bw, y + bh / 2, 22, "muted", 1.0,
                   "semibold", "left", tag=f"{a.id}.v{i}")
        else:
            slot = w / n
            bw = slot * 0.58
            x = -w / 2 + slot * i + (slot - bw) / 2
            bh = (h - 40) * f
            d.rrect(x, h / 2 - bh, bw, max(bh, 0.1), bw * 0.12)
            d.fill(col)
            d.text(labels[i] if i < len(labels) else "", x + bw / 2, h / 2 + 24, 22, "ink", 1.0, "semibold",
                   tag=f"{a.id}.l{i}")
            d.text(fmt_value(v) + (f" {unit}" if unit else ""), x + bw / 2, h / 2 - bh - 20, 22, "muted", 1.0,
                   "semibold", tag=f"{a.id}.v{i}")


@drawer("line_chart")
def line_chart(d: Draw, a, prm, pres):
    w, h = float(prm.get("w") or 640), float(prm.get("h") or 340)
    series = prm.get("series") or []
    allv = [float(v) for s in series for v in s.get("values") or []] or [0, 1]
    lo = float(prm["y_min"]) if prm.get("y_min") is not None else min(allv)
    hi = float(prm["y_max"]) if prm.get("y_max") is not None else max(allv)
    if hi - lo < 1e-9:
        hi = lo + 1
    x0, y0, x1, y1 = -w / 2 + 50, -h / 2 + 10, w / 2 - 10, h / 2 - 40
    for k in range(5):
        y = lerp(y1, y0, k / 4)
        d.poly([(x0, y), (x1, y)])
        d.stroke("muted", 0.18 if k else 0.6, 1.2 if k else 2)
    d.poly([(x0, y0), (x0, y1)])
    d.stroke("muted", 0.6, 2)
    dec = 2 if hi - lo < 1 else (1 if hi - lo < 10 else 0)
    d.text(fmt_value(hi, dec), x0 - 10, y0, 18, "muted", 1.0, "medium", "right")
    d.text(fmt_value(lo, dec), x0 - 10, y1, 18, "muted", 1.0, "medium", "right")
    ticks = prm.get("x_ticks") or []
    for i, tk in enumerate(ticks):
        x = lerp(x0, x1, i / max(1, len(ticks) - 1))
        d.text(tk, x, y1 + 22, 18, "muted", 1.0, "medium", tag=f"{a.id}.x{i}")
    if prm.get("x_label"):
        d.text(prm["x_label"], (x0 + x1) / 2, y1 + 50, 20, "muted", 1.0, "semibold", tag=f"{a.id}.xl")
    if prm.get("y_label"):
        d.text(prm["y_label"], x0 + 6, y0 - 18, 20, "muted", 1.0, "semibold", "left", tag=f"{a.id}.yl")
    prog = clamp(float(prm.get("progress", 1.0) if prm.get("progress") is not None else 1.0)) * pres.reveal
    palette = ["accent", "accent2", "accent3", "warn"]
    for si, s in enumerate(series):
        vals = [float(v) for v in s.get("values") or []]
        if len(vals) < 2:
            continue
        pts = [(lerp(x0, x1, i / (len(vals) - 1)), lerp(y1, y0, (v - lo) / (hi - lo))) for i, v in enumerate(vals)]
        col = s.get("color") or palette[si % 4]
        shown = d.partial(pts, prog)
        d.line(shown, col, 1.0, 4, glow=0.8)
        if prog > 0:
            ex, ey = shown[-1]
            d.glow(ex, ey, 26, col, 0.5)
            d.circle(ex, ey, 6.5)
            d.fill(col)
        if s.get("name") and len(series) > 1:
            d.text(s["name"], x1 - 4, y0 + 14 + 28 * si, 20, col, 1.0, "semibold", "right", tag=f"{a.id}.s{si}")


@drawer("balance")
def balance(d: Draw, a, prm, pres):
    w = float(prm.get("width") or 480)
    tilt = balance_tilt(prm)
    col = prm.get("color") or "muted"
    fh, drop, pr = balance_dims(w)
    d.poly([(0, -6), (-fh * 0.22, fh), (fh * 0.22, fh)], close=True)
    d.fill(col, 0.85)
    d.ground(-max(fh * 0.55, 60), max(fh * 0.55, 60), fh + 1, 0.7)
    c, s = math.cos(tilt), math.sin(tilt)
    ends = ((-w / 2 * c, -w / 2 * s), (w / 2 * c, w / 2 * s))
    d.poly([ends[0], ends[1]])
    d.stroke("ink", 0.9, 8)
    d.circle(0, 0, 10)
    d.fill("ink")
    for (ex, ey), key, tkey, pc in ((ends[0], "left", "left_text", "accent2"), (ends[1], "right", "right_text", "accent")):
        pan_y = ey + drop
        for sx in (-pr * 0.82, pr * 0.82):
            d.poly([(ex, ey), (ex + sx, pan_y)])
            d.stroke("muted", 0.7, 1.5)
        d.c.new_path()
        d.c.arc(ex, pan_y, pr, 0, math.pi)
        d.c.close_path()
        d.fill(pc, 0.9)
        amt = float(prm.get(key) or 0)
        tot = max(float(prm.get("left") or 0), float(prm.get("right") or 0), 1e-6)
        bh = min(w * 0.13, drop * 0.75) * clamp(amt / tot)
        d.rrect(ex - pr * 0.55, pan_y - bh, pr * 1.1, bh, 4)
        d.fill(pc, 0.55)
        if prm.get(tkey):
            d.text(prm[tkey], ex, pan_y + pr + 24, 24, "ink", 1.0, "semibold", tag=f"{a.id}.{key}")


@drawer("compare")
def compare(d: Draw, a, prm, pres):
    w = float(prm.get("w") or 900)
    cw = w / 2 - 30
    for side, sx, col in (("left", -w / 4 - 8, "accent2"), ("right", w / 4 + 8, "accent")):
        d.rrect(sx - cw / 2, -160, cw, 320, 22)
        d.fill("surface", 0.9, keep=True)
        d.stroke(col, 0.7, 2)
        d.text(prm.get(f"{side}_title", ""), sx, -118, 34, col, 1.0, "bold", tag=f"{a.id}.{side}")
        for i, item in enumerate(prm.get(f"{side}_items") or []):
            k = clamp(pres.reveal * 4 - i)
            d.circle(sx - cw / 2 + 34, -50 + i * 56, 6)
            d.fill(col, k)
            d.text(item, sx - cw / 2 + 54, -50 + i * 56, 26, "ink", k, "medium", "left", tag=f"{a.id}.{side}{i}")
    d.circle(0, 0, 30)
    d.fill("bg")
    d.text("vs", 0, 0, 26, "muted", 1.0, "bold")
