"""The electrical-grid kit: generation, transformation, transmission, distribution and loads."""
from __future__ import annotations

import math

from ..model import clamp, ease, lerp, poly_at, poly_len
from . import Draw, drawer, rnd
from .basic import traces
from .mech import gear_path

WOOD = "#9C7A54"
COPPER = "#D08A45"
STATE_COL = {"normal": "accent", "off": "muted", "highlight": "accent", "overload": "hot", "failed": "warn"}


def _puffs(d: Draw, x, y, seed, rate, amount, size, color="ink", drift=0.25, rise=1.0, n=7):
    if amount <= 0.02:
        return
    for i in range(n):
        age = (d.t * rate + i / n + rnd(seed, i) * 0.3) % 1.0
        px = x + age * size * 2.6 * drift * 4 + math.sin(d.t * 1.3 + i) * size * 0.15
        py = y - age * size * 4.2 * rise
        r = size * (0.35 + age * 0.9)
        d.circle(px, py, r)
        d.fill(color, 0.32 * amount * (1 - age) * min(1.0, age * 6))


def _label_below(d: Draw, a, prm, y):
    if prm.get("text"):
        d.text(prm["text"], 0, y, 24, "ink", 0.92, "semibold", tag=a.id)


# ---- generation ----------------------------------------------------------------------------------
@drawer("plant")
def plant(d: Draw, a, prm, pres):
    s = float(prm.get("size") or 220)
    out = clamp(float(prm.get("output") if prm.get("output") is not None else 0.8))
    kind = prm.get("type", "gas")
    ph = a.phase("output", d.t)
    g = s / 2
    d.ground(-0.58 * s, 0.58 * s, g, 0.6)
    lit = d.mixc("surface", "accent", 0.25 + 0.6 * out)
    if kind in ("gas", "coal", "geothermal"):
        d.rrect(-0.5 * s, -0.02 * s, 0.66 * s, 0.52 * s, 6)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.9, 2)
        for i in range(4):
            d.rrect(-0.44 * s + i * 0.15 * s, 0.08 * s, 0.1 * s, 0.07 * s, 2)
            d.fill(lit, 0.9)
        if kind == "gas":
            d.rrect(0.22 * s, -0.42 * s, 0.1 * s, 0.92 * s, 3)
            d.fill("surface", 1.0, keep=True)
            d.stroke("muted", 0.9, 2)
            for k in range(6):
                pts = []
                for j in range(14):
                    yy = -0.44 * s - j * 0.022 * s
                    pts.append((0.27 * s + math.sin(d.t * 5 + j * 0.8 + k * 1.7) * (0.012 + 0.03 * j / 14) * s
                                + (k - 2.5) * 0.012 * s, yy))
                d.line(pts, "hot", 0.22 * out, 2.5)
            d.glow(0.27 * s, -0.5 * s, 0.16 * s, "hot", 0.25 * out)
            cx, cy, r = -0.18 * s, 0.32 * s, 0.11 * s
            d.circle(cx, cy, r)
            d.fill("bg", 1.0, keep=True)
            d.stroke("muted", 0.9, 2)
            for off, al in d.ghosts(out * 300):
                ang = math.radians(ph * 1800) + off
                for i in range(8):
                    th = ang + 2 * math.pi * i / 8
                    d.poly([(cx + math.cos(th) * r * 0.2, cy + math.sin(th) * r * 0.2),
                            (cx + math.cos(th + 0.35) * r * 0.9, cy + math.sin(th + 0.35) * r * 0.9)])
                    d.stroke("accent2", al * 0.9, 2.5)
        elif kind == "coal":
            d.poly([(0.18 * s, g), (0.21 * s, -0.48 * s), (0.31 * s, -0.48 * s), (0.34 * s, g)], close=True)
            d.fill("surface", 1.0, keep=True)
            d.stroke("muted", 0.9, 2)
            d.c.new_path()
            d.c.move_to(-0.56 * s, g)
            d.c.curve_to(-0.5 * s, 0.32 * s, -0.36 * s, 0.32 * s, -0.3 * s, g)
            d.fill(d.mixc("bg", "muted", 0.35), 1.0)
            _puffs(d, 0.26 * s, -0.5 * s, a.id, 0.25 + 0.3 * out, out, 0.07 * s, "muted", drift=0.4)
        else:
            for k, x in enumerate((0.25 * s, 0.4 * s)):
                d.poly([(x, g), (x, 0.2 * s)])
                d.stroke("muted", 0.9, 5)
                _puffs(d, x, 0.2 * s, f"{a.id}{k}", 0.3 + 0.3 * out, out, 0.05 * s, "ink", drift=0.1)
    elif kind == "nuclear":
        def tower(cx, w, h):
            c = d.c
            c.new_path()
            c.move_to(cx - w / 2, g)
            c.curve_to(cx - w * 0.28, g - h * 0.55, cx - w * 0.28, g - h * 0.75, cx - w * 0.36, g - h)
            c.line_to(cx + w * 0.36, g - h)
            c.curve_to(cx + w * 0.28, g - h * 0.75, cx + w * 0.28, g - h * 0.55, cx + w / 2, g)
            c.close_path()
            d.fill("surface", 1.0, keep=True)
            d.stroke("muted", 0.9, 2)
            _puffs(d, cx, g - h - 0.02 * s, f"{a.id}{cx}", 0.18 + 0.2 * out, out, w * 0.22, "ink", drift=0.15, n=8)
        tower(-0.22 * s, 0.42 * s, 0.62 * s)
        d.rrect(0.12 * s, 0.12 * s, 0.32 * s, 0.38 * s, 4)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.9, 2)
        d.c.new_path()
        d.c.arc(0.28 * s, 0.12 * s, 0.16 * s, math.pi, 2 * math.pi)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.9, 2)
        d.glow(0.28 * s, 0.3 * s, 0.12 * s, "accent2", 0.35 * out)
    elif kind == "hydro":
        lvl = -0.12 * s
        d.poly([(-0.58 * s, lvl + math.sin(d.t * 2) * 2), (-0.12 * s, lvl), (-0.12 * s, g), (-0.58 * s, g)], close=True)
        d.fill("cold", 0.45)
        d.poly([(-0.14 * s, -0.22 * s), (0.02 * s, -0.22 * s), (0.16 * s, g), (-0.14 * s, g)], close=True)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.9, 2)
        pen = [(-0.14 * s, 0.05 * s), (0.2 * s, 0.38 * s)]
        d.line(pen, "cold", 0.5, 7)
        L = math.dist(*pen)
        for i in range(6):
            u = ((ph * 2.2 + i / 6) % 1.0)
            x, y = lerp(pen[0][0], pen[1][0], u), lerp(pen[0][1], pen[1][1], u)
            d.circle(x, y, 3.5)
            d.fill("ink", 0.8 * min(1.0, out * 2))
        cx, cy, r = 0.27 * s, 0.4 * s, 0.08 * s
        d.circle(cx, cy, r)
        d.stroke("muted", 0.9, 2)
        for off, al in d.ghosts(out * 240):
            ang = math.radians(ph * 1440) + off
            for i in range(5):
                th = ang + 2 * math.pi * i / 5
                d.poly([(cx, cy), (cx + math.cos(th) * r, cy + math.sin(th) * r)])
                d.stroke("accent2", al, 2.5)
        d.poly([(0.16 * s, 0.46 * s), (0.58 * s, 0.46 * s)])
        d.stroke("cold", 0.5, 4)
        _ = L
    elif kind == "wind":
        hub = (0.0, -0.22 * s)
        d.poly([(-0.035 * s, g), (-0.015 * s, hub[1]), (0.015 * s, hub[1]), (0.035 * s, g)], close=True)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.9, 1.5)
        d.rrect(-0.05 * s, hub[1] - 0.035 * s, 0.13 * s, 0.07 * s, 6)
        d.fill("muted", 1.0)
        for off, al in d.ghosts(out * 40):
            ang = math.radians(ph * 240) + off
            for i in range(3):
                th = ang + 2 * math.pi * i / 3
                c = d.c
                c.save()
                c.translate(*hub)
                c.rotate(th)
                c.new_path()
                c.move_to(0, -0.018 * s)
                c.curve_to(0.15 * s, -0.04 * s, 0.35 * s, -0.02 * s, 0.42 * s, 0)
                c.line_to(0, 0.018 * s)
                c.close_path()
                d.fill("ink", 0.92 * al)
                c.restore()
        d.circle(*hub, 0.025 * s)
        d.fill("ink")
    elif kind == "solar":
        for row in range(2):
            for col in range(3):
                x = -0.5 * s + col * 0.34 * s + row * 0.06 * s
                y = 0.08 * s + row * 0.2 * s
                pts = [(x, y + 0.12 * s), (x + 0.28 * s, y + 0.12 * s), (x + 0.33 * s, y), (x + 0.05 * s, y)]
                d.poly(pts, close=True)
                d.fill(d.mixc("cold", "accent", out * 0.3), 0.5 + 0.4 * out, keep=True)
                d.stroke("ink", 0.5, 1.2)
                gl = (math.sin(d.t * 1.5 + row + col) + 1) / 2
                d.glow(x + 0.18 * s, y + 0.06 * s, 0.06 * s, "ink", 0.25 * out * gl)
        d.circle(0.38 * s, -0.32 * s, 0.07 * s)
        d.fill("accent", 0.3 + 0.7 * out)
        for i in range(8):
            th = 2 * math.pi * i / 8 + d.t * 0.2
            d.poly([(0.38 * s + math.cos(th) * 0.1 * s, -0.32 * s + math.sin(th) * 0.1 * s),
                    (0.38 * s + math.cos(th) * 0.15 * s, -0.32 * s + math.sin(th) * 0.15 * s)])
            d.stroke("accent", out, 2.5)
    else:
        for k in range(3):
            x = -0.48 * s + k * 0.33 * s
            d.rrect(x, 0.12 * s, 0.28 * s, 0.38 * s, 4)
            d.fill("surface", 1.0, keep=True)
            d.stroke("muted", 0.9, 2)
            for j in range(4):
                on = (j + 1) / 4 <= out + 0.01
                d.rrect(x + 0.05 * s, 0.42 * s - j * 0.07 * s, 0.18 * s, 0.045 * s, 2)
                d.fill("good" if on else "bg", 0.95)
    _label_below(d, a, prm, g + 26)


