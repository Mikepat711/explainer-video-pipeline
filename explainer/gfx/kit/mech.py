"""Motion and mechanism: particles, waves, rotors, coils, fields, gears, chains, springs, levers, cables."""
from __future__ import annotations

import math

from ..model import POINT_KINDS, clamp, lerp, poly_angle, poly_at, poly_len
from . import Draw, drawer
from .basic import traces


@drawer("flow")
def flow(d: Draw, a, prm, pres):
    pts = d.m.polyline(a, d.t, prm)
    if len(pts) < 2:
        return
    L = poly_len(pts)
    n = max(1, int(round(float(prm.get("particles") or 14))))
    gap = L / n
    size = float(prm.get("size") or 7)
    col = prm.get("color") or "accent"
    style = prm.get("style", "dots")
    direction = prm.get("direction", "forward")
    if direction == "alternate":
        amp = min(gap * 0.42, 10 + float(prm.get("speed") or 0) * 0.35)
        off = amp * math.sin(2 * math.pi * 0.9 * d.t)
    else:
        off = a.phase("speed", d.t) * (-1 if direction == "reverse" else 1)
    shown = pres.reveal
    for i in range(n + 1):
        s = (i * gap + off) % L if direction != "alternate" else i * gap + gap / 2 + off
        if not 0 <= s <= L:
            continue
        u = s / L
        if u > shown:
            continue
        edge = min(1.0, s / (gap * 0.8), (L - s) / (gap * 0.8)) if direction != "alternate" else 1.0
        x, y = poly_at(pts, u)
        ang = poly_angle(pts, u) + (math.pi if direction == "reverse" else 0)
        alpha = clamp(edge)
        if style == "dashes":
            dx, dy = math.cos(ang) * size * 1.6, math.sin(ang) * size * 1.6
            d.poly([(x - dx, y - dy), (x + dx, y + dy)])
            d.stroke(col, alpha * 0.9, size * 0.55)
        elif style == "arrows":
            d.arrow_head(x + math.cos(ang) * size * 0.6, y + math.sin(ang) * size * 0.6, ang, col, alpha, size * 1.5)
        elif style == "packets":
            d.c.save()
            d.c.translate(x, y)
            d.c.rotate(ang)
            d.rrect(-size, -size * 0.6, size * 2, size * 1.2, size * 0.3)
            d.fill(col, alpha)
            d.c.restore()
        elif style == "pulses":
            d.glow(x, y, size * 3.2, col, 0.5 * alpha)
            d.circle(x, y, size * 0.7)
            d.fill(col, alpha)
        else:
            d.glow(x, y, size * 2.4, col, 0.32 * alpha)
            d.circle(x, y, size / 2)
            d.fill(col, alpha)


WAVES = {
    "sine": lambda x: math.sin(x),
    "square": lambda x: 1.0 if math.sin(x) >= 0 else -1.0,
    "sawtooth": lambda x: 2 * ((x / (2 * math.pi)) % 1) - 1,
    "triangle": lambda x: 2 * abs(2 * ((x / (2 * math.pi)) % 1) - 1) - 1,
}


@drawer("wave")
def wave(d: Draw, a, prm, pres):
    w, h = float(prm.get("w") or 420), float(prm.get("h") or 150)
    col = prm.get("color") or "accent"
    if prm.get("axis", True):
        d.poly([(-w / 2, 0), (w / 2, 0)])
        d.stroke("muted", 0.55, 1.5)
        d.poly([(-w / 2, -h / 2), (-w / 2, h / 2)])
        d.stroke("muted", 0.4, 1.5)
    fn = WAVES.get(prm.get("waveform", "sine"), WAVES["sine"])
    cycles = float(prm.get("cycles") or 3)
    amp = clamp(float(prm.get("amplitude") if prm.get("amplitude") is not None else 0.8))
    ph = 2 * math.pi * (a.phase("speed", d.t) + float(prm.get("phase") or 0) / 360)
    n = 220
    pts = [(-w / 2 + w * i / n, -amp * h / 2 * 0.92 * fn(2 * math.pi * cycles * i / n - ph)) for i in range(n + 1)]
    d.line(pts, col, 1.0, 4, glow=1.0, progress=pres.reveal)
    if amp > 0.02:
        x, y = pts[0]
        d.glow(x, y, 22, col, 0.5)
        d.circle(x, y, 6)
        d.fill(col)
    if prm.get("text"):
        d.text(prm["text"], -w / 2 + 8, -h / 2 - 22, 22, "muted", 1.0, "semibold", "left", tag=a.id)


