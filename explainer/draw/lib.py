"""Shared skia drawing helpers and the dark-navy explainer look.

Scene and art modules import this as `lib` (the bundle loader injects the alias).
Design space is always 1920×1080; the renderer may scale the finished frame.
Fonts are Poppins (OFL), vendored under explainer/fonts/Poppins/ or found on disk.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np

W, H, FPS = 1920, 1080, 30

_PKG_FONTS = Path(__file__).resolve().parent.parent / "fonts" / "Poppins"
_FONT_FILES = {
    "reg": "Poppins-Regular.ttf",
    "med": "Poppins-Medium.ttf",
    "semi": "Poppins-SemiBold.ttf",
    "bold": "Poppins-Bold.ttf",
    "it": "Poppins-Italic.ttf",
}

# palette
BG0, BG1 = (16, 28, 58), (6, 11, 26)
WHITE = (240, 244, 252)
MUTED = (150, 165, 200)
AMBER = (255, 184, 60)
ORANGE = (255, 128, 64)
CYAN = (80, 210, 255)
PINK = (255, 80, 120)
GREEN = (90, 230, 150)
GOLD = (255, 214, 102)
STONE_T, STONE_B = (226, 200, 150), (168, 132, 88)
WOOD, WOOD_L = (139, 92, 48), (196, 142, 82)

_TF = None
_bg = None


def font_dirs() -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("EXPLAINER_FONT_DIR")
    if env:
        dirs.append(Path(env).expanduser())
    dirs.append(_PKG_FONTS)
    home = Path.home()
    dirs += [
        home / "Library" / "Fonts",
        Path("/Library/Fonts"),
        Path("/opt/homebrew/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path("/usr/share/fonts/truetype/poppins"),
        Path("/usr/share/fonts/truetype/sand-box/google/Poppins"),
        Path("/usr/share/fonts/TTF"),
    ]
    return dirs


def find_font_file(name: str) -> Path:
    for d in font_dirs():
        p = d / name
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"Poppins font {name} not found. The pipeline vendors it under explainer/fonts/Poppins/, "
        f"or set EXPLAINER_FONT_DIR to a folder that contains {', '.join(_FONT_FILES.values())}."
    )


def typefaces():
    """Lazy-load skia typefaces so importing this module does not require skia until a draw happens."""
    global _TF
    if _TF is None:
        import skia
        tf = {}
        for key, name in _FONT_FILES.items():
            path = find_font_file(name)
            face = skia.Typeface.MakeFromFile(str(path))
            if face is None:
                raise RuntimeError(f"skia could not load font {path}")
            tf[key] = face
        _TF = tf
    return _TF


def reset_caches() -> None:
    """Drop cached typefaces and the background snapshot (tests / worker reuse)."""
    global _TF, _bg
    _TF = None
    _bg = None


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def prog(t, a, d):
    return clamp((t - a) / d) if d > 0 else (1.0 if t >= a else 0.0)


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def eio(x):
    x = clamp(x)
    return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def eout(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ein(x):
    x = clamp(x)
    return x * x * x


def eback(x, s=1.4):
    x = clamp(x)
    x -= 1
    return x * x * ((s + 1) * x + s) + 1


def fade(t, a, d=0.5, out=None, dout=0.5):
    v = smooth(prog(t, a, d))
    if out is not None:
        v *= 1 - smooth(prog(t, out, dout))
    return v


def lerp(a, b, u):
    return a + (b - a) * u


def lerpc(c1, c2, u):
    return tuple(lerp(a, b, u) for a, b in zip(c1, c2))


def col(c, a=1.0):
    import skia
    return skia.Color(int(c[0]), int(c[1]), int(c[2]), int(clamp(a) * 255))


def paint(c, a=1.0, stroke=None, blur=None, cap="round", join="round"):
    import skia
    p = skia.Paint(AntiAlias=True, Color=col(c, a))
    if stroke is not None:
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(stroke)
        p.setStrokeCap({"round": skia.Paint.kRound_Cap, "butt": skia.Paint.kButt_Cap}[cap])
        p.setStrokeJoin(skia.Paint.kRound_Join if join == "round" else skia.Paint.kMiter_Join)
    if blur:
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur))
    return p


def poly_path(pts, close=True):
    import skia
    p = skia.Path()
    p.moveTo(*pts[0])
    for q in pts[1:]:
        p.lineTo(*q)
    if close:
        p.close()
    return p


def polyline_path(pts):
    return poly_path(pts, close=False)


def background():
    global _bg
    if _bg is None:
        import skia
        s = skia.Surface(W, H)
        c = s.getCanvas()
        sh = skia.GradientShader.MakeRadial((W * 0.5, H * 0.38), W * 0.75, [col(BG0), col(BG1)])
        c.drawPaint(skia.Paint(Shader=sh))
        dp = paint((120, 150, 220), 0.07)
        for y in range(30, H, 60):
            for x in range(30, W, 60):
                c.drawCircle(x, y, 1.6, dp)
        vg = skia.GradientShader.MakeRadial(
            (W / 2, H / 2), W * 0.62,
            [col((0, 0, 0), 0), col((0, 0, 0), 0.0), col((0, 0, 0), 0.45)],
            [0, 0.7, 1],
        )
        c.drawPaint(skia.Paint(Shader=vg))
        _bg = s.makeImageSnapshot()
    return _bg


def font(size, w="semi"):
    import skia
    return skia.Font(typefaces()[w], size)


def text_w(s, size, w="semi"):
    return font(size, w).measureText(s)


def text(c, s, x, y, size=40, color=WHITE, a=1.0, w="semi", align="center", glow=None):
    if a <= 0.003:
        return
    f = font(size, w)
    tw = f.measureText(s)
    x0 = x - tw / 2 if align == "center" else (x - tw if align == "right" else x)
    if glow:
        c.drawString(s, x0, y, f, paint(glow, a * 0.55, blur=size * 0.25))
    c.drawString(s, x0, y, f, paint(color, a))
    return tw


def chip(c, s, x, y, size=30, color=WHITE, fill=(30, 50, 95), a=1.0, w="med", border=None, padx=24, h=None):
    if a <= 0.003:
        return
    import skia
    tw = text_w(s, size, w)
    h = h or size * 1.75
    r = skia.RRect.MakeRectXY(skia.Rect(x - tw / 2 - padx, y - h / 2, x + tw / 2 + padx, y + h / 2), h / 2, h / 2)
    c.drawRRect(r, paint(fill, a * 0.85))
    if border:
        c.drawRRect(r, paint(border, a, stroke=2.5))
    text(c, s, x, y + size * 0.36, size, color, a, w)


def wrap(s, size, maxw, w="med"):
    words = s.split()
    lines, cur = [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if text_w(t, size, w) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    if len(lines) == 2 and len(lines[1].split()) == 1 and len(lines[0].split()) > 3:
        a = lines[0].split()
        lines = [" ".join(a[:-1]), a[-1] + " " + lines[1]]
    return lines


def caption(c, s, a):
    if a <= 0.003 or not s:
        return
    import skia
    size = 44
    lines = wrap(s, size, 1500)
    lh = size * 1.32
    tw = max(text_w(l, size, "med") for l in lines)
    hgt = lh * len(lines) + 34
    ycen = 1000 if len(lines) == 1 else 980
    r = skia.RRect.MakeRectXY(
        skia.Rect(W / 2 - tw / 2 - 34, ycen - hgt / 2, W / 2 + tw / 2 + 34, ycen + hgt / 2), 22, 22
    )
    c.drawRRect(r, paint((4, 8, 20), 0.72 * a))
    y0 = ycen - hgt / 2 + 17 + size * 0.98
    for i, l in enumerate(lines):
        text(c, l, W / 2, y0 + i * lh, size, WHITE, a, "med")


def scene_chip(c, s, a):
    if a <= 0.003:
        return
    import skia
    c.drawRRect(skia.RRect.MakeRectXY(skia.Rect(70, 52, 76, 92), 3, 3), paint(AMBER, a))
    text(c, s.upper(), 92, 84, 26, (200, 212, 240), a * 0.9, "semi", "left")


def glow_path(c, path, color, width, a=1.0, glow=2.6, core=True):
    if a <= 0.003:
        return
    c.drawPath(path, paint(color, a * 0.5, stroke=width * glow, blur=width * 1.4))
    c.drawPath(path, paint(color, a, stroke=width))
    if core:
        c.drawPath(path, paint((255, 255, 255), a * 0.55, stroke=max(1, width * 0.35)))


def arrow(c, p0, p1, color, width=10, a=1.0, grow=1.0, head=None, glow=True):
    if a <= 0.003 or grow <= 0.001:
        return
    x0, y0 = p0
    x1, y1 = p1
    x1 = x0 + (x1 - x0) * grow
    y1 = y0 + (y1 - y0) * grow
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    if L < 1:
        return
    ux, uy = dx / L, dy / L
    head = head or width * 3.0
    head = min(head, L * 0.6)
    bx, by = x1 - ux * head * 0.85, y1 - uy * head * 0.85
    shaft = polyline_path([(x0, y0), (bx, by)])
    hp = poly_path([
        (x1, y1),
        (x1 - ux * head - uy * head * 0.62, y1 - uy * head + ux * head * 0.62),
        (x1 - ux * head + uy * head * 0.62, y1 - uy * head - ux * head * 0.62),
    ])
    if glow:
        c.drawPath(shaft, paint(color, a * 0.45, stroke=width * 2.6, blur=width * 1.2))
        c.drawPath(hp, paint(color, a * 0.45, blur=width * 1.2))
    c.drawPath(shaft, paint(color, a, stroke=width, cap="butt"))
    c.drawPath(hp, paint(color, a))
    c.drawPath(polyline_path([(x0, y0), (bx, by)]), paint((255, 255, 255), a * 0.4, stroke=width * 0.3))


def stone(c, pts, a=1.0, tint=None, shade=0.0, glow=0.0, glowc=AMBER, outline=(70, 52, 34)):
    if a <= 0.003:
        return
    import skia
    path = poly_path(pts)
    ys = [p[1] for p in pts]
    y0, y1 = min(ys), max(ys)
    t, b = STONE_T, STONE_B
    if tint:
        t = lerpc(t, tint[0], tint[1])
        b = lerpc(b, tint[0], tint[1])
    if shade:
        t = lerpc(t, (0, 0, 0), shade)
        b = lerpc(b, (0, 0, 0), shade)
    if glow > 0:
        c.drawPath(path, paint(glowc, a * glow * 0.8, blur=22))
    sh = skia.GradientShader.MakeLinear([(0, y0 - 1), (0, y1 + 1)], [col(t, a), col(b, a)])
    c.drawPath(path, skia.Paint(AntiAlias=True, Shader=sh))
    if glow > 0:
        c.drawPath(path, paint(glowc, a * glow * 0.35))
    c.drawPath(path, paint(outline, a * 0.9, stroke=2.2))
    c.drawPath(path, paint((255, 245, 220), a * 0.18, stroke=1.0))


def centroid(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def rot(p, ang, about):
    s, co = math.sin(ang), math.cos(ang)
    x, y = p[0] - about[0], p[1] - about[1]
    return (about[0] + x * co - y * s, about[1] + x * s + y * co)


def curve_stones(f, n, th, gap=3.0, samples=8, u0=0.0, u1=1.0, normal_sign=1, splits=None):
    N = 400
    us = np.linspace(u0, u1, N)
    P = np.array([f(u) for u in us])
    seg = np.hypot(*np.diff(P, axis=0).T)
    S = np.concatenate([[0], np.cumsum(seg)])
    L = S[-1]

    def at(s):
        i = int(np.clip(np.searchsorted(S, s) - 1, 0, N - 2))
        k = (s - S[i]) / max(seg[i], 1e-9)
        p = P[i] + (P[i + 1] - P[i]) * k
        d = (P[i + 1] - P[i]) / max(seg[i], 1e-9)
        return p, d

    bounds = splits if splits is not None else [L * i / n for i in range(n + 1)]
    polys = []
    for i in range(len(bounds) - 1):
        sa, sb = bounds[i] + gap / 2, bounds[i + 1] - gap / 2
        outer, inner = [], []
        for j in range(samples + 1):
            s = sa + (sb - sa) * j / samples
            p, d = at(s)
            nx, ny = d[1] * normal_sign, -d[0] * normal_sign
            outer.append((p[0] + nx * th / 2, p[1] + ny * th / 2))
            inner.append((p[0] - nx * th / 2, p[1] - ny * th / 2))
        polys.append(outer + inner[::-1])
    return polys, L, at


def semicircle(cx, cy, r):
    return lambda u: (cx - r * math.cos(math.pi * u), cy - r * math.sin(math.pi * u))


def partial_polyline(pts, frac):
    if frac >= 1:
        return pts
    if frac <= 0:
        return pts[:1]
    d = [0]
    for i in range(1, len(pts)):
        d.append(d[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    tgt = d[-1] * frac
    out = [pts[0]]
    for i in range(1, len(pts)):
        if d[i] <= tgt:
            out.append(pts[i])
        else:
            k = (tgt - d[i - 1]) / max(d[i] - d[i - 1], 1e-9)
            out.append((lerp(pts[i - 1][0], pts[i][0], k), lerp(pts[i - 1][1], pts[i][1], k)))
            break
    return out


def flow_dots(c, pts, t, color, speed=0.35, n=10, r=6, a=1.0):
    if a <= 0.003:
        return
    d = [0]
    for i in range(1, len(pts)):
        d.append(d[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    L = d[-1]
    for k in range(n):
        u = (t * speed + k / n) % 1.0
        s = u * L
        i = max(1, min(len(pts) - 1, int(np.searchsorted(d, s))))
        kk = (s - d[i - 1]) / max(d[i] - d[i - 1], 1e-9)
        x = lerp(pts[i - 1][0], pts[i][0], kk)
        y = lerp(pts[i - 1][1], pts[i][1], kk)
        aa = a * math.sin(math.pi * u) ** 0.7
        c.drawCircle(x, y, r * 2.4, paint(color, aa * 0.45, blur=r * 1.6))
        c.drawCircle(x, y, r, paint((255, 250, 235), aa))


def ground(c, y, x0=0, x1=W, a=1.0, color=(34, 46, 78)):
    if a <= 0.003:
        return
    import skia
    sh = skia.GradientShader.MakeLinear([(0, y), (0, y + 160)], [col(color, a), col(BG1, 0)])
    c.drawRect(skia.Rect(x0, y, x1, y + 160), skia.Paint(AntiAlias=True, Shader=sh))
    c.drawLine(x0, y, x1, y, paint((110, 140, 200), a * 0.6, stroke=2.5))


def block(c, rect, a=1.0, top=(70, 84, 120), bot=(40, 50, 80), outline=(120, 140, 190), r=6):
    if a <= 0.003:
        return
    import skia
    x0, y0, x1, y1 = rect
    sh = skia.GradientShader.MakeLinear([(0, y0), (0, y1)], [col(top, a), col(bot, a)])
    rr = skia.RRect.MakeRectXY(skia.Rect(x0, y0, x1, y1), r, r)
    c.drawRRect(rr, skia.Paint(AntiAlias=True, Shader=sh))
    c.drawRRect(rr, paint(outline, a * 0.6, stroke=2))


def leader(c, p0, p1, color, a, r=6):
    if a <= 0.003:
        return
    c.drawLine(p0[0], p0[1], p1[0], p1[1], paint(color, a * 0.85, stroke=2.5))
    c.drawCircle(p1[0], p1[1], r, paint(color, a))