@drawer("generator")
def generator(d: Draw, a, prm, pres):
    s = float(prm.get("size") or 300)
    R = 0.44 * s
    rpm = float(prm.get("rpm") or 0) * d.m.spin
    ang = d.spin_angle(a)
    poles = max(2, int(prm.get("poles") or 2))
    drive = clamp(abs(rpm) / 60)
    d.circle(0, 0, R)
    d.fill("surface", 1.0)
    d.circle(0, 0, R)
    d.stroke("muted", 0.9, 3)
    d.circle(0, 0, R * 0.7)
    d.stroke("muted", 0.6, 2)
    copper = d.mixc(COPPER, "muted", 0.15)
    n = 6
    for i in range(n):
        th = 2 * math.pi * i / n
        emf = abs(math.cos(poles / 2 * (ang - th)))
        c = d.c
        c.save()
        c.rotate(th)
        d.rrect(R * 0.7, -0.07 * s, R * 0.26, 0.14 * s, 4)
        d.fill("muted", 0.5)
        for k in range(5):
            x = R * 0.72 + k * R * 0.05
            d.poly([(x, -0.085 * s), (x, 0.085 * s)])
            d.stroke(copper, 1.0, 3.2)
        if drive > 0:
            d.glow(R * 0.83, 0, 0.12 * s, "accent", 0.55 * emf * drive)
        c.restore()
    r = R * 0.6
    for off, al in d.ghosts(rpm):
        c = d.c
        c.save()
        c.rotate(ang + off)
        for i in range(poles):
            a0, a1 = 2 * math.pi * i / poles, 2 * math.pi * (i + 1) / poles
            c.new_path()
            c.move_to(0, 0)
            c.arc(0, 0, r, a0, a1)
            c.close_path()
            d.fill("hot" if i % 2 == 0 else "cold", 0.92 * al)
            if al == 1.0:
                mid = (a0 + a1) / 2
                c.save()
                c.translate(math.cos(mid) * r * 0.6, math.sin(mid) * r * 0.6)
                c.rotate(-(ang + off))
                d.text("N" if i % 2 == 0 else "S", 0, 0, r * 0.32, "bg", 1.0, "bold")
                c.restore()
        c.restore()
    d.circle(0, 0, r * 0.16)
    d.fill("ink")
    d.poly([(R, 0), (0.5 * s, 0)])
    d.stroke("accent", 0.4 + 0.6 * drive, 4)
    if prm.get("show_wave"):
        w0, w1 = 0.56 * s, 1.5 * s
        amp = 0.16 * s * drive
        d.poly([(w0, 0), (w1, 0)])
        d.stroke("muted", 0.5, 1.5)
        pts = [(lerp(w0, w1, i / 120), -amp * math.sin(poles / 2 * ang - i / 120 * 4 * math.pi)) for i in range(121)]
        d.line(pts, "accent", 1.0, 4, glow=1.0)
    _label_below(d, a, prm, 0.5 * s + 26)


