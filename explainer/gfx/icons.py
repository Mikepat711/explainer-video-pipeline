"""Procedural line icons drawn in a unit box centred on (cx, cy) with edge length `s`."""
from __future__ import annotations

import math

import cairo

from .canvas import Painter


def _stroke(p: Painter, color, a, lw):
    c = p.ctx
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    c.set_line_join(cairo.LINE_JOIN_ROUND)
    p.rgba(color, a)
    c.set_line_width(lw)
    c.stroke()


def draw_icon(p: Painter, name: str, cx: float, cy: float, s: float, color="text", a=1.0, t: float = 0.0):
    c = p.ctx
    lw = max(1.5, s * 0.07)
    fn = ICONS.get(name, ICONS["spark"])
    c.save()
    c.translate(cx, cy)
    c.scale(s / 100, s / 100)
    c.new_path()
    fn(p, c, color, a, lw * 100 / s, t)
    c.restore()
    c.new_path()


def _satellite(p, c, col, a, lw, t):
    c.rectangle(-14, -14, 28, 28)
    _stroke(p, col, a, lw)
    for sx in (-1, 1):
        x0 = 20 if sx > 0 else -48
        c.rectangle(x0, -12, 28, 24)
        _stroke(p, col, a, lw)
        c.move_to(x0 + 14, -12)
        c.line_to(x0 + 14, 12)
        _stroke(p, col, a * 0.7, lw * 0.6)
        c.move_to(14 * sx, 0)
        c.line_to(20 * sx, 0)
        _stroke(p, col, a, lw)
    c.move_to(0, 14)
    c.line_to(0, 26)
    _stroke(p, col, a, lw)
    c.arc(0, 34, 8, math.pi * 1.1, math.pi * 1.9)
    _stroke(p, col, a, lw)


def _signal(p, c, col, a, lw, t):
    c.arc(0, 20, 5, 0, 2 * math.pi)
    p.rgba(col, a)
    c.fill()
    for i, r in enumerate((18, 32, 46)):
        ph = (t * 1.2 - i * 0.25) % 1.0
        c.arc(0, 20, r, math.pi * 1.25, math.pi * 1.75)
        _stroke(p, col, a * (0.45 + 0.55 * (1 - ph)), lw)


def _clock(p, c, col, a, lw, t):
    c.arc(0, 0, 40, 0, 2 * math.pi)
    _stroke(p, col, a, lw)
    ang = t * 2.0
    c.move_to(0, 0)
    c.line_to(22 * math.sin(ang), -22 * math.cos(ang))
    _stroke(p, col, a, lw)
    c.move_to(0, 0)
    c.line_to(0, -30)
    _stroke(p, col, a, lw * 0.8)
    for k in range(12):
        an = k / 12 * 2 * math.pi
        c.move_to(34 * math.sin(an), -34 * math.cos(an))
        c.line_to(38 * math.sin(an), -38 * math.cos(an))
    _stroke(p, col, a * 0.7, lw * 0.5)


def _flame(p, c, col, a, lw, t):
    w = 1 + 0.04 * math.sin(t * 9)
    c.move_to(0, 44)
    c.curve_to(-34 * w, 40, -38 * w, 6, -16, -16)
    c.curve_to(-10, -2, -4, -2, -2, 4)
    c.curve_to(0, -20, 6, -34, 4, -46)
    c.curve_to(26 * w, -30, 40 * w, 0, 32, 22)
    c.curve_to(26, 38, 14, 44, 0, 44)
    _stroke(p, col, a, lw)
    c.move_to(0, 40)
    c.curve_to(-14, 36, -14, 18, 0, 8)
    c.curve_to(14, 18, 14, 36, 0, 40)
    _stroke(p, col, a * 0.8, lw * 0.8)


def _snowflake(p, c, col, a, lw, t):
    for k in range(6):
        an = k * math.pi / 3 + t * 0.2
        dx, dy = math.cos(an), math.sin(an)
        c.move_to(0, 0)
        c.line_to(42 * dx, 42 * dy)
        for d in (22, 32):
            px, py = d * dx, d * dy
            for sgn in (-1, 1):
                a2 = an + sgn * 0.7
                c.move_to(px, py)
                c.line_to(px + 11 * math.cos(a2), py + 11 * math.sin(a2))
    _stroke(p, col, a, lw)