def _angle(a, d: Draw, param: str = "rpm") -> float:
    return d.spin_angle(a, param)


@drawer("rotor")
def rotor(d: Draw, a, prm, pres):
    r = float(prm.get("radius") or 80)
    col = prm.get("color") or "accent"
    base_ang = _angle(a, d)
    rpm = float(prm.get("rpm") or 0) * d.m.spin
    style = prm.get("style", "turbine")
    c = d.c
    d.circle(0, 0, r * 1.04)
    d.fill("surface", 0.55)
    for off, gal in reversed(d.ghosts(rpm)):
        d.p.alpha *= gal
        _rotor_body(d, prm, r, col, style, base_ang + off)
        d.p.alpha /= gal
    d.circle(0, 0, max(5, r * 0.16))
    d.fill("ink", 0.95)
    d.circle(0, 0, max(2, r * 0.06))
    d.fill("bg")


def _rotor_body(d: Draw, prm, r, col, style, ang):
    c = d.c
    c.save()
    c.rotate(ang)
    if style == "magnet":
        poles = max(2, int(prm.get("poles") or 2))
        for i in range(poles):
            a0, a1 = 2 * math.pi * i / poles, 2 * math.pi * (i + 1) / poles
            c.new_path()
            c.move_to(0, 0)
            c.arc(0, 0, r, a0, a1)
            c.close_path()
            d.fill("hot" if i % 2 == 0 else "cold", 0.92)
            mid = (a0 + a1) / 2
            c.save()
            c.translate(math.cos(mid) * r * 0.58, math.sin(mid) * r * 0.58)
            c.rotate(-ang)
            d.text("N" if i % 2 == 0 else "S", 0, 0, max(14, r * 0.34), "bg", 1.0, "bold")
            c.restore()
        d.circle(0, 0, r)
        d.stroke("ink", 0.5, 2)
    elif style == "wheel":
        d.circle(0, 0, r)
        d.stroke(col, 1.0, max(4, r * 0.14))
        for i in range(8):
            th = 2 * math.pi * i / 8
            d.poly([(0, 0), (math.cos(th) * r * 0.92, math.sin(th) * r * 0.92)])
            d.stroke(col, 0.75, max(2, r * 0.05))
        d.circle(r * 0.86, 0, max(3, r * 0.07))
        d.fill("ink", 0.9)
    elif style == "fan":
        for i in range(4):
            c.save()
            c.rotate(2 * math.pi * i / 4)
            c.new_path()
            c.move_to(r * 0.12, -r * 0.05)
            c.curve_to(r * 0.5, -r * 0.42, r * 0.95, -r * 0.3, r * 0.95, 0)
            c.curve_to(r * 0.9, r * 0.2, r * 0.5, r * 0.18, r * 0.12, r * 0.05)
            c.close_path()
            d.fill(col, 0.9)
            c.restore()
    elif style == "propeller":
        for i in range(3):
            c.save()
            c.rotate(2 * math.pi * i / 3)
            c.new_path()
            c.move_to(0, -r * 0.06)
            c.curve_to(r * 0.4, -r * 0.18, r * 0.9, -r * 0.1, r, 0)
            c.curve_to(r * 0.9, r * 0.08, r * 0.4, r * 0.1, 0, r * 0.06)
            c.close_path()
            d.fill(col, 0.95)
            c.restore()
    else:
        n = 14
        for i in range(n):
            c.save()
            c.rotate(2 * math.pi * i / n)
            c.new_path()
            c.move_to(r * 0.28, -r * 0.03)
            c.curve_to(r * 0.55, -r * 0.18, r * 0.8, -r * 0.16, r * 0.97, -r * 0.05)
            c.line_to(r * 0.97, r * 0.04)
            c.curve_to(r * 0.78, -r * 0.04, r * 0.55, -r * 0.03, r * 0.28, r * 0.06)
            c.close_path()
            d.fill(col, 0.88)
            c.restore()
        d.circle(0, 0, r)
        d.stroke(col, 0.35, 2)
    c.restore()