# ---- transformation -------------------------------------------------------------------------------
def _bushing(d: Draw, x, y0, h, w):
    discs = max(3, int(h / (w * 0.9)))
    d.poly([(x, y0), (x, y0 - h)])
    d.stroke("muted", 0.9, w * 0.35)
    for k in range(discs):
        yy = y0 - h * (k + 0.5) / discs
        d.c.save()
        d.c.translate(x, yy)
        d.c.scale(w, w * 0.3)
        d.circle(0, 0, 1)
        d.c.restore()
        d.fill("ink", 0.75)


@drawer("transformer")
def transformer(d: Draw, a, prm, pres):
    s = float(prm.get("size") or 300)
    st = prm.get("style", "cutaway")
    flux = clamp(float(prm.get("flux") if prm.get("flux") is not None else 0.8))
    fph = a.phase("flux", d.t)
    hum = flux * (0.6 + 0.4 * math.sin(d.t * 2 * math.pi * 1.2))
    if st == "cutaway":
        W, H, th = 0.86 * s, 0.62 * s, 0.13 * s
        d.rrect(-W / 2, -H / 2, W, H, 6)
        d.c.rectangle(-W / 2 + th, -H / 2 + th, W - 2 * th, H - 2 * th)
        d.c.set_fill_rule(1)
        d.fill(d.mixc("muted", "bg", 0.35))
        d.c.set_fill_rule(0)
        for k in range(1, 5):
            inset = th * k / 5
            d.rrect(-W / 2 + inset, -H / 2 + inset, W - 2 * inset, H - 2 * inset, 4)
            d.stroke("bg", 0.35, 1)
        cw = W / 2 - th / 2
        ch = H / 2 - th / 2
        loop = [(-cw, -ch), (cw, -ch), (cw, ch), (-cw, ch), (-cw, -ch)]
        if flux > 0.02:
            d.poly(loop)
            d.stroke("accent3", 0.75 * flux, 3, dash=([16, 14], -(fph * 90) % 30))
            L = poly_len(loop)
            for i in range(4):
                u = ((fph * 90 / L) + i / 4) % 1.0
                x, y = poly_at(loop, u)
                u2 = (u + 0.004) % 1.0
                x2, y2 = poly_at(loop, u2)
                d.arrow_head(x2, y2, math.atan2(y2 - y, x2 - x), "accent3", flux, 15)
        copper = d.mixc(COPPER, "accent", 0.35 * hum)

        def winding(x, turns, label, side):
            n = max(1, int(turns))
            span = H - 2 * th + 0.12 * s
            for k in range(n):
                y = -span / 2 + span * (k + 0.5) / n
                d.c.save()
                d.c.translate(x, y)
                d.c.scale(th * 0.95, max(3.0, min(14.0, span / n * 0.42)))
                d.circle(0, 0, 1)
                d.c.restore()
                d.stroke(copper, 1.0, 3.2 if n > 20 else 4.5)
            if flux > 0.02:
                d.glow(x, 0, th * 1.6, "accent", 0.25 * hum)
            lead_y = -span / 2
            d.poly([(x + side * th, lead_y), (side * s / 2, 0)])
            d.stroke(copper, 0.9, 3)
            if prm.get("show_meters", True) and label:
                d.pill(label, x, -H / 2 - 0.13 * s, max(18, 0.07 * s), "accent2" if side < 0 else "accent", "surface",
                       1.0, "bold", tag=f"{a.id}.{'in' if side < 0 else 'out'}")
        winding(-cw, prm.get("primary_turns") or 10, prm.get("v_in", ""), -1)
        winding(cw, prm.get("secondary_turns") or 4, prm.get("v_out", ""), 1)
        return
    if st == "substation":
        d.rrect(-0.3 * s, -0.12 * s, 0.6 * s, 0.52 * s, 6)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.9, 2)
        for sx in (-1, 1):
            for k in range(5):
                x = sx * (0.33 * s + k * 0.028 * s)
                d.poly([(x, -0.04 * s), (x, 0.34 * s)])
                d.stroke("muted", 0.8, 3)
        d.rrect(-0.22 * s, -0.24 * s, 0.44 * s, 0.08 * s, 0.04 * s)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.8, 1.5)
        for k, x in enumerate((-0.2 * s, -0.12 * s, 0.12 * s, 0.2 * s)):
            hv = x < 0
            _bushing(d, x, -0.12 * s, (0.16 if hv else 0.1) * s, 0.035 * s)
        d.poly([(-0.2 * s, -0.28 * s), (-0.5 * s, -0.28 * s)])
        d.stroke(COPPER, 0.9, 2.5)
        d.poly([(0.2 * s, -0.22 * s), (0.36 * s, -0.28 * s), (0.5 * s, -0.28 * s)])
        d.stroke(COPPER, 0.9, 2.5)
        d.glow(0, 0.14 * s, 0.3 * s, "accent", 0.32 * hum)
        if prm.get("show_meters", True):
            for x, key, col in ((-0.24 * s, "v_in", "accent2"), (0.24 * s, "v_out", "accent")):
                if prm.get(key):
                    d.pill(prm[key], x, 0.52 * s + 4, max(18, 0.1 * s), col, "surface", 1.0, "bold",
                           tag=f"{a.id}.{key}")
        return
    if st == "pole_can":
        w, h = 0.5 * s, 0.9 * s
        d.rrect(-w / 2, -h / 2 + 0.1 * s, w, h, w * 0.3)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.9, 2)
        _bushing(d, -0.12 * s, -h / 2 + 0.1 * s, 0.14 * s, 0.04 * s)
        _bushing(d, 0.12 * s, -h / 2 + 0.1 * s, 0.1 * s, 0.035 * s)
        d.glow(0, 0, 0.4 * s, "accent", 0.3 * hum)
        return
    for sx in (-1, 1):
        d.circle(sx * 0.13 * s, 0, 0.2 * s)
        d.stroke("accent" if sx > 0 else "accent2", 1.0, 4)
        d.poly([(sx * 0.33 * s, 0), (sx * 0.45 * s, 0)])
        d.stroke("muted", 0.9, 3)
    d.glow(0, 0, 0.3 * s, "accent3", 0.3 * hum)