def _bolt(p, c, col, a, lw, t):
    c.move_to(8, -46)
    c.line_to(-24, 6)
    c.line_to(-2, 6)
    c.line_to(-10, 46)
    c.line_to(24, -8)
    c.line_to(2, -8)
    c.close_path()
    _stroke(p, col, a, lw)


def _house(p, c, col, a, lw, t):
    c.move_to(-42, -2)
    c.line_to(0, -40)
    c.line_to(42, -2)
    _stroke(p, col, a, lw)
    c.move_to(-32, -10)
    c.line_to(-32, 40)
    c.line_to(32, 40)
    c.line_to(32, -10)
    _stroke(p, col, a, lw)
    c.rectangle(-10, 14, 20, 26)
    _stroke(p, col, a * 0.8, lw * 0.8)


def _phone(p, c, col, a, lw, t):
    p.rrect_path(-24, -44, 48, 88, 10)
    _stroke(p, col, a, lw)
    c.move_to(-8, 34)
    c.line_to(8, 34)
    _stroke(p, col, a, lw)
    c.arc(0, -6, 12, 0, 2 * math.pi)
    _stroke(p, col, a * 0.8, lw * 0.7)
    c.arc(0, -6, 3, 0, 2 * math.pi)
    p.rgba(col, a)
    c.fill()


def _drop(p, c, col, a, lw, t):
    c.move_to(0, -44)
    c.curve_to(10, -26, 34, -4, 34, 14)
    c.curve_to(34, 34, 18, 44, 0, 44)
    c.curve_to(-18, 44, -34, 34, -34, 14)
    c.curve_to(-34, -4, -10, -26, 0, -44)
    _stroke(p, col, a, lw)


def _cloud(p, c, col, a, lw, t):
    c.move_to(-30, 26)
    c.curve_to(-50, 26, -50, -4, -28, -4)
    c.curve_to(-26, -30, 12, -34, 16, -10)
    c.curve_to(40, -16, 50, 26, 30, 26)
    c.close_path()
    _stroke(p, col, a, lw)


def _fan(p, c, col, a, lw, t):
    c.arc(0, 0, 44, 0, 2 * math.pi)
    _stroke(p, col, a * 0.6, lw * 0.7)
    for k in range(3):
        an = t * 5 + k * 2 * math.pi / 3
        c.save()
        c.rotate(an)
        c.move_to(0, 0)
        c.curve_to(10, -12, 30, -18, 34, -4)
        c.curve_to(30, 6, 12, 6, 0, 0)
        _stroke(p, col, a, lw)
        c.restore()
    c.arc(0, 0, 5, 0, 2 * math.pi)
    p.rgba(col, a)
    c.fill()


def _sun(p, c, col, a, lw, t):
    c.arc(0, 0, 18, 0, 2 * math.pi)
    _stroke(p, col, a, lw)
    for k in range(8):
        an = k * math.pi / 4 + t * 0.3
        c.move_to(28 * math.cos(an), 28 * math.sin(an))
        c.line_to(42 * math.cos(an), 42 * math.sin(an))
    _stroke(p, col, a, lw)


def _thermometer(p, c, col, a, lw, t):
    c.move_to(-9, 20)
    c.line_to(-9, -36)
    c.arc(0, -36, 9, math.pi, 0)
    c.line_to(9, 20)
    c.arc(0, 30, 15, -math.pi / 2 + 0.93, math.pi * 1.5 - 0.93)
    _stroke(p, col, a, lw)
    c.arc(0, 30, 8, 0, 2 * math.pi)
    p.rgba(col, a)
    c.fill()
    lvl = -10 - 16 * (0.5 + 0.5 * math.sin(t * 1.5))
    c.rectangle(-3, lvl, 6, 30 - lvl)
    c.fill()


def _gauge(p, c, col, a, lw, t):
    c.arc(0, 8, 40, math.pi, 2 * math.pi)
    _stroke(p, col, a, lw)
    an = math.pi + (0.3 + 0.4 * (0.5 + 0.5 * math.sin(t))) * math.pi
    c.move_to(0, 8)
    c.line_to(32 * math.cos(an), 8 + 32 * math.sin(an))
    _stroke(p, col, a, lw)
    c.move_to(-44, 8)
    c.line_to(44, 8)
    _stroke(p, col, a * 0.7, lw * 0.7)