@drawer("coil")
def coil(d: Draw, a, prm, pres):
    turns = max(1, int(prm.get("turns") or 8))
    L, r = float(prm.get("length") or 220), float(prm.get("radius") or 50)
    cur = float(prm.get("current") or 0)
    col = prm.get("color") or "accent2"
    c = d.c
    c.save()
    if prm.get("orientation") == "vertical":
        c.rotate(math.pi / 2)
    d.rrect(-L / 2 - 14, -r * 0.45, L + 28, r * 0.9, 6)
    d.fill("muted", 0.35)
    hot = d.mixc(col, "hot", clamp(abs(cur)))
    pitch = L / turns
    for i in range(turns):
        x = -L / 2 + pitch * (i + 0.5)
        c.save()
        c.translate(x, 0)
        c.scale(pitch * 0.42, r)
        c.new_path()
        c.arc(0, 0, 1, -math.pi / 2, math.pi / 2)
        c.restore()
        d.stroke("muted", 0.5, 4)
    for i in range(turns):
        x = -L / 2 + pitch * (i + 0.5)
        c.save()
        c.translate(x, 0)
        c.scale(pitch * 0.42, r)
        c.new_path()
        c.arc(0, 0, 1, math.pi / 2, 3 * math.pi / 2)
        c.restore()
        if abs(cur) > 0.05:
            c.save()
            c.translate(x, 0)
            c.scale(pitch * 0.42, r)
            c.new_path()
            c.arc(0, 0, 1, math.pi / 2, 3 * math.pi / 2)
            c.restore()
            d.stroke(hot, 0.25 * abs(cur), 12)
            c.save()
            c.translate(x, 0)
            c.scale(pitch * 0.42, r)
            c.new_path()
            c.arc(0, 0, 1, math.pi / 2, 3 * math.pi / 2)
            c.restore()
        d.stroke(hot, 1.0, 5)
    for sx in (-1, 1):
        d.poly([(sx * L / 2, r), (sx * (L / 2 + 30), r)])
        d.stroke(hot, 1.0, 4)
    if abs(cur) > 0.05:
        off = (a.phase("current", d.t) * 120) % pitch
        for i in range(turns):
            x = -L / 2 + pitch * i + off
            if -L / 2 < x < L / 2:
                d.arrow_head(x, -r - 2, 0 if cur > 0 else math.pi, hot, abs(cur), 12)
    c.restore()
    if prm.get("text"):
        d.text(prm["text"], 0, r + 36, 22, "muted", 1.0, "semibold", tag=a.id)