# ---- transmission and distribution ----------------------------------------------------------------
def tower_shape(d: Draw, h: float, circuits: int = 1, col="muted", a=1.0) -> None:
    base, top = h / 2, -h / 2
    waist = top + 0.32 * h
    legs = [((-0.18 * h, base), (-0.06 * h, waist), (-0.04 * h, top + 0.06 * h), (0, top)),
            ((0.18 * h, base), (0.06 * h, waist), (0.04 * h, top + 0.06 * h), (0, top))]
    for leg in legs:
        d.poly(leg)
        d.stroke(col, a, 3)
    levels = 7
    for k in range(levels):
        f0, f1 = k / levels, (k + 1) / levels
        y0, y1 = lerp(base, waist, f0), lerp(base, waist, f1)
        x0, x1 = lerp(0.18 * h, 0.06 * h, f0), lerp(0.18 * h, 0.06 * h, f1)
        d.poly([(-x0, y0), (x1, y1)])
        d.stroke(col, 0.6 * a, 1.5)
        d.poly([(x0, y0), (-x1, y1)])
        d.stroke(col, 0.6 * a, 1.5)
    arms = [(top + 0.22 * h, 0.34 * h)] + ([(top + 0.1 * h, 0.27 * h)] if circuits >= 2 else [])
    for y, span in arms:
        d.poly([(-span, y), (span, y)])
        d.stroke(col, a, 3)
        for sx in (-1, 1):
            d.poly([(sx * 0.05 * h, y + 0.05 * h), (sx * span, y)])
            d.stroke(col, 0.7 * a, 1.8)
            ix = sx * span
            d.poly([(ix, y), (ix, y + 0.09 * h)])
            d.stroke("ink", 0.7 * a, 2)
            for j in range(3):
                d.c.save()
                d.c.translate(ix, y + 0.025 * h + j * 0.025 * h)
                d.c.scale(0.018 * h, 0.006 * h)
                d.circle(0, 0, 1)
                d.c.restore()
                d.fill("ink", 0.7 * a)


@drawer("tower")
def tower(d: Draw, a, prm, pres):
    h = float(prm.get("height") or 260)
    tower_shape(d, h, int(prm.get("circuits") or 1), prm.get("color") or "muted")
    d.ground(-0.26 * h, 0.26 * h, h / 2, 0.6)


def pole_shape(d: Draw, h: float, can: bool = False, col=None) -> None:
    top = -h / 2
    wood = d.mixc(col or WOOD, "bg", 0.12)
    d.poly([(-0.025 * h, h / 2), (-0.017 * h, top), (0.017 * h, top), (0.025 * h, h / 2)], close=True)
    d.fill(wood)
    d.rrect(-0.23 * h, top + 0.06 * h, 0.46 * h, 0.025 * h, 2)
    d.fill(wood)
    for x in (-0.2 * h, 0, 0.2 * h):
        d.rrect(x - 0.008 * h, top + 0.02 * h, 0.016 * h, 0.04 * h, 2)
        d.fill("ink", 0.75)
    if can:
        d.rrect(0.04 * h, top + 0.2 * h, 0.12 * h, 0.16 * h, 0.03 * h)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.9, 1.5)
        d.poly([(0.1 * h, top + 0.2 * h), (0.1 * h, top + 0.16 * h), (0.2 * h, top + 0.03 * h)])
        d.stroke(COPPER, 0.85, 1.6)


@drawer("pole")
def pole(d: Draw, a, prm, pres):
    h = float(prm.get("height") or 200)
    pole_shape(d, h, bool(prm.get("transformer")), prm.get("color") if prm.get("color") not in (None, "muted") else None)
    if prm.get("transformer"):
        d.glow(0.1 * h, -h / 2 + 0.28 * h, 0.12 * h, "accent", 0.18)
    d.ground(-0.12 * h, 0.12 * h, h / 2, 0.6)