def _gear(p, c, col, a, lw, t):
    c.save()
    c.rotate(t * 0.8)
    n = 8
    for k in range(n * 2):
        an = k * math.pi / n
        r = 40 if k % 2 == 0 else 30
        an2 = an + math.pi / n
        if k == 0:
            c.move_to(r * math.cos(an), r * math.sin(an))
        c.line_to(r * math.cos(an), r * math.sin(an))
        c.line_to(r * math.cos(an2 - 0.12), r * math.sin(an2 - 0.12))
    c.close_path()
    _stroke(p, col, a, lw)
    c.arc(0, 0, 12, 0, 2 * math.pi)
    _stroke(p, col, a, lw)
    c.restore()


def _chip(p, c, col, a, lw, t):
    p.rrect_path(-26, -26, 52, 52, 6)
    _stroke(p, col, a, lw)
    c.rectangle(-12, -12, 24, 24)
    _stroke(p, col, a * 0.7, lw * 0.7)
    for k in (-14, 0, 14):
        for sx, sy, ex, ey in ((k, -26, k, -40), (k, 26, k, 40), (-26, k, -40, k), (26, k, 40, k)):
            c.move_to(sx, sy)
            c.line_to(ex, ey)
    _stroke(p, col, a, lw * 0.8)


def _globe(p, c, col, a, lw, t):
    c.arc(0, 0, 42, 0, 2 * math.pi)
    _stroke(p, col, a, lw)
    for k in (-1, 1):
        c.save()
        c.scale(abs(math.cos(t * 0.6 + k * 0.8)) * 0.9 + 0.1, 1)
        c.arc(0, 0, 42, 0, 2 * math.pi)
        c.restore()
        _stroke(p, col, a * 0.6, lw * 0.7)
    for y in (-20, 0, 20):
        hw = math.sqrt(42 ** 2 - y ** 2)
        c.move_to(-hw, y)
        c.line_to(hw, y)
    _stroke(p, col, a * 0.6, lw * 0.7)


def _pin(p, c, col, a, lw, t):
    bob = 3 * math.sin(t * 3)
    c.move_to(0, 44 + bob * 0)
    c.curve_to(-8, 26, -32, 6, -32, -14)
    c.arc(0, -14, 32, math.pi, 2 * math.pi)
    c.curve_to(32, 6, 8, 26, 0, 44)
    _stroke(p, col, a, lw)
    c.arc(0, -14, 11, 0, 2 * math.pi)
    _stroke(p, col, a, lw)


def _spark(p, c, col, a, lw, t):
    c.move_to(0, -44)
    c.curve_to(4, -10, 10, -4, 44, 0)
    c.curve_to(10, 4, 4, 10, 0, 44)
    c.curve_to(-4, 10, -10, 4, -44, 0)
    c.curve_to(-10, -4, -4, -10, 0, -44)
    _stroke(p, col, a, lw)


def _compressor(p, c, col, a, lw, t):
    p.rrect_path(-30, -40, 60, 80, 26)
    _stroke(p, col, a, lw)
    c.move_to(-30, -8)
    c.line_to(30, -8)
    _stroke(p, col, a * 0.6, lw * 0.7)
    k = 0.5 + 0.5 * math.sin(t * 6)
    c.rectangle(-16, 2 + 10 * k, 32, 8)
    _stroke(p, col, a, lw * 0.8)
    c.move_to(0, -40)
    c.line_to(0, -50)
    c.move_to(-40, 24)
    c.line_to(-30, 24)
    _stroke(p, col, a, lw)


def _coil(p, c, col, a, lw, t):
    c.move_to(-46, -34)
    for i in range(5):
        y = -34 + i * 17
        x0, x1 = (-46, 40) if i % 2 == 0 else (40, -46)
        c.line_to(x1, y)
        if i < 4:
            c.arc(x1, y + 8.5, 8.5, -math.pi / 2, math.pi / 2) if i % 2 == 0 else \
                c.arc_negative(x1, y + 8.5, 8.5, -math.pi / 2, -3 * math.pi / 2)
    _stroke(p, col, a, lw)


def _valve(p, c, col, a, lw, t):
    c.move_to(-46, 0)
    c.line_to(-18, 0)
    c.move_to(18, 0)
    c.line_to(46, 0)
    _stroke(p, col, a, lw)
    c.move_to(-18, -18)
    c.line_to(18, 18)
    c.line_to(18, -18)
    c.line_to(-18, 18)
    c.close_path()
    _stroke(p, col, a, lw)
    c.move_to(0, 0)
    c.line_to(0, -34)
    c.move_to(-12, -34)
    c.line_to(12, -34)
    _stroke(p, col, a, lw)


