# Flat diagram art for the grid Part 4 explainer (skia). All coordinates in 1920x1080 space.
import math, skia, numpy as np
from .lib import *

HOT_A = (255, 160, 60); HOT_B = (255, 96, 86); NEUT = (236, 240, 248); GRN = (90, 220, 130)
COPPER = (214, 140, 80); STEEL = (150, 160, 178); STEEL_D = (96, 106, 124)
PANEL_L = (200, 205, 214); PANEL_D = (150, 157, 170); BRK = (50, 54, 64); HANDLE = (28, 30, 36)
HOUSE_W = (36, 52, 90); HOUSE_E = (110, 140, 200); ROOF = (60, 44, 70); LIT = (255, 214, 120)
EARTH_T, EARTH_B = (92, 66, 44), (52, 36, 26)
WATER = (80, 170, 255); RED = (255, 72, 72)

def bump(x): x = clamp(x); return math.sin(math.pi * x)
def rr(c, x0, y0, x1, y1, r, p): c.drawRRect(skia.RRect.MakeRectXY(skia.Rect(x0, y0, x1, y1), r, r), p)
def grad_rr(c, x0, y0, x1, y1, r, top, bot, a=1.0, outline=None, ow=2.0):
    sh = skia.GradientShader.MakeLinear([(0, y0), (0, y1)], [col(top, a), col(bot, a)])
    rr(c, x0, y0, x1, y1, r, skia.Paint(AntiAlias=True, Shader=sh))
    if outline: rr(c, x0, y0, x1, y1, r, paint(outline, a, stroke=ow))

def label(c, s, x, y, color=WHITE, a=1.0, size=28, w='semi', align='center', bg=True, border=None):
    """pill label (bg) or plain text"""
    if a <= 0.003: return
    if bg:
        tw = text_w(s, size, w); h = size * 1.6; padx = 18
        x0 = x - tw / 2 - padx if align == 'center' else (x - padx if align == 'left' else x - tw - padx)
        rr(c, x0, y - h / 2, x0 + tw + 2 * padx, y + h / 2, h / 2, paint((10, 18, 40), a * 0.88))
        rr(c, x0, y - h / 2, x0 + tw + 2 * padx, y + h / 2, h / 2, paint(border or color, a * 0.9, stroke=2.2))
        text(c, s, x0 + padx + tw / 2, y + size * 0.36, size, color, a, w)
    else:
        text(c, s, x, y + size * 0.36, size, color, a, w, align)

def card(c, x0, y0, x1, y1, a=1.0, border=(70, 95, 150), fill=(12, 22, 48), r=22):
    if a <= 0.003: return
    c.drawRRect(skia.RRect.MakeRectXY(skia.Rect(x0, y0 + 8, x1, y1 + 8), r, r), paint((0, 0, 0), a * 0.35, blur=14))
    rr(c, x0, y0, x1, y1, r, paint(fill, a * 0.94)); rr(c, x0, y0, x1, y1, r, paint(border, a * 0.9, stroke=2.2))

# ------------------------------------------------------------------ wires
WIRE_STYLE = {  # core, edge(glow) colour
    'hotA': ((70, 44, 30), HOT_A), 'hotB': ((70, 30, 30), HOT_B), 'hot': ((34, 34, 40), HOT_A),
    'neutral': (NEUT, (190, 200, 220)), 'ground': (COPPER, GRN), 'hv': ((60, 60, 70), (255, 120, 90)),
    'plain': ((70, 80, 100), (140, 155, 190)), 'water': ((40, 70, 110), WATER)}
def wire(c, pts, kind, a=1.0, live=0.0, t=0.0, grow=1.0, w=10, speed=0.35, n=None, heat=0.0, dots=None, rev=False, dotc=None):
    if a <= 0.003 or grow <= 0.001: return
    P = partial_polyline(pts, grow) if grow < 1 else pts
    if len(P) < 2: return
    core, edge = WIRE_STYLE[kind]
    path = polyline_path(P)
    if live > 0.01:
        c.drawPath(path, paint(edge, a * 0.35 * live, stroke=w * 3.2, blur=w * 1.3))
    c.drawPath(path, paint(lerpc((70, 82, 110), edge, 0.35 + 0.65 * live), a, stroke=w + 5))
    cc = core
    if heat > 0:
        cc = lerpc(core, (255, 70, 30), clamp(heat * 1.6)); cc = lerpc(cc, (255, 230, 170), clamp(heat * 2 - 1))
        c.drawPath(path, paint((255, 90, 40), a * heat * 0.7, stroke=w * 4, blur=w * 2.2))
    c.drawPath(path, paint(cc, a, stroke=w))
    if kind == 'neutral' or heat > 0.3:
        c.drawPath(path, paint((255, 255, 255), a * 0.5, stroke=max(1, w * 0.3)))
    dl = live if dots is None else dots
    if dl > 0.01 and grow >= 0.999:
        L = sum(math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]) for i in range(1, len(pts)))
        nn = n or max(3, int(L / 70))
        flow_dots(c, pts[::-1] if rev else pts, t, dotc or edge, speed * 300 / max(L, 1), nn, max(3.5, w * 0.48), a * dl)