@drawer("powerline")
def powerline(d: Draw, a, prm, pres):
    m, t = d.m, d.t
    p0, p1 = m.point(prm.get("from"), t, "from"), m.point(prm.get("to"), t, "to")
    pts = m.powerline_curve(prm, p0, p1)
    if len(pts) < 2:
        return
    volt = prm.get("voltage", "hv")
    n = int(prm.get("supports") or 0)
    heat = clamp(float(prm.get("heat") or 0))
    flow = clamp(float(prm.get("flow") if prm.get("flow") is not None else 0.6))
    for i in range(1, n + 1):
        kx, ky = lerp(p0[0], p1[0], i / (n + 1)), lerp(p0[1], p1[1], i / (n + 1))
        if volt == "hv":
            H = 150.0
            d.c.save()
            d.c.translate(kx + 0.34 * H, ky + 0.19 * H)
            tower_shape(d, H, 1, "muted", 0.55)
            d.c.restore()
        else:
            H = 120.0 if volt == "mv" else 90.0
            d.c.save()
            d.c.translate(kx - 0.2 * H, ky + 0.46 * H)
            pole_shape(d, H)
            d.c.restore()
    shown = d.partial(pts, pres.reveal)
    lw = {"hv": 3.4, "mv": 2.8, "lv": 2.2}.get(volt, 3)
    wire = d.mixc("muted", "hot", heat)
    if heat > 0.02:
        flick = 0.85 + 0.15 * math.sin(t * 7)
        d.poly(shown)
        d.stroke("hot", 0.16 * heat * flick, lw * 7)
        d.poly(shown)
        d.stroke("accent", 0.22 * heat * flick, lw * 3)
    if volt == "hv":
        upper = [(x, y - 12) for x, y in shown]
        d.poly(upper)
        d.stroke(wire, 0.55, lw * 0.8)
    d.poly(shown)
    d.stroke(wire, 1.0, lw)
    L = poly_len(pts)
    if flow > 0.01:
        gap = 64.0
        off = a.phase("flow", t) * 260
        for i in range(int(L / gap) + 1):
            s = (i * gap + off) % L
            u = s / L
            if u > pres.reveal:
                continue
            x, y = poly_at(pts, u)
            al = min(1.0, flow * 2.5) * min(1.0, s / 40, (L - s) / 40)
            d.glow(x, y, 11, "accent", 0.5 * al)
            d.circle(x, y, 2.6)
            d.fill("ink", al)
    traces(d, a, pts, lw=lw * 1.6)
    if prm.get("text") and pres.reveal > 0.5:
        mx, my = poly_at(pts, 0.5)
        d.pill(prm["text"], mx, my - 34, 22, "ink", "surface", 1.0, "semibold", tag=a.id, stroke="muted")


def _state_color(state: str) -> str:
    return STATE_COL.get(state, "accent")


def _switch_flash(d: Draw, x, y, since, size):
    if since is None or not 0 <= since <= 0.45:
        return
    k = 1 - since / 0.45
    d.glow(x, y, size * 2.2, "ink", 0.8 * k)
    d.glow(x, y, size * 1.2, "accent", 0.9 * k)
    for i in range(5):
        th = 2 * math.pi * rnd(f"{x}{y}", i) + since * 4
        pts = [(x, y)]
        for j in range(1, 4):
            r = size * 0.5 * j
            pts.append((x + math.cos(th + (rnd("j", i * 7 + j) - 0.5) * 0.9) * r,
                        y + math.sin(th + (rnd("k", i * 5 + j) - 0.5) * 0.9) * r))
        d.poly(pts)
        d.stroke("ink", k, 2)


@drawer("substation")
def substation(d: Draw, a, prm, pres):
    s = float(prm.get("size") or 280)
    state = prm.get("state", "normal")
    since_t, _prev = a.track("state").changed_at(d.t)
    since = d.t - since_t if since_t is not None else None
    col = _state_color(state)
    pulse = 0.5 + 0.5 * math.sin(d.t * 6) if state in ("overload", "highlight") else 1.0
    dim = 0.4 if state == "off" else 1.0
    x0, y0, w, h = -0.5 * s, -0.36 * s, s, 0.72 * s
    d.rrect(x0, y0 + 0.1 * s, w, h - 0.1 * s, 4)
    d.fill("surface", 0.5)
    for k in range(13):
        x = x0 + w * k / 12
        d.poly([(x, y0 + 0.1 * s), (x, y0 + h)])
        d.stroke("muted", 0.55, 2)
    d.rrect(x0, y0 + 0.1 * s, w, h - 0.1 * s, 4)
    d.stroke("muted", 0.7, 1.5, dash=([4, 4],))
    bus_y = -0.12 * s
    for sx in (-1, 1):
        gx = sx * 0.42 * s
        d.poly([(gx, 0.36 * s), (gx, -0.2 * s)])
        d.stroke("muted", 0.9, 3)
    if state == "highlight":
        d.glow(0, bus_y, 0.5 * s, "accent", 0.25 * pulse)
    if state == "overload":
        d.glow(0, bus_y, 0.45 * s, "hot", 0.35 * pulse)
    d.poly([(-0.5 * s, bus_y), (0.5 * s, bus_y)])
    d.stroke(col, dim * (0.9 if state != "highlight" else 0.7 + 0.3 * pulse), 4)
    n = max(1, int(prm.get("breakers") or 3))
    for i in range(n):
        bx = lerp(-0.28 * s, 0.28 * s, (i + 0.5) / n) if n > 1 else 0
        d.poly([(bx, bus_y), (bx, -0.02 * s)])
        d.stroke(col, dim * 0.8, 2.5)
        d.rrect(bx - 0.035 * s, -0.02 * s, 0.07 * s, 0.08 * s, 3)
        d.fill("bg", 1.0, keep=True)
        d.stroke("muted", 0.9, 1.5)
        opened = state in ("failed", "off")
        ang = -0.7 * (ease("spring", since / 0.3) if (since is not None and opened and since < 0.3) else (1 if opened else 0))
        px, py = bx - 0.022 * s, 0.045 * s
        L = 0.044 * s
        d.poly([(px, py), (px + math.cos(ang) * L, py + math.sin(ang) * L)])
        d.stroke("warn" if opened else "good", 1.0, 2.5)
        if state == "failed":
            _switch_flash(d, bx, 0.02 * s, since, 0.05 * s)
    d.rrect(-0.12 * s, 0.12 * s, 0.24 * s, 0.16 * s, 4)
    d.fill("surface", 1.0, keep=True)
    d.stroke("muted", 0.9, 1.5)
    for k in range(4):
        x = -0.1 * s + k * 0.065 * s
        d.poly([(x, 0.14 * s), (x, 0.26 * s)])
        d.stroke("muted", 0.6, 2)
    d.glow(0, 0.2 * s, 0.14 * s, "accent", 0.3 * dim)
    d.poly([(0, bus_y), (0, 0.12 * s)])
    d.stroke(col, dim * 0.7, 2)
    if state == "failed":
        _puffs(d, 0, 0.06 * s, a.id, 0.4, 1.0, 0.04 * s, "muted", drift=0.1)
    _label_below(d, a, prm, 0.36 * s + 26)