@drawer("field")
def field(d: Draw, a, prm, pres):
    around = prm.get("around")
    tid = str(around).partition(".")[0] if isinstance(around, str) else None
    ta = d.m.actors.get(tid) if tid else None
    strength = clamp(float(prm.get("strength") if prm.get("strength") is not None else 0.8))
    if strength <= 0.01:
        return
    col = prm.get("color") or "accent"
    rad = float(prm.get("radius") or 160) * float(a.value("scale", d.t) or 1)
    n = max(2, int(prm.get("lines") or 6))
    style = prm.get("style", "magnetic")
    flowoff = (d.t * 40) % 24
    if ta is not None and (ta.kind in POINT_KINDS or ta.kind in ("powerline", "arrow")) and "." not in str(around):
        pts = d.m.polyline(ta, d.t)
        if len(pts) < 2:
            return
        for i in range(n):
            u = (i + 0.5) / n
            x, y = poly_at(pts, u)
            ang = poly_angle(pts, u)
            nx, ny = -math.sin(ang), math.cos(ang)
            k = clamp(pres.reveal * n - i * 0.6)
            if style == "magnetic":
                d.c.save()
                d.c.translate(x, y)
                d.c.rotate(ang)
                d.c.scale(rad * 0.18, rad)
                d.c.new_path()
                d.c.arc(0, 0, 1, 0, 2 * math.pi)
                d.c.restore()
                d.stroke(col, 0.55 * strength * k, 2.2, dash=([10, 8], -flowoff))
            else:
                for sgn in (-1, 1):
                    x1, y1 = x + nx * 18 * sgn, y + ny * 18 * sgn
                    x2, y2 = x + nx * rad * sgn, y + ny * rad * sgn
                    d.poly([(x1, y1), (x2, y2)])
                    d.stroke(col, 0.6 * strength * k, 2.2, dash=([12, 9], -flowoff) if style != "electric" else None)
                    if style == "electric":
                        d.arrow_head(x2, y2, math.atan2(y2 - y1, x2 - x1), col, 0.8 * strength * k, 13)
        return
    cx, cy = d.m.point(around, d.t)
    if style == "magnetic":
        for i in range(1, n // 2 + 1):
            f = i / (n // 2 + 0.5)
            for sgn in (-1, 1):
                d.c.save()
                d.c.translate(cx + sgn * rad * f * 0.5, cy)
                d.c.scale(rad * f * 0.5, rad * f * 0.8)
                d.c.new_path()
                d.c.arc(0, 0, 1, 0, 2 * math.pi)
                d.c.restore()
                d.stroke(col, 0.55 * strength * pres.reveal, 2.2, dash=([10, 8], -flowoff * sgn))
    elif style == "heat":
        for i in range(n):
            x = cx + (i - (n - 1) / 2) * rad * 1.4 / n
            pts = [(x + 8 * math.sin(d.t * 3 + k * 0.5 + i), cy - k * rad / 12) for k in range(13)]
            d.line(pts, col, 0.5 * strength * pres.reveal, 2.5)
    else:
        for i in range(n):
            th = 2 * math.pi * i / n
            r0 = rad * 0.25
            x1, y1 = cx + math.cos(th) * r0, cy + math.sin(th) * r0
            x2, y2 = cx + math.cos(th) * rad, cy + math.sin(th) * rad
            d.poly([(x1, y1), (x2, y2)])
            d.stroke(col, 0.6 * strength * pres.reveal, 2.2, dash=([12, 9], -flowoff) if style == "radial" else None)
            if style == "electric":
                d.arrow_head(x2, y2, th, col, 0.8 * strength, 13)


def gear_path(d: Draw, teeth: int, r: float) -> None:
    depth = min(r * 0.18, 2 * math.pi * r / teeth * 0.45)
    ro, ri = r, r - depth
    c = d.c
    c.new_path()
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a0 = i * step
        for frac, rad in ((0.0, ri), (0.15, ro), (0.5, ro), (0.65, ri)):
            ang = a0 + frac * step
            (c.move_to if i == 0 and frac == 0 else c.line_to)(math.cos(ang) * rad, math.sin(ang) * rad)
    c.close_path()


@drawer("gear")
def gear(d: Draw, a, prm, pres):
    teeth = max(6, int(prm.get("teeth") or 20))
    r = float(prm.get("radius") or 60)
    col = prm.get("color") or "muted"
    c = d.c
    c.save()
    c.rotate(_angle(a, d) + math.pi / teeth * (a.order % 2))
    gear_path(d, teeth, r)
    d.fill(d.mixc(col, "bg", 0.35), 1.0, keep=True)
    d.stroke(col, 1.0, 2.5)
    spokes = int(prm.get("spokes") if prm.get("spokes") is not None else 5)
    if spokes and r > 30:
        d.circle(0, 0, r * 0.66)
        d.stroke(col, 0.9, 2)
        for i in range(spokes):
            th = 2 * math.pi * i / spokes
            d.poly([(math.cos(th) * r * 0.2, math.sin(th) * r * 0.2), (math.cos(th) * r * 0.66, math.sin(th) * r * 0.66)])
            d.stroke(col, 0.9, max(3, r * 0.08))
    c.restore()
    d.circle(0, 0, max(4, r * 0.16))
    d.fill("ink", 0.9)


@drawer("chain")
def chain(d: Draw, a, prm, pres):
    pts = d.m.polyline(a, d.t, prm)
    if len(pts) < 3:
        return
    col = prm.get("color") or "muted"
    d.line(d.partial(pts, pres.reveal), d.mixc(col, "bg", 0.3), 1.0, 9)
    L = poly_len(pts)
    pitch = 16.0
    off = a.phase("speed", d.t) % pitch
    n = int(L / pitch)
    for i in range(n):
        u = ((i * pitch + off) % L) / L
        if u > pres.reveal:
            continue
        x, y = poly_at(pts, u)
        ang = poly_angle(pts, u)
        dx, dy = math.cos(ang) * pitch * 0.32, math.sin(ang) * pitch * 0.32
        d.poly([(x - dx, y - dy), (x + dx, y + dy)])
        d.stroke("ink" if i % 2 else col, 0.95, 5)


@drawer("spring")
def spring(d: Draw, a, prm, pres):
    p0, p1 = d.m.point(prm.get("from"), d.t, "from"), d.m.point(prm.get("to"), d.t, "to")
    comp = clamp(float(prm.get("compression") or 0), 0, 0.9)
    end = (lerp(p0[0], p1[0], 1 - comp), lerp(p0[1], p1[1], 1 - comp))
    L = math.dist(p0, end) or 1
    ux, uy = (end[0] - p0[0]) / L, (end[1] - p0[1]) / L
    nx, ny = -uy, ux
    coils = max(3, int(prm.get("coils") or 10))
    amp = 16
    pts = [p0]
    lead = L * 0.08
    pts.append((p0[0] + ux * lead, p0[1] + uy * lead))
    for i in range(coils * 2):
        f = lead + (L - 2 * lead) * (i + 0.5) / (coils * 2)
        s = amp * (1 if i % 2 == 0 else -1)
        pts.append((p0[0] + ux * f + nx * s, p0[1] + uy * f + ny * s))
    pts += [(end[0] - ux * lead, end[1] - uy * lead), end]
    col = prm.get("color") or "muted"
    d.line(pts, d.mixc(col, "hot", comp * 0.8), 1.0, 4, progress=pres.reveal)


@drawer("lever")
def lever(d: Draw, a, prm, pres):
    L = float(prm.get("length") or 100)
    w = float(prm.get("width") or 16)
    ang = math.radians(float(prm.get("angle") or 0))
    col = prm.get("color") or "muted"
    d.c.save()
    d.c.rotate(ang)
    d.rrect(-w / 2, -w / 2, L * pres.reveal + w, w, w / 2)
    d.fill(d.mixc(col, "bg", 0.2), 1.0, keep=True)
    d.stroke("ink", 0.4, 1.5)
    d.circle(L, 0, w * 0.45)
    d.fill("ink", 0.8)
    d.c.restore()
    d.circle(0, 0, w * 0.75)
    d.fill("surface", 1.0, keep=True)
    d.stroke("ink", 0.9, 2)


@drawer("cable")
def cable(d: Draw, a, prm, pres):
    pts = d.m.polyline(a, d.t, prm)
    if len(pts) < 2:
        return
    ten = clamp(float(prm.get("tension") if prm.get("tension") is not None else 0.5))
    col = d.mixc(prm.get("color") or "muted", "accent", max(0.0, ten - 0.5) * 2)
    w = float(prm.get("width") or 5)
    d.line(pts, col, 1.0, w, glow=max(0.0, ten - 0.6) * 2.5, progress=pres.reveal)
    traces(d, a, pts, lw=w)