def flow_cont(c, pts, t, color, spacing=60, speed=160, r=6, a=1.0):
    """evenly spaced dots moving along a polyline without the fade envelope (for loops)"""
    if a <= 0.003: return
    d = [0]
    for i in range(1, len(pts)): d.append(d[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    L = d[-1]; off = (t * speed) % spacing; s = off
    while s < L:
        i = max(1, min(len(pts) - 1, int(np.searchsorted(d, s))))
        kk = (s - d[i - 1]) / max(d[i] - d[i - 1], 1e-9)
        x = lerp(pts[i - 1][0], pts[i][0], kk); y = lerp(pts[i - 1][1], pts[i][1], kk)
        ea = min(1, s / 40, (L - s) / 40)
        c.drawCircle(x, y, r * 2.3, paint(color, a * ea * 0.45, blur=r * 1.5))
        c.drawCircle(x, y, r, paint((255, 252, 240), a * ea))
        s += spacing

def sag(p0, p1, depth, n=24):
    return [(lerp(p0[0], p1[0], i / n), lerp(p0[1], p1[1], i / n) + depth * 4 * (i / n) * (1 - i / n)) for i in range(n + 1)]

def rounded_poly(pts, r=30, n=6):
    """polyline with rounded corners"""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        d0 = math.hypot(p1[0] - p0[0], p1[1] - p0[1]); d1 = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if d0 < 1e-6 or d1 < 1e-6: continue
        rr_ = min(r, d0 / 2, d1 / 2)
        a = (p1[0] + (p0[0] - p1[0]) * rr_ / d0, p1[1] + (p0[1] - p1[1]) * rr_ / d0)
        b = (p1[0] + (p2[0] - p1[0]) * rr_ / d1, p1[1] + (p2[1] - p1[1]) * rr_ / d1)
        for k in range(n + 1):
            u = k / n
            out.append(((1 - u) ** 2 * a[0] + 2 * (1 - u) * u * p1[0] + u * u * b[0], (1 - u) ** 2 * a[1] + 2 * (1 - u) * u * p1[1] + u * u * b[1]))
    out.append(pts[-1]); return out

# ------------------------------------------------------------------ street hardware
def pole(c, x, gy, top, a=1.0, arm=True, w=22):
    if a <= 0.003: return
    sh = skia.GradientShader.MakeLinear([(x - w / 2, 0), (x + w / 2, 0)], [col(WOOD_L, a), col(WOOD, a)])
    c.drawRect(skia.Rect(x - w / 2, top, x + w / 2, gy), skia.Paint(AntiAlias=True, Shader=sh))
    if arm:
        c.drawRect(skia.Rect(x - 110, top + 30, x + 110, top + 46), paint(WOOD, a))
        for dx in (-95, 0, 95):
            rr(c, x + dx - 7, top + 6, x + dx + 7, top + 32, 4, paint((180, 200, 220), a))

def can_xfmr(c, x, y, s=1.0, a=1.0, glow=0.0):
    """gray pole-top transformer can, centre-top at (x,y)"""
    if a <= 0.003: return
    w, h = 64 * s, 104 * s
    if glow > 0: rr(c, x - w / 2 - 6, y - 6, x + w / 2 + 6, y + h + 6, 18 * s, paint(CYAN, a * glow * 0.5, blur=20 * s))
    sh = skia.GradientShader.MakeLinear([(x - w / 2, 0), (x + w / 2, 0)], [col((170, 178, 192), a), col((205, 212, 224), a), col((120, 128, 144), a)], [0, 0.4, 1])
    rr(c, x - w / 2, y + 10 * s, x + w / 2, y + h, 10 * s, skia.Paint(AntiAlias=True, Shader=sh))
    rr(c, x - w / 2 - 4 * s, y + 4 * s, x + w / 2 + 4 * s, y + 16 * s, 5 * s, paint((185, 192, 205), a))
    for k in range(3):
        c.drawLine(x - w / 2 + 4 * s, y + (40 + 22 * k) * s, x + w / 2 - 4 * s, y + (40 + 22 * k) * s, paint((140, 148, 162), a, stroke=2 * s))
    rr(c, x - 8 * s, y - 16 * s, x + 8 * s, y + 6 * s, 4 * s, paint((120, 80, 70), a))  # bushing

def pad_xfmr(c, x, gy, s=1.0, a=1.0):
    if a <= 0.003: return
    w, h = 200 * s, 150 * s
    c.drawRect(skia.Rect(x - w / 2 - 14 * s, gy - 10 * s, x + w / 2 + 14 * s, gy + 4 * s), paint((150, 155, 165), a))
    grad_rr(c, x - w / 2, gy - 10 * s - h, x + w / 2, gy - 10 * s, 10 * s, (70, 140, 95), (40, 96, 64), a, (120, 190, 140), 2)
    for k in range(5):
        yy = gy - 10 * s - h + (30 + 14 * k) * s
        c.drawLine(x + 20 * s, yy, x + w / 2 - 22 * s, yy, paint((30, 70, 46), a, stroke=4 * s))
    c.drawCircle(x - w / 2 + 34 * s, gy - h / 2, 8 * s, paint((200, 200, 160), a))

def house_icon(c, x, gy, s=1.0, a=1.0, lit=0.0):
    """small flat house standing on ground y (centre x)"""
    if a <= 0.003: return
    w, h = 300 * s, 190 * s
    roof = poly_path([(x - w / 2 - 30 * s, gy - h), (x, gy - h - 130 * s), (x + w / 2 + 30 * s, gy - h)])
    c.drawPath(roof, paint(ROOF, a)); c.drawPath(roof, paint(HOUSE_E, a * 0.6, stroke=2.5))
    c.drawRect(skia.Rect(x - w / 2, gy - h, x + w / 2, gy), paint(HOUSE_W, a))
    c.drawRect(skia.Rect(x - w / 2, gy - h, x + w / 2, gy), paint(HOUSE_E, a * 0.6, stroke=2.5))
    for wx in (-90, 70):
        wc = lerpc((40, 60, 100), LIT, lit)
        if lit > 0: c.drawRect(skia.Rect(x + (wx - 10) * s, gy - (150 + 10) * s, x + (wx + 60) * s, gy - (80 - 10) * s), paint(LIT, a * lit * 0.4, blur=18 * s))
        c.drawRect(skia.Rect(x + wx * s, gy - 150 * s, x + (wx + 50) * s, gy - 80 * s), paint(wc, a))
    c.drawRect(skia.Rect(x - 25 * s, gy - 100 * s, x + 25 * s, gy), paint((24, 34, 60), a))

def meter(c, x, y, r=40, a=1.0, t=0.0, spin=0.0, digits=None):
    """round electric meter (glass globe + socket box) centred at x,y"""
    if a <= 0.003: return
    grad_rr(c, x - r * 1.05, y - r * 1.25, x + r * 1.05, y + r * 1.45, r * 0.18, (160, 168, 184), (110, 118, 134), a, (190, 198, 214), 2)
    c.drawCircle(x, y, r, paint((210, 225, 240), a * 0.95))
    c.drawCircle(x, y, r, paint((120, 130, 150), a, stroke=max(2, r * 0.06)))
    rr(c, x - r * 0.62, y - r * 0.32, x + r * 0.62, y + r * 0.12, r * 0.08, paint((24, 40, 36), a))
    if digits is not None and r > 30:
        text(c, digits, x, y + r * 0.04, r * 0.34, (120, 255, 170), a, 'semi')
    # rotating disc mark
    ang = t * 6 * spin
    c.drawLine(x - r * 0.5, y + r * 0.45, x + r * 0.5, y + r * 0.45, paint((90, 100, 120), a, stroke=max(1.5, r * 0.04)))
    mx = x + r * 0.45 * math.cos(ang)
    c.drawCircle(mx, y + r * 0.45, r * 0.06, paint((220, 60, 60), a * (0.4 + 0.6 * abs(math.sin(ang)))))

def lightning(c, x, y, s=1.0, a=1.0, color=(255, 240, 140)):
    if a <= 0.003: return
    pts = [(0, 0), (-30, 90), (-6, 90), (-36, 190), (40, 70), (12, 70), (36, 0)]
    p = poly_path([(x + px * s, y + py * s) for px, py in pts])
    c.drawPath(p, paint(color, a * 0.6, blur=22 * s)); c.drawPath(p, paint(color, a))

# ------------------------------------------------------------------ outlets / plugs
def outlet(c, x, y, s=1.0, a=1.0, hl=None, plate=True):
    """US duplex outlet centred at (x,y). hl: dict part->(color, alpha) for 'hot','neutral','ground'"""
    if a <= 0.003: return
    hl = hl or {}
    if plate:
        c.drawRRect(skia.RRect.MakeRectXY(skia.Rect(x - 82 * s, y - 128 * s + 6 * s, x + 82 * s, y + 128 * s + 6 * s), 14 * s, 14 * s), paint((0, 0, 0), a * 0.35, blur=10 * s))
        grad_rr(c, x - 82 * s, y - 128 * s, x + 82 * s, y + 128 * s, 14 * s, (238, 238, 232), (208, 208, 202), a, (170, 170, 165), 2)
        c.drawCircle(x, y, 6 * s, paint((170, 170, 165), a)); c.drawLine(x - 4 * s, y, x + 4 * s, y, paint((120, 120, 115), a, stroke=1.6 * s))
    for dy in (-62, 62):
        cy = y + dy * s
        face = skia.Path(); face.addRRect(skia.RRect.MakeRectXY(skia.Rect(x - 52 * s, cy - 46 * s, x + 52 * s, cy + 46 * s), 30 * s, 30 * s))
        c.drawPath(face, paint((226, 226, 220), a)); c.drawPath(face, paint((180, 180, 175), a, stroke=1.6 * s))
        parts = {'neutral': skia.Rect(x - 30 * s, cy - 32 * s, x - 18 * s, cy + 4 * s),  # tall (left)
                 'hot': skia.Rect(x + 18 * s, cy - 28 * s, x + 28 * s, cy + 2 * s)}       # short (right)
        for k, r_ in parts.items():
            if k in hl: c.drawRect(r_.makeOutset(6 * s, 6 * s), paint(hl[k][0], a * hl[k][1] * 0.7, blur=8 * s))
            c.drawRRect(skia.RRect.MakeRectXY(r_, 2 * s, 2 * s), paint((40, 40, 44), a))
        g = skia.Path(); g.addArc(skia.Rect(x - 11 * s, cy + 14 * s, x + 11 * s, cy + 36 * s), 180, 180)
        g.lineTo(x + 11 * s, cy + 36 * s); g.lineTo(x - 11 * s, cy + 36 * s); g.close()
        if 'ground' in hl:
            c.drawCircle(x, cy + 27 * s, 22 * s, paint(hl['ground'][0], a * hl['ground'][1] * 0.75, blur=9 * s))
        c.drawPath(g, paint((40, 40, 44), a))

def plug_face(c, x, y, s=1.0, a=1.0, hl_ground=0.0):
    """three-prong plug seen from the front"""
    if a <= 0.003: return
    grad_rr(c, x - 64 * s, y - 70 * s, x + 64 * s, y + 70 * s, 30 * s, (60, 64, 76), (36, 40, 50), a, (110, 118, 140), 2)
    for dx, hh in ((-28, 40), (28, 32)):
        rr(c, x + dx * s - 6 * s, y - 40 * s, x + dx * s + 6 * s, y + (hh - 40) * s, 2 * s, paint((215, 200, 150), a))
    if hl_ground > 0: c.drawCircle(x, y + 36 * s, 26 * s, paint(GRN, a * hl_ground * 0.8, blur=10 * s))
    c.drawCircle(x, y + 36 * s, 11 * s, paint((215, 200, 150), a))
    c.drawCircle(x, y + 36 * s, 11 * s, paint((140, 120, 80), a, stroke=1.5 * s))

def gfci(c, x, y, s=1.0, a=1.0, led=1.0, reset_out=0.0, hl_btn=0.0, t=0.0):
    """decora-style GFCI outlet centred at (x,y)"""
    if a <= 0.003: return
    c.drawRRect(skia.RRect.MakeRectXY(skia.Rect(x - 92 * s, y - 140 * s + 6 * s, x + 92 * s, y + 140 * s + 6 * s), 14 * s, 14 * s), paint((0, 0, 0), a * 0.35, blur=10 * s))
    grad_rr(c, x - 92 * s, y - 140 * s, x + 92 * s, y + 140 * s, 14 * s, (238, 238, 232), (208, 208, 202), a, (170, 170, 165), 2)
    grad_rr(c, x - 62 * s, y - 118 * s, x + 62 * s, y + 118 * s, 8 * s, (230, 230, 224), (214, 214, 208), a, (175, 175, 170), 1.5)
    for dy in (-74, 74):
        cy = y + dy * s
        rr(c, x - 30 * s, cy - 20 * s, x - 19 * s, cy + 14 * s, 2 * s, paint((40, 40, 44), a))
        rr(c, x + 19 * s, cy - 16 * s, x + 29 * s, cy + 12 * s, 2 * s, paint((40, 40, 44), a))
        g = skia.Path(); g.addArc(skia.Rect(x - 10 * s, cy + 16 * s, x + 10 * s, cy + 36 * s), 180, 180)
        g.lineTo(x + 10 * s, cy + 36 * s); g.lineTo(x - 10 * s, cy + 36 * s); g.close(); c.drawPath(g, paint((40, 40, 44), a))
    # buttons
    if hl_btn > 0: rr(c, x - 54 * s, y - 34 * s, x + 54 * s, y + 34 * s, 14 * s, paint(GOLD, a * hl_btn * 0.6, blur=12 * s))
    po = 5 * s * reset_out
    rr(c, x - 44 * s, y - 24 * s, x - 4 * s, y + 24 * s, 7 * s, paint((40, 42, 50), a))
    text(c, 'TEST', x - 24 * s, y + 6 * s, 11 * s, (230, 230, 230), a, 'bold')
    rr(c, x + 4 * s - po, y - 24 * s - po, x + 44 * s + po, y + 24 * s + po, 7 * s, paint((205, 60, 60), a))
    text(c, 'RESET', x + 24 * s, y + 6 * s, 10 * s, (255, 240, 240), a, 'bold')
    lc = lerpc((70, 80, 70), (90, 255, 140), led)
    if led > 0: c.drawCircle(x + 50 * s, y - 100 * s, 12 * s, paint((90, 255, 140), a * led * 0.6, blur=8 * s))
    c.drawCircle(x + 50 * s, y - 100 * s, 5 * s, paint(lc, a))

def wall_switch(c, x, y, s=1.0, a=1.0, on=1.0):
    if a <= 0.003: return
    c.drawRRect(skia.RRect.MakeRectXY(skia.Rect(x - 70 * s, y - 110 * s + 6 * s, x + 70 * s, y + 110 * s + 6 * s), 12 * s, 12 * s), paint((0, 0, 0), a * 0.35, blur=10 * s))
    grad_rr(c, x - 70 * s, y - 110 * s, x + 70 * s, y + 110 * s, 12 * s, (238, 238, 232), (208, 208, 202), a, (170, 170, 165), 2)
    rr(c, x - 16 * s, y - 40 * s, x + 16 * s, y + 40 * s, 4 * s, paint((175, 175, 170), a))
    yy = lerp(30, -30, on) * s
    rr(c, x - 13 * s, y + yy - 26 * s, x + 13 * s, y + yy + 26 * s, 6 * s, paint((246, 246, 240), a))
    rr(c, x - 13 * s, y + yy - 26 * s, x + 13 * s, y + yy + 26 * s, 6 * s, paint((160, 160, 155), a, stroke=1.5 * s))

# ------------------------------------------------------------------ breakers
def breaker_body(c, cx, cy, w, h, a=1.0, poles=1, pos=1.0, side=1, pitch=None, glow=None, glow_a=0.0, rating=None, s=1.0):
    """one breaker. pos: 1=ON (handle toward centre), 0.5=tripped (middle), 0=OFF. side=+1 left column (centre is +x)."""
    if a <= 0.003: return
    pitch = pitch or h * 1.1
    tot = h + (poles - 1) * pitch
    y0 = cy - h / 2; y1 = y0 + tot
    if glow and glow_a > 0:
        rr(c, cx - w / 2 - 8 * s, y0 - 8 * s, cx + w / 2 + 8 * s, y1 + 8 * s, 10 * s, paint(glow, a * glow_a * 0.55, blur=12 * s))
        rr(c, cx - w / 2 - 5 * s, y0 - 5 * s, cx + w / 2 + 5 * s, y1 + 5 * s, 9 * s, paint(glow, a * glow_a, stroke=3.5 * s))
    grad_rr(c, cx - w / 2, y0, cx + w / 2, y1, 6 * s, (66, 70, 82), (42, 46, 56), a, (100, 108, 124), 1.5 * s)
    hw, hh = w * 0.36, h * 0.46
    off = (pos - 0.5) * 2 * (w * 0.2) * side
    hcs = [cy + k * pitch for k in range(poles)]
    rr(c, cx - w * 0.32, y0 + h * 0.18, cx + w * 0.32, y1 - h * 0.18, 4 * s, paint((24, 26, 32), a))
    for hc in hcs:
        rr(c, cx + off - hw / 2, hc - hh / 2, cx + off + hw / 2, hc + hh / 2, 4 * s, paint((24, 26, 30), a))
        rr(c, cx + off - hw / 2 + 2 * s, hc - hh / 2 + 2 * s, cx + off + hw / 2 - 2 * s, hc - hh / 2 + hh * 0.4, 3 * s, paint((92, 96, 108), a))
    if poles > 1:  # handle tie
        rr(c, cx + off - hw * 0.18, hcs[0], cx + off + hw * 0.18, hcs[-1], 3 * s, paint((170, 176, 190), a))
    if rating:
        text(c, rating, cx - side * w * 0.36, y0 + h * 0.62, h * 0.26, (200, 205, 215), a, 'bold')

# Realistic residential panel. Panel-local coordinates: 0..600 x 0..800.
PW, PH = 600, 800
ROW0, PITCH, BH, BW = 236, 58, 50, 118
BUS_X = (288, 312)
BREAKERS = [  # (column 0=left 1=right, row, poles, label)
    (0, 0, 1, 'Kitchen'), (0, 1, 1, 'Kitchen'), (0, 2, 2, 'Dryer'), (0, 4, 1, 'Bathroom'), (0, 5, 1, 'Bedrooms'),
    (0, 6, 1, 'Living room'), (0, 7, 2, 'EV charger'),
    (1, 0, 2, 'Range / oven'), (1, 2, 2, 'Water heater'), (1, 4, 2, 'Central AC'), (1, 6, 1, 'Microwave'),
    (1, 7, 1, 'Lights'), (1, 8, 1, 'Garage')]
def bk_center(i):
    col_, row, poles, _ = BREAKERS[i]
    return (236 if col_ == 0 else 364), ROW0 + row * PITCH
def bk_index(lbl, n=0):
    k = [i for i, b in enumerate(BREAKERS) if b[3] == lbl]; return k[n]

def panel(c, X, Y, S=1.0, a=1.0, door=1.0, xray=0.0, dir_a=1.0, hl=None, pos=None, brk_a=1.0, wires_in=0.0, t=0.0,
          bars=0.0, neutral_in=0.0, live=0.0, cover=1.0, main_hl=0.0, bus_hl=0.0, bus_rows=None):
    """hl: {index: (colour, alpha)}; pos: {index: handle pos}. xray reveals bus bars; bars reveals neutral/ground bars."""
    if a <= 0.003: return
    hl = hl or {}; pos = pos or {}
    c.save(); c.translate(X, Y); c.scale(S, S)
    # incoming cable from the top (drawn behind the box)
    if wires_in > 0:
        wire(c, [(262, -260), (262, 70)], 'hotA', a, live, t, eout(wires_in), w=16)
        wire(c, [(338, -260), (338, 70)], 'hotB', a, live, t, eout(wires_in), w=16)
    if neutral_in > 0:
        wire(c, [(470, -260), (470, 40), (552, 120), (552, 210)], 'neutral', a, live * 0.0, t, eout(neutral_in), w=14)
    c.drawRRect(skia.RRect.MakeRectXY(skia.Rect(-36, 6, PW + 36, PH + 18), 16, 16), paint((0, 0, 0), a * 0.45, blur=18))
    grad_rr(c, -30, 0, PW + 30, PH, 14, (140, 148, 162), (104, 112, 128), a, (180, 188, 204), 2.5)
    rr(c, -10, 22, PW + 10, PH - 22, 8, paint((44, 48, 58), a))   # can interior
    # bus bars (x-ray)
    if xray > 0.003:
        xa = a * xray
        for k, bx in enumerate(BUS_X):
            cc = HOT_A if k == 0 else HOT_B
            g = 0.4 + 0.6 * bus_hl
            c.drawRect(skia.Rect(bx - 9, 150, bx + 9, 770), paint(cc, xa * 0.35 * g, blur=10))
            c.drawRect(skia.Rect(bx - 8, 150, bx + 8, 770), paint(lerpc((120, 90, 60), cc, 0.6), xa))
        for r in range(9):
            y = ROW0 + r * PITCH; k = r % 2; cc = HOT_A if k == 0 else HOT_B
            emph = 1.0 if (bus_rows is None or r in bus_rows) else 0.35
            c.drawRect(skia.Rect(250, y - 7, 350, y + 7), paint(cc, xa * emph))
        # main lugs
        c.drawRect(skia.Rect(250, 60, 350, 150), paint((80, 84, 96), xa))
    if bars > 0.003:
        ba = a * bars
        rr(c, 540, 200, 564, 760, 5, paint((205, 210, 220), ba)); rr(c, 36, 200, 60, 760, 5, paint(COPPER, ba))
        for yy in range(220, 760, 34):
            c.drawCircle(552, yy, 5, paint((120, 125, 135), ba)); c.drawCircle(48, yy, 5, paint((130, 80, 40), ba))
    # dead-front cover with breakers
    if cover > 0.003:
        ca = a * cover * (1 - 0.82 * xray)
        grad_rr(c, 0, 30, PW, PH - 30, 8, PANEL_L, PANEL_D, ca, (225, 230, 238), 1.5)
        rr(c, 168, 200, 432, 782, 6, paint((70, 74, 86), ca))
    # main breaker
    ma = a * brk_a * (1 - 0.6 * xray)
    if main_hl > 0:
        rr(c, 206, 62, 394, 182, 12, paint(GOLD, a * main_hl * 0.6, blur=14)); rr(c, 208, 64, 392, 180, 12, paint(GOLD, a * main_hl, stroke=4))
    grad_rr(c, 216, 72, 384, 172, 8, (66, 70, 82), (42, 46, 56), ma, (100, 108, 124), 1.5)
    rr(c, 236, 100, 364, 144, 6, paint((24, 26, 30), ma)); rr(c, 248, 104, 352, 120, 4, paint((92, 96, 108), ma))
    text(c, 'MAIN', 300, 164, 15, (220, 224, 232), ma, 'bold')
    for i, (cl, row, poles, lbl) in enumerate(BREAKERS):
        cx, cy = bk_center(i); side = 1 if cl == 0 else -1
        hc, ha = hl.get(i, (None, 0))
        breaker_body(c, cx, cy, BW, BH, a * brk_a * (1 - 0.6 * xray), poles, pos.get(i, 1.0), side, PITCH, hc, ha)
        if dir_a > 0:
            ly = cy + (poles - 1) * PITCH / 2
            da = a * dir_a * cover * (1 - xray)
            tc = (34, 40, 56) if ha < 0.5 else lerpc((34, 40, 56), (10, 10, 10), 0.5)
            if cl == 0: text(c, lbl, 160, ly + 8, 21, tc, da, 'semi', 'right')
            else: text(c, lbl, 440, ly + 8, 21, tc, da, 'semi', 'left')
    # door (hinged on the left edge)
    if True:
        th = door * math.radians(100); cw = math.cos(th); sk = 46 * math.sin(th)
        xr = -30 + (PW + 60) * cw
        pts = [(-30, 0), (xr, -sk), (xr, PH + sk), (-30, PH)]
        front = cw > 0
        sh = skia.GradientShader.MakeLinear([(0, 0), (max(abs(xr), 1) * (1 if front else -1), 0)],
                                            [col((168, 175, 188) if front else (90, 96, 110), a), col((132, 140, 154) if front else (70, 76, 90), a)])
        c.drawPath(poly_path(pts), skia.Paint(AntiAlias=True, Shader=sh))
        c.drawPath(poly_path(pts), paint((190, 198, 212), a, stroke=2))
        if front and cw > 0.15:
            lx = xr - 40 * cw
            rr(c, lx - 10 * cw, PH / 2 - 40, lx + 10 * cw, PH / 2 + 40, 4, paint((80, 86, 100), a))
            rr(c, xr * 0.3, 90, xr * 0.7, 130, 4, paint((210, 214, 222), a * 0.8))
    c.restore()

def panel_pt(X, Y, S, px, py): return (X + px * S, Y + py * S)

# ------------------------------------------------------------------ appliance icons (centred at x,y; ~140px box at s=1)
def icon(c, name, x, y, s=1.0, a=1.0, on=0.0, t=0.0):
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    BODY, BODY_D, EDGE = (196, 206, 224), (150, 162, 186), (230, 236, 248)
    def body(x0, y0, x1, y1, r=10, top=BODY, bot=BODY_D): grad_rr(c, x0, y0, x1, y1, r, top, bot, a, EDGE, 1.5)
    if name == 'toaster':
        body(-62, -30, 62, 50, 22)
        for dx in (-26, 14):
            rr(c, dx - 6, -36, dx + 18, -24, 4, paint((60, 64, 76), a))
            if on > 0: rr(c, dx - 6, -40, dx + 18, -28, 4, paint((255, 110, 50), a * on, blur=6))
        rr(c, 46, -8, 58, 24, 3, paint((70, 74, 88), a))
        if on > 0:
            for k in range(3):
                ph = (t * 0.6 + k / 3) % 1
                c.drawCircle(-20 + k * 20 + 6 * math.sin(t * 2 + k), -46 - ph * 40, 8 + 4 * ph, paint((220, 230, 255), a * on * 0.3 * (1 - ph), blur=5))
    elif name == 'microwave':
        body(-80, -50, 80, 50, 8)
        rr(c, -68, -38, 28, 38, 6, paint(lerpc((30, 36, 50), (255, 200, 110), on * 0.8), a))
        if on > 0: rr(c, -68, -38, 28, 38, 6, paint((255, 190, 90), a * on * 0.6, blur=12))
        for k in range(4): rr(c, 40, -34 + k * 14, 68, -26 + k * 14, 2, paint((80, 86, 100), a))
        rr(c, 40, 22, 68, 36, 3, paint((40, 200, 120) if on > 0.5 else (60, 70, 80), a))
    elif name == 'coffee':
        body(-50, -60, 50, -30, 8); body(-50, -30, -20, 60, 6); body(-50, 50, 50, 66, 6)
        c.drawRRect(skia.RRect.MakeRectXY(skia.Rect(-12, 0, 40, 48), 8, 8), paint((120, 170, 220), a * 0.35))
        c.drawRect(skia.Rect(-10, lerp(46, 18, on), 38, 46), paint((110, 60, 30), a * 0.9))
        c.drawRRect(skia.RRect.MakeRectXY(skia.Rect(-12, 0, 40, 48), 8, 8), paint(EDGE, a, stroke=2))
        c.drawCircle(-35, 0, 5, paint((255, 70, 60) if on > 0.5 else (90, 60, 60), a))
        if on > 0:
            for k in range(2):
                ph = (t * 0.5 + k / 2) % 1
                c.drawCircle(14 + 5 * math.sin(t * 2 + k * 2), -4 - ph * 50, 6 + 5 * ph, paint((220, 230, 255), a * on * 0.25 * (1 - ph), blur=5))
    elif name == 'tv':
        rr(c, -78, -52, 78, 42, 6, paint((30, 34, 44), a)); rr(c, -78, -52, 78, 42, 6, paint(EDGE, a, stroke=2))
        sh = skia.GradientShader.MakeLinear([(-70, -44), (70, 34)], [col((80, 140, 255), a), col((160, 90, 255), a)])
        rr(c, -70, -44, 70, 34, 4, skia.Paint(AntiAlias=True, Shader=sh))
        c.drawRect(skia.Rect(-8, 42, 8, 56), paint(BODY_D, a)); rr(c, -40, 54, 40, 62, 3, paint(BODY_D, a))
    elif name == 'phone':
        rr(c, -60, 10, -24, 54, 6, paint(BODY, a))  # charger block
        for dx in (-50, -36): c.drawRect(skia.Rect(dx, 54, dx + 4, 66), paint((210, 200, 150), a))
        pth = skia.Path(); pth.moveTo(-42, 10); pth.cubicTo(-42, -30, 0, 40, 10, 0)
        c.drawPath(pth, paint((230, 236, 248), a, stroke=4))
        rr(c, 6, -62, 58, 50, 10, paint((30, 34, 44), a)); rr(c, 6, -62, 58, 50, 10, paint(EDGE, a, stroke=2.5))
        rr(c, 12, -52, 52, 38, 4, paint((60, 200, 140), a * 0.8))
        rr(c, 26, -20, 38, 4, 2, paint((240, 255, 245), a))
    elif name == 'bulb':
        if on > 0: c.drawCircle(0, -14, 70, paint(LIT, a * 0.35 * on, blur=26))
        c.drawCircle(0, -14, 42, paint(lerpc((200, 210, 230), LIT, 0.8), a))
        rr(c, -20, 26, 20, 52, 4, paint((160, 168, 184), a))
        for k in range(3): c.drawLine(-20, 32 + k * 7, 20, 32 + k * 7, paint((110, 118, 134), a, stroke=2))
    elif name == 'outlet':
        outlet(c, 0, 0, 0.42, a)
    elif name == 'dryer':
        body(-62, -70, 62, 70, 10)
        c.drawLine(-62, -40, 62, -40, paint(BODY_D, a, stroke=2))
        c.drawCircle(30, -55, 8, paint((90, 100, 120), a)); rr(c, -50, -60, -10, -50, 3, paint((60, 200, 140), a))
        c.drawCircle(0, 16, 40, paint((40, 46, 60), a)); c.drawCircle(0, 16, 40, paint(EDGE, a, stroke=5))
        c.drawCircle(0, 16, 26, paint((70, 80, 100), a))
    elif name == 'oven':
        body(-66, -70, 66, 70, 10)
        for k in range(4): c.drawCircle(-42 + k * 28, -54, 8, paint((80, 86, 100), a))
        c.drawLine(-66, -38, 66, -38, paint(BODY_D, a, stroke=2))
        rr(c, -48, -22, 48, 48, 6, paint((30, 36, 50), a))
        rr(c, -36, -12, 36, 38, 4, paint((255, 130, 60), a * 0.45))
        rr(c, -40, -32, 40, -27, 2, paint((90, 96, 110), a))
    elif name == 'heater':
        body(-44, -72, 44, 66, 30)
        c.drawRect(skia.Rect(-20, -84, -10, -72), paint(COPPER, a)); c.drawRect(skia.Rect(10, -84, 20, -72), paint(COPPER, a))
        rr(c, -20, 10, 20, 40, 4, paint((80, 86, 100), a)); text(c, 'HOT', 0, -16, 18, (230, 90, 70), a, 'bold')
    elif name == 'ac':
        body(-70, -56, 70, 66, 10)
        c.drawCircle(0, 4, 44, paint((50, 56, 72), a))
        for k in range(12): c.drawLine(-44, -40 + k * 8, 44, -40 + k * 8, paint((110, 118, 134), a * 0.55, stroke=1.5))
        ang = t * 9 * (0.3 + on)
        for k in range(3):
            an = ang + k * 2 * math.pi / 3
            c.drawLine(0, 4, 32 * math.cos(an), 4 + 32 * math.sin(an), paint((200, 210, 230), a, stroke=9))
        c.drawCircle(0, 4, 8, paint((200, 210, 230), a))
    elif name == 'ev':
        body(-34, -72, 34, 50, 12)
        rr(c, -22, -58, 22, -26, 4, paint((40, 200, 130), a))
        lightning(c, 3, -54, 0.13, a, (20, 40, 30))
        pth = skia.Path(); pth.moveTo(0, 50); pth.cubicTo(0, 90, 70, 90, 70, 30)
        c.drawPath(pth, paint((40, 44, 56), a, stroke=8)); rr(c, 60, 10, 80, 36, 5, paint((60, 64, 76), a))
    elif name == 'washer':
        body(-62, -70, 62, 70, 10)
        c.drawLine(-62, -40, 62, -40, paint(BODY_D, a, stroke=2))
        c.drawCircle(0, 16, 40, paint((60, 120, 200), a)); c.drawCircle(0, 16, 40, paint(EDGE, a, stroke=5))
    elif name == 'lamp':
        if on > 0: c.drawCircle(0, -40, 90, paint(LIT, a * 0.3 * on, blur=30))
        shade = poly_path([(-44, -16), (44, -16), (28, -70), (-28, -70)])
        c.drawPath(shade, paint(lerpc((210, 200, 180), (255, 236, 180), on), a))
        c.drawRect(skia.Rect(-4, -16, 4, 54), paint((150, 130, 100), a)); rr(c, -30, 50, 30, 62, 5, paint((150, 130, 100), a))
    c.restore()

def icon_card(c, name, x, y, lbl, a=1.0, accent=CYAN, on=1.0, t=0.0, s=1.0, pop=1.0):
    if a <= 0.003: return
    sc = s * (0.85 + 0.15 * eback(pop))
    c.save(); c.translate(x, y); c.scale(sc, sc)
    card(c, -110, -100, 110, 100, a, accent, (14, 24, 52))
    icon(c, name, 0, -12, 0.82, a, on, t)
    text(c, lbl, 0, 84, 24, WHITE, a, 'med')
    c.restore()

def earth(c, x0, y0, x1, y1, a=1.0):
    if a <= 0.003: return
    sh = skia.GradientShader.MakeLinear([(0, y0), (0, y1)], [col(EARTH_T, a), col(EARTH_B, a * 0.0)])
    c.drawRect(skia.Rect(x0, y0, x1, y1), skia.Paint(AntiAlias=True, Shader=sh))
    c.drawLine(x0, y0, x1, y0, paint((130, 170, 110), a, stroke=4))
    rng = np.random.default_rng(3)
    for k in range(40):
        px = rng.uniform(x0 + 10, x1 - 10); py = rng.uniform(y0 + 15, y0 + (y1 - y0) * 0.7)
        c.drawCircle(px, py, rng.uniform(2, 5), paint((130, 100, 70), a * 0.5))

def person(c, x, y, s=1.0, a=1.0, color=(170, 185, 215), reach=1.0):
    """simple standing figure, feet at (x,y), facing left; reach raises the left arm"""
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    p = paint(color, a)
    c.drawCircle(0, -250, 30, p)
    rr(c, -34, -212, 34, -90, 26, p)
    c.drawPath(polyline_path([(-14, -96), (-20, 0)]), paint(color, a, stroke=22))
    c.drawPath(polyline_path([(14, -96), (20, 0)]), paint(color, a, stroke=22))
    hx, hy = lerp(-40, -110, reach), lerp(-110, -160, reach)
    c.drawPath(polyline_path([(-22, -196), (hx, hy)]), paint(color, a, stroke=20))
    c.drawPath(polyline_path([(22, -196), (34, -110)]), paint(color, a, stroke=20))
    c.restore()
    return (x + hx * s, y + hy * s)

def fuse(c, x, y, s=1.0, a=1.0, melt=0.0, t=0.0):
    """Edison-base screw-in fuse, centre of glass at (x,y)"""
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    # screw base
    for k in range(5):
        rr(c, -58 + (k % 2) * 4, 70 + k * 18, 58 - (k % 2) * 4, 86 + k * 18, 8, paint((200, 180, 120), a))
    rr(c, -16, 160, 16, 176, 4, paint((180, 160, 100), a))
    grad_rr(c, -90, 40, 90, 74, 10, (70, 74, 86), (44, 48, 58), a, (110, 118, 134), 2)
    c.drawCircle(0, -30, 92, paint((150, 200, 255), a * 0.16)); c.drawCircle(0, -30, 92, paint((210, 230, 255), a * 0.6, stroke=3))
    # metal strip
    g = 1 - smooth(clamp(melt * 1.4))
    L = [(-60, -30), (-20, -30)]; R = [(20, -30), (60, -30)]
    pc = (230, 230, 235)
    if melt > 0: pc = lerpc(pc, (255, 120, 40), clamp(melt * 3))
    c.drawPath(polyline_path(L), paint(pc, a, stroke=8)); c.drawPath(polyline_path(R), paint(pc, a, stroke=8))
    mid = [(-20, -30), (20, -30)]
    if g > 0.02:
        c.drawPath(polyline_path([(-20, -30), (lerp(-20, 0, g), -30)]), paint(pc, a, stroke=8 * g + 0.5))
        c.drawPath(polyline_path([(lerp(20, 0, g), -30), (20, -30)]), paint(pc, a, stroke=8 * g + 0.5))
    if 0.05 < melt < 0.8:
        fl = bump((melt - 0.05) / 0.75)
        c.drawCircle(0, -30, 40, paint((255, 170, 60), a * fl * 0.8, blur=20))
    if melt >= 0.7:
        c.drawCircle(-20, -24, 6, paint((120, 110, 100), a)); c.drawCircle(20, -24, 6, paint((120, 110, 100), a))
        c.drawCircle(0, -26, 40, paint((40, 40, 40), a * 0.25, blur=16))
    c.restore()

def gauge(c, x, y, r, val, vmax=30, limit=20, a=1.0, t=0.0, lbl='amps flowing'):
    """semicircular dial with red zone above limit"""
    if a <= 0.003: return
    card(c, x - r - 40, y - r - 40, x + r + 40, y + 70, a)
    def ang(v): return math.pi + math.pi * clamp(v / vmax)
    arc = skia.Path(); arc.addArc(skia.Rect(x - r, y - r, x + r, y + r), 180, 180 * limit / vmax)
    c.drawPath(arc, paint((70, 200, 140), a * 0.9, stroke=16, cap='butt'))
    arc2 = skia.Path(); arc2.addArc(skia.Rect(x - r, y - r, x + r, y + r), 180 + 180 * limit / vmax, 180 * (1 - limit / vmax))
    over = val > limit
    c.drawPath(arc2, paint(RED, a * (0.75 + 0.25 * over * (0.5 + 0.5 * math.sin(t * 12))), stroke=16, cap='butt'))
    for k in range(7):
        an = math.pi + math.pi * k / 6
        c.drawLine(x + (r - 26) * math.cos(an), y + (r - 26) * math.sin(an), x + (r - 12) * math.cos(an), y + (r - 12) * math.sin(an), paint(MUTED, a, stroke=3))
    la = ang(limit)
    c.drawLine(x + (r - 34) * math.cos(la), y + (r - 34) * math.sin(la), x + (r + 14) * math.cos(la), y + (r + 14) * math.sin(la), paint(WHITE, a, stroke=4))
    text(c, f'{limit}', x + (r + 34) * math.cos(la), y + (r + 34) * math.sin(la) + 6, 24, WHITE, a, 'bold')
    an = ang(val)
    c.drawLine(x, y, x + (r - 20) * math.cos(an), y + (r - 20) * math.sin(an), paint(RED if over else WHITE, a, stroke=7))
    c.drawCircle(x, y, 12, paint(WHITE, a))
    text(c, lbl, x, y + 48, 26, MUTED, a, 'med')

def flame(c, x, y, s=1.0, a=1.0, t=0.0):
    if a <= 0.003: return
    for cc, sc in (((255, 80, 30), 1.0), ((255, 170, 60), 0.66), ((255, 240, 180), 0.34)):
        fl = 1 + 0.08 * math.sin(t * 17 + sc * 5) + 0.05 * math.sin(t * 29)
        hh = 70 * s * sc * fl; ww = 34 * s * sc
        p = skia.Path(); p.moveTo(x, y - hh)
        p.cubicTo(x + ww * 0.3, y - hh * 0.6, x + ww, y - hh * 0.45, x + ww * 0.8, y - hh * 0.1)
        p.cubicTo(x + ww * 0.6, y + hh * 0.12, x - ww * 0.6, y + hh * 0.12, x - ww * 0.8, y - hh * 0.1)
        p.cubicTo(x - ww, y - hh * 0.45, x - ww * 0.3, y - hh * 0.6, x, y - hh)
        if sc == 1.0: c.drawPath(p, paint(cc, a * 0.5, blur=14 * s))
        c.drawPath(p, paint(cc, a))

def xmark(c, x, y, r, a=1.0, color=RED):
    if a <= 0.003: return
    c.drawLine(x - r, y - r, x + r, y + r, paint(color, a, stroke=r * 0.32)); c.drawLine(x + r, y - r, x - r, y + r, paint(color, a, stroke=r * 0.32))
def tick(c, x, y, r, a=1.0, color=GREEN):
    if a <= 0.003: return
    c.drawPath(polyline_path([(x - r, y), (x - r * 0.3, y + r * 0.7), (x + r, y - r * 0.7)]), paint(color, a, stroke=r * 0.32))