@drawer("breaker")
def breaker(d: Draw, a, prm, pres):
    s = float(prm.get("size") or 90)
    state = prm.get("state", "closed")
    since_t, _ = a.track("state").changed_at(d.t)
    since = d.t - since_t if since_t is not None else None
    opened = state == "open"
    d.rrect(-0.5 * s, -0.3 * s, s, 0.6 * s, 0.1 * s)
    d.fill("surface", 1.0, keep=True)
    d.stroke("warn" if opened else "muted", 0.9, 2)
    for sx in (-1, 1):
        d.poly([(sx * 0.5 * s, 0), (sx * 0.25 * s, 0)])
        d.stroke("ink", 0.9, 3)
        d.circle(sx * 0.25 * s, 0, 0.05 * s)
        d.fill("ink")
    if since is not None and since < 0.35:
        f = ease("spring", since / 0.35)
        ang = -math.radians(40) * (f if opened else 1 - f)
    else:
        ang = -math.radians(40) if opened else 0.0
    L = 0.5 * s
    tip = (-0.25 * s + math.cos(ang) * L, math.sin(ang) * L)
    d.poly([(-0.25 * s, 0), tip])
    d.stroke("warn" if opened else "good", 1.0, max(3, 0.06 * s))
    if opened:
        _switch_flash(d, 0.25 * s, 0, since, 0.18 * s)
    _label_below(d, a, prm, 0.3 * s + 22)


@drawer("battery")
def battery(d: Draw, a, prm, pres):
    s = float(prm.get("size") or 140)
    ch = clamp(float(prm.get("charge") if prm.get("charge") is not None else 0.6))
    fl = clamp(float(prm.get("flow") or 0), -1, 1)
    w, h = 1.1 * s, 0.7 * s
    x0 = -0.6 * s
    d.rrect(x0, -h / 2, w, h, 0.1 * s)
    d.fill("surface", 1.0, keep=True)
    d.stroke("muted", 0.9, 2.5)
    d.rrect(x0 + w, -0.12 * s, 0.08 * s, 0.24 * s, 3)
    d.fill("muted")
    col = "warn" if ch < 0.15 else "good"
    inner = w - 0.1 * s
    d.rrect(x0 + 0.05 * s, -h / 2 + 0.05 * s, max(0.5, inner * ch), h - 0.1 * s, 0.06 * s)
    d.fill(col, 0.85)
    for k in range(1, 5):
        x = x0 + 0.05 * s + inner * k / 5
        d.poly([(x, -h / 2 + 0.05 * s), (x, h / 2 - 0.05 * s)])
        d.stroke("bg", 0.6, 2)
    d.text(f"{round(ch * 100)}%", x0 + w / 2, 0, max(16, 0.2 * s), "ink", 1.0, "bold", tag=a.id)
    if abs(fl) > 0.03:
        sgn = 1 if fl < 0 else -1
        off = (d.t * 1.6 * abs(fl)) % 1.0
        for i in range(3):
            u = (i / 3 + off) % 1.0
            x = x0 + w + 0.12 * s + u * 0.35 * s if sgn > 0 else x0 + w + 0.47 * s - u * 0.35 * s
            d.arrow_head(x, 0, 0 if sgn > 0 else math.pi, "accent", abs(fl) * min(1.0, u * 4, (1 - u) * 4), 0.13 * s)


# ---- loads ----------------------------------------------------------------------------------------
def _window(d: Draw, x, y, w, h, on: float, warm="accent"):
    d.rrect(x, y, w, h, 2)
    d.fill(d.mixc("bg", warm, 0.15 + 0.75 * on), 1.0)
    if on > 0.05:
        d.glow(x + w / 2, y + h / 2, max(w, h) * 1.3, warm, 0.28 * on)


@drawer("house")
def house(d: Draw, a, prm, pres):
    s = float(prm.get("size") or 120)
    lights = clamp(float(prm.get("lights") if prm.get("lights") is not None else 0.8))
    load = clamp(float(prm.get("load") or 0))
    style = prm.get("style", "house")
    g = s / 2
    d.ground(-0.55 * s, 0.55 * s, g, 0.6)

    def lit(i):
        th = 0.15 + 0.8 * rnd(a.id, i)
        return clamp((lights - th) * 6 + (1 if lights >= 0.999 else 0))
    if style == "apartment":
        d.rrect(-0.3 * s, -0.5 * s, 0.6 * s, s, 4)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.9, 2)
        k = 0
        for row in range(6):
            for col in range(3):
                _window(d, -0.22 * s + col * 0.16 * s, -0.42 * s + row * 0.145 * s, 0.11 * s, 0.09 * s, lit(k))
                k += 1
    elif style == "shop":
        d.rrect(-0.42 * s, -0.1 * s, 0.84 * s, 0.6 * s, 4)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.9, 2)
        for i in range(6):
            d.c.rectangle(-0.42 * s + i * 0.14 * s, -0.1 * s, 0.14 * s, 0.1 * s)
            d.fill("accent" if i % 2 == 0 else "ink", 0.85)
        _window(d, -0.34 * s, 0.08 * s, 0.4 * s, 0.26 * s, lit(0))
    else:
        d.rrect(-0.38 * s, -0.06 * s, 0.76 * s, 0.56 * s, 3)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.9, 2)
        d.poly([(-0.47 * s, -0.04 * s), (0, -0.44 * s), (0.47 * s, -0.04 * s)], close=True)
        d.fill(d.mixc("surface", "muted", 0.35), 1.0, keep=True)
        d.stroke("muted", 0.9, 2)
        d.rrect(0.18 * s, -0.38 * s, 0.08 * s, 0.16 * s, 1)
        d.fill(d.mixc("surface", "muted", 0.35))
        d.rrect(-0.06 * s, 0.24 * s, 0.13 * s, 0.26 * s, 2)
        d.fill(d.mixc("bg", "muted", 0.3))
        wins = [(-0.3 * s, 0.06 * s), (0.14 * s, 0.06 * s), (-0.06 * s, -0.24 * s)]
        for i, (wx, wy) in enumerate(wins):
            ww, wh = (0.16 * s, 0.14 * s) if i < 2 else (0.12 * s, 0.1 * s)
            _window(d, wx, wy, ww, wh, max(lit(i), load * 0.9 if i == 0 else 0))
        if load > 0.02:
            kx, ky = -0.22 * s, 0.17 * s
            d.c.new_path()
            d.c.move_to(kx - 0.04 * s, ky + 0.025 * s)
            d.c.line_to(kx - 0.03 * s, ky - 0.03 * s)
            d.c.line_to(kx + 0.03 * s, ky - 0.03 * s)
            d.c.line_to(kx + 0.04 * s, ky + 0.025 * s)
            d.c.close_path()
            d.fill("bg", 0.9 * min(1.0, load * 3))
            _puffs(d, kx, ky - 0.08 * s, a.id, 0.5, load, 0.035 * s, "ink", drift=0.05, rise=0.8, n=5)
            d.glow(kx, ky, 0.12 * s, "hot", 0.45 * load)
    ix, iy = -0.42 * s, -0.12 * s
    if style == "house":
        d.poly([(ix, iy), (ix + 0.06 * s, -0.04 * s)])
        d.stroke("muted", 0.9, 2)
        d.circle(ix, iy, 3)
        d.fill("ink", 0.8)