def _layers(p, c, col, a, lw, t):
    for i, y in enumerate((-16, 0, 16)):
        c.move_to(0, y - 18)
        c.line_to(40, y)
        c.line_to(0, y + 18)
        c.line_to(-40, y)
        c.close_path()
        _stroke(p, col, a * (1 - i * 0.2), lw)


def _antenna(p, c, col, a, lw, t):
    c.move_to(0, -10)
    c.line_to(-22, 44)
    c.move_to(0, -10)
    c.line_to(22, 44)
    c.move_to(-12, 20)
    c.line_to(12, 20)
    _stroke(p, col, a, lw)
    c.arc(0, -18, 7, 0, 2 * math.pi)
    _stroke(p, col, a, lw)
    for r in (18, 30):
        c.arc(0, -18, r, -math.pi * 0.8, -math.pi * 0.2)
        _stroke(p, col, a * 0.7, lw * 0.8)


def _building(p, c, col, a, lw, t):
    c.rectangle(-34, -40, 36, 84)
    c.rectangle(2, -14, 32, 58)
    _stroke(p, col, a, lw)
    for y in (-28, -14, 0, 14, 28):
        c.move_to(-26, y)
        c.line_to(-6, y)
    _stroke(p, col, a * 0.6, lw * 0.7)


def _check(p, c, col, a, lw, t):
    c.arc(0, 0, 42, 0, 2 * math.pi)
    _stroke(p, col, a, lw)
    c.move_to(-18, 2)
    c.line_to(-4, 16)
    c.line_to(20, -12)
    _stroke(p, col, a, lw)


def _atom(p, c, col, a, lw, t):
    for k in range(3):
        c.save()
        c.rotate(k * math.pi / 3 + t * 0.4)
        c.scale(1, 0.36)
        c.arc(0, 0, 44, 0, 2 * math.pi)
        c.restore()
        _stroke(p, col, a, lw * 0.8)
    c.arc(0, 0, 7, 0, 2 * math.pi)
    p.rgba(col, a)
    c.fill()


def _kettle(p, c, col, a, lw, t):
    c.move_to(-26, -14)
    c.line_to(-32, 30)
    c.curve_to(-32, 36, -28, 38, -22, 38)
    c.line_to(22, 38)
    c.curve_to(28, 38, 32, 36, 32, 30)
    c.line_to(26, -14)
    c.curve_to(14, -20, -14, -20, -26, -14)
    _stroke(p, col, a, lw)
    c.move_to(-29, 8)
    c.curve_to(-40, 4, -46, -6, -48, -14)
    _stroke(p, col, a, lw)
    c.move_to(27, -6)
    c.curve_to(46, -6, 46, 26, 31, 26)
    _stroke(p, col, a, lw)
    c.move_to(-6, -19)
    c.line_to(-6, -24)
    c.line_to(6, -24)
    c.line_to(6, -19)
    _stroke(p, col, a, lw * 0.8)
    c.move_to(-36, 46)
    c.line_to(36, 46)
    _stroke(p, col, a * 0.8, lw)
    for i, x in enumerate((-50, -42)):
        ph = (t * 0.8 + i * 0.5) % 1.0
        y0 = -22 - ph * 24
        c.move_to(x, y0)
        c.curve_to(x - 6, y0 - 6, x + 6, y0 - 10, x, y0 - 16)
        _stroke(p, col, a * 0.7 * math.sin(math.pi * ph), lw * 0.6)


def _plug(p, c, col, a, lw, t):
    p.rrect_path(-24, -16, 48, 34, 8)
    _stroke(p, col, a, lw)
    for x in (-10, 10):
        c.move_to(x, -16)
        c.line_to(x, -40)
    _stroke(p, col, a, lw)
    c.move_to(0, 18)
    c.curve_to(0, 34, 18, 32, 18, 46)
    _stroke(p, col, a, lw)


ICONS = {
    "satellite": _satellite, "signal": _signal, "clock": _clock, "flame": _flame, "snowflake": _snowflake,
    "bolt": _bolt, "house": _house, "phone": _phone, "drop": _drop, "cloud": _cloud, "fan": _fan, "sun": _sun,
    "thermometer": _thermometer, "gauge": _gauge, "gear": _gear, "chip": _chip, "globe": _globe, "pin": _pin,
    "spark": _spark, "compressor": _compressor, "coil": _coil, "valve": _valve, "layers": _layers,
    "antenna": _antenna, "building": _building, "check": _check, "atom": _atom, "kettle": _kettle, "plug": _plug,
}