@drawer("city")
def city(d: Draw, a, prm, pres):
    w, h = float(prm.get("w") or 420), float(prm.get("h") or 240)
    lights = clamp(float(prm.get("lights") if prm.get("lights") is not None else 0.8))
    n = max(3, int(prm.get("buildings") or 12))
    g = h / 2
    d.glow(0, g, w * 0.55, "accent", 0.18 * lights)
    x = -w / 2
    bw_avg = w / n
    k = 0
    for i in range(n):
        bw = bw_avg * (0.75 + 0.5 * rnd(a.id, i))
        if x + bw > w / 2:
            bw = w / 2 - x
        if bw < 8:
            break
        bh = h * (0.35 + 0.65 * rnd(a.id, i + 100))
        d.c.rectangle(x + 2, g - bh, bw - 4, bh)
        d.fill("surface", 1.0, keep=True)
        d.stroke("muted", 0.7, 1.2)
        cols = max(1, int((bw - 10) / 14))
        rows = max(1, int((bh - 14) / 18))
        for r in range(rows):
            for c in range(cols):
                th = rnd(a.id, k + 1000)
                on = clamp((lights - th) * 8 + (1 if lights >= 0.999 else 0))
                wx = x + 6 + c * (bw - 12) / cols
                wy = g - bh + 8 + r * 18
                d.c.rectangle(wx, wy, max(3, (bw - 12) / cols - 5), 9)
                d.fill(d.mixc("bg", "accent", 0.12 + 0.8 * on), 1.0)
                k += 1
        x += bw
    d.ground(-w / 2 - 10, w / 2 + 10, g, 0.6)


@drawer("factory")
def factory(d: Draw, a, prm, pres):
    s = float(prm.get("size") or 220)
    load = clamp(float(prm.get("load") if prm.get("load") is not None else 0.6))
    g = s / 2
    d.ground(-0.55 * s, 0.55 * s, g, 0.6)
    pts = [(-0.45 * s, g), (-0.45 * s, -0.05 * s)]
    for i in range(4):
        x = -0.45 * s + i * 0.18 * s
        pts += [(x + 0.18 * s, -0.17 * s), (x + 0.18 * s, -0.05 * s)]
    pts += [(0.27 * s, g)]
    d.poly(pts, close=True)
    d.fill("surface", 1.0, keep=True)
    d.stroke("muted", 0.9, 2)
    d.poly([(0.3 * s, g), (0.32 * s, -0.42 * s), (0.4 * s, -0.42 * s), (0.42 * s, g)], close=True)
    d.fill("surface", 1.0, keep=True)
    d.stroke("muted", 0.9, 2)
    _puffs(d, 0.36 * s, -0.44 * s, a.id, 0.25 + 0.35 * load, load, 0.06 * s, "muted", drift=0.3)
    for i in range(3):
        _window(d, -0.4 * s + i * 0.2 * s, 0.05 * s, 0.13 * s, 0.1 * s, load)
    d.c.save()
    d.c.translate(-0.12 * s, 0.32 * s)
    d.c.rotate(math.radians(a.phase("load", d.t) * 400))
    gear_path(d, 10, 0.1 * s)
    d.fill("accent2", 0.4 + 0.6 * load)
    d.c.restore()
    off = (a.phase("load", d.t) * 0.8) % 1.0
    for i in range(5):
        u = (i / 5 + off) % 1.0
        d.rrect(0.0 + u * 0.24 * s, 0.4 * s, 0.03 * s, 0.03 * s, 2)
        d.fill("ink", 0.7 * load)


# ---- schematic network ----------------------------------------------------------------------------
NODE_COL = {"plant": "accent", "substation": "accent2", "battery": "good", "hub": "accent2", "switch": "ink"}


def _node_glyph(d: Draw, kind: str, x, y, r, col, a=1.0):
    c = d.c
    if kind == "plant":
        d.circle(x, y, r)
        d.fill("surface", a, keep=True)
        d.stroke(col, a, 2.5)
        d.line([(x - r * 0.6 + r * 1.2 * i / 16, y - r * 0.32 * math.sin(2 * math.pi * i / 16)) for i in range(17)],
               col, a, 2.5)
    elif kind == "substation":
        d.rrect(x - r, y - r * 0.8, r * 2, r * 1.6, 3)
        d.fill("surface", a, keep=True)
        d.stroke(col, a, 2)
        d.poly([(x - r * 0.7, y - r * 0.2), (x + r * 0.7, y - r * 0.2)])
        d.stroke(col, a, 2.5)
        d.poly([(x, y - r * 0.2), (x, y + r * 0.5)])
        d.stroke(col, a, 2)
    elif kind in ("city", "factory"):
        hs = (0.9, 1.5, 1.1) if kind == "city" else (0.9, 0.9, 1.6)
        for i, hh in enumerate(hs):
            bx = x - r + i * r * 0.68
            c.rectangle(bx, y + r * 0.8 - r * hh, r * 0.6, r * hh)
            d.fill("surface", a, keep=True)
            d.stroke(col, a, 1.8)
            if kind == "city":
                wy = y + r * 0.8 - r * hh + r * 0.2
                while wy + r * 0.2 < y + r * 0.7:
                    c.rectangle(bx + r * 0.18, wy, r * 0.24, r * 0.18)
                    d.fill("accent" if col != "muted" else "muted", a * 0.85)
                    wy += r * 0.38
    elif kind in ("house", "load"):
        d.poly([(x - r * 0.8, y + r * 0.8), (x - r * 0.8, y - r * 0.1), (x, y - r * 0.85), (x + r * 0.8, y - r * 0.1),
                (x + r * 0.8, y + r * 0.8)], close=True)
        d.fill("surface", a, keep=True)
        d.stroke(col, a, 2)
    elif kind == "battery":
        d.rrect(x - r, y - r * 0.55, r * 1.8, r * 1.1, 3)
        d.fill("surface", a, keep=True)
        d.stroke(col, a, 2)
        d.rrect(x - r * 0.85, y - r * 0.4, r * 1.0, r * 0.8, 2)
        d.fill(col, a * 0.8)
    elif kind == "switch":
        d.circle(x, y, r * 0.8)
        d.fill("surface", a, keep=True)
        d.stroke(col, a, 2)
        d.poly([(x - r * 0.5, y + r * 0.2), (x + r * 0.45, y - r * 0.35)])
        d.stroke(col, a, 2.5)
    else:
        d.circle(x, y, r * 0.75)
        d.fill("surface", a, keep=True)
        d.stroke(col, a, 2.5)


@drawer("network")
def network(d: Draw, a, prm, pres):
    m, t = d.m, d.t
    nodes = m.nodes(a)
    pos = {nid: m.network_point(a, n, t) for nid, n in nodes.items()}
    edges = [e for e in prm.get("edges") or [] if e.get("from") in pos and e.get("to") in pos]
    total = max(1, len(edges))
    for i, e in enumerate(edges):
        part = f"{e['from']}-{e['to']}"
        p, q = pos[e["from"]], pos[e["to"]]
        k = clamp(pres.reveal * total * 1.2 - i * 1.0) if pres.reveal < 1 else 1.0
        if k <= 0:
            continue
        cls = e.get("class", "hv")
        state = a.sub_value(part, "state", t)
        fl = float(a.sub_value(part, "flow", t) or 0)
        col = {"hv": "accent", "mv": "accent", "lv": "ink", "link": "muted", "pipe": "cold"}.get(cls, "accent")
        lw = {"hv": 5, "mv": 3.5, "lv": 2.4, "link": 2, "pipe": 6}.get(cls, 3)
        alpha = 0.9
        if state == "off":
            col, alpha = "muted", 0.35
        elif state == "failed":
            col = "warn"
        elif state == "overload":
            col = "hot"
            d.line([p, q], "hot", 0.3 + 0.2 * math.sin(t * 8), lw * 3, progress=k)
        elif state == "highlight":
            d.line([p, q], "accent", 0.3, lw * 3, progress=k)
        end = (lerp(p[0], q[0], k), lerp(p[1], q[1], k))
        d.poly([p, end])
        d.stroke(col, alpha, lw, dash=([8, 7],) if cls == "link" or state == "failed" else None)
        if state == "failed":
            mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
            for sx in (-1, 1):
                d.poly([(mx - 9, my - 9 * sx), (mx + 9, my + 9 * sx)])
                d.stroke("warn", 1.0, 3)
        L = math.dist(p, q)
        if abs(fl) > 0.01 and state not in ("off", "failed") and k >= 1:
            gap = 46.0
            off = a.sub_phase(part, t) * 150
            for j in range(int(L / gap) + 1):
                s = (j * gap + off) % L
                u = s / L
                x, y = lerp(p[0], q[0], u), lerp(p[1], q[1], u)
                al = min(1.0, abs(fl) * 3) * min(1.0, s / 25, (L - s) / 25)
                d.glow(x, y, 10, "accent", 0.45 * al)
                d.circle(x, y, 2.8)
                d.fill("ink", al)
        traces(d, a, [p, q], part, lw=lw)
    nlist = list(nodes.items())
    for i, (nid, n) in enumerate(nlist):
        x, y = pos[nid]
        k = clamp(pres.reveal * len(nlist) - i * 0.7) if pres.reveal < 1 else 1.0
        if k <= 0:
            continue
        state = a.sub_value(nid, "state", t)
        kind = n.get("kind", "generic")
        col = NODE_COL.get(kind, "ink")
        al = k
        if state == "off":
            al *= 0.32
        elif state == "failed":
            col = "warn"
        if state == "highlight":
            d.glow(x, y, 46, "accent", 0.45)
        if state == "overload":
            d.glow(x, y, 44, "hot", 0.35 + 0.25 * math.sin(t * 8))
        if state == "failed":
            d.circle(x, y, 30)
            d.stroke("warn", 0.6 + 0.4 * math.sin(t * 10), 2.5)
        _node_glyph(d, kind, x, y, 20, col if state != "off" else "muted", al)
        if kind in ("city", "house", "load") and state not in ("off", "failed"):
            d.glow(x, y, 30, "accent", 0.25 * k)
        if n.get("text"):
            d.text(n["text"], x, y + 40, 20, "ink" if state != "off" else "muted", 0.95 * k, "semibold", tag=f"{a.id}.{nid}")
