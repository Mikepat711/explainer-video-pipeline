# Flat diagram art for the natural gas explainer (skia). Coordinates in 1920x1080 space.
import math, skia, numpy as np
from lib import *
from art import (rr, grad_rr, label, card, flow_cont, sag, rounded_poly, house_icon, person, flame as fire_flame,
                 xmark, tick, bump, HOUSE_W, HOUSE_E, ROOF, LIT, EARTH_T, EARTH_B, RED, STEEL, STEEL_D, WATER)

GAS = (110, 220, 255)       # methane / gas flow
PE_Y = (246, 198, 58)       # yellow polyethylene
STEEL_C = (150, 160, 178); STEEL_DK = (84, 94, 112)
RUST = (150, 96, 70)
ODOR = (190, 230, 90)       # odorised gas tint
HEAT = (255, 110, 60)
SOIL_T, SOIL_B = (78, 60, 46), (40, 30, 26)
GRASS = (88, 150, 92)
SALT = (226, 230, 238)

def pipe(c, pts, w, a=1.0, kind='steel', grow=1.0, flow=0.0, t=0.0, spacing=None, speed=140, dotc=GAS, glow=0.0, r=None):
    """thick pipe along polyline; flow = alpha of moving gas dots"""
    if a <= 0.003 or grow <= 0.001: return
    P = partial_polyline(pts, grow) if grow < 1 else pts
    if len(P) < 2: return
    body = {'steel': STEEL_C, 'pe': PE_Y, 'iron': RUST, 'dark': (70, 80, 100), 'gas': (90, 150, 190)}[kind]
    edge = lerpc(body, (0, 0, 0), 0.55)
    path = polyline_path(P)
    if glow > 0: c.drawPath(path, paint(dotc, a * glow * 0.45, stroke=w * 2.6, blur=w * 0.9))
    c.drawPath(path, paint(edge, a, stroke=w + 5))
    c.drawPath(path, paint(body, a, stroke=w))
    c.drawPath(path, paint(lerpc(body, (255, 255, 255), 0.35), a * 0.55, stroke=max(1.5, w * 0.22)))
    if flow > 0.01:
        flow_cont(c, P, t, dotc, spacing or max(26, w * 2.2), speed, max(3, w * 0.2), a * flow)

def soil(c, x0, y0, x1, y1, a=1.0, grass=True, top=SOIL_T, bot=SOIL_B):
    if a <= 0.003: return
    sh = skia.GradientShader.MakeLinear([(0, y0), (0, y1)], [col(top, a), col(bot, a * 0.9)])
    c.drawRect(skia.Rect(x0, y0, x1, y1), skia.Paint(AntiAlias=True, Shader=sh))
    rng = np.random.default_rng(int(x0 + y0) % 997)
    for k in range(int((x1 - x0) * (y1 - y0) / 9000)):
        px = rng.uniform(x0 + 6, x1 - 6); py = rng.uniform(y0 + 12, y1 - 6)
        c.drawCircle(px, py, rng.uniform(2, 4.5), paint((120, 96, 72), a * 0.45))
    if grass: c.drawLine(x0, y0, x1, y0, paint(GRASS, a, stroke=6))

def burner(c, x, y, s=1.0, a=1.0, fl=0.0, t=0.0):
    """stove burner seen in slight perspective (ellipse), blue flame ring when fl>0"""
    if a <= 0.003: return
    rx, ry = 120 * s, 34 * s
    c.drawOval(skia.Rect(x - rx * 1.25, y - ry * 1.25, x + rx * 1.25, y + ry * 1.25), paint((30, 32, 40), a))
    for k in range(8):  # grate
        an = k * math.pi / 4
        c.drawLine(x, y, x + rx * 1.25 * math.cos(an), y + ry * 1.25 * math.sin(an), paint((60, 62, 72), a, stroke=7 * s))
    c.drawOval(skia.Rect(x - rx * 0.62, y - ry * 0.62, x + rx * 0.62, y + ry * 0.62), paint((88, 90, 102), a))
    c.drawOval(skia.Rect(x - rx * 0.4, y - ry * 0.4, x + rx * 0.4, y + ry * 0.4), paint((50, 52, 62), a))
    if fl > 0.01:
        c.drawOval(skia.Rect(x - rx * 0.9, y - ry * 1.4 - 30 * s, x + rx * 0.9, y + ry * 0.6), paint((60, 120, 255), a * fl * 0.35, blur=26 * s))
        n = 18
        for k in range(n):
            an = 2 * math.pi * k / n
            px = x + rx * 0.62 * math.cos(an); py = y + ry * 0.62 * math.sin(an)
            front = 0.55 + 0.45 * max(0, math.sin(an))
            h = (40 + 8 * math.sin(t * 19 + k * 1.7)) * s * fl
            wd = 7 * s
            p = skia.Path(); p.moveTo(px - wd, py); p.quadTo(px - wd * 0.6, py - h * 0.6, px, py - h)
            p.quadTo(px + wd * 0.6, py - h * 0.6, px + wd, py); p.close()
            c.drawPath(p, paint((70, 130, 255), a * fl * front))
            p2 = skia.Path(); p2.moveTo(px - wd * 0.5, py); p2.quadTo(px - wd * 0.3, py - h * 0.35, px, py - h * 0.55)
            p2.quadTo(px + wd * 0.3, py - h * 0.35, px + wd * 0.5, py); p2.close()
            c.drawPath(p2, paint((170, 220, 255), a * fl * front))

def knob(c, x, y, r, ang, a=1.0):
    if a <= 0.003: return
    c.drawCircle(x, y + 4, r + 4, paint((0, 0, 0), a * 0.4, blur=6))
    c.drawCircle(x, y, r, paint((210, 214, 224), a)); c.drawCircle(x, y, r, paint((120, 126, 140), a, stroke=3))
    c.drawCircle(x, y, r * 0.78, paint((236, 238, 244), a))
    dx, dy = math.sin(ang), -math.cos(ang)
    c.drawLine(x - dx * r * 0.6, y - dy * r * 0.6, x + dx * r * 0.7, y + dy * r * 0.7, paint((70, 76, 90), a, stroke=r * 0.28))
    c.drawCircle(x + dx * r * 0.62, y + dy * r * 0.62, r * 0.1, paint(RED, a))

def stove(c, x, y, s=1.0, a=1.0, knob_ang=0.0, fl=0.0, t=0.0):
    """front-ish stove: top surface centre at (x,y)"""
    if a <= 0.003: return
    w = 520 * s
    # top surface (trapezoid)
    top = poly_path([(x - w / 2 + 40 * s, y - 90 * s), (x + w / 2 - 40 * s, y - 90 * s), (x + w / 2, y + 60 * s), (x - w / 2, y + 60 * s)])
    c.drawPath(top, paint((44, 48, 60), a)); c.drawPath(top, paint((110, 118, 140), a, stroke=3 * s))
    # front panel
    grad_rr(c, x - w / 2, y + 60 * s, x + w / 2, y + 170 * s, 6 * s, (214, 218, 228), (170, 176, 190), a, (120, 126, 140), 2 * s)
    grad_rr(c, x - w / 2, y + 170 * s, x + w / 2, y + 470 * s, 6 * s, (200, 204, 216), (150, 156, 170), a, (120, 126, 140), 2 * s)
    rr(c, x - w / 2 + 40 * s, y + 200 * s, x + w / 2 - 40 * s, y + 420 * s, 10 * s, paint((26, 30, 40), a))
    rr(c, x - w / 2 + 60 * s, y + 186 * s, x + w / 2 - 60 * s, y + 198 * s, 5 * s, paint((120, 126, 140), a))
    burner(c, x - 120 * s, y - 32 * s, 0.62 * s, a, 0, t)
    burner(c, x + 120 * s, y - 32 * s, 0.62 * s, a, 0, t)
    burner(c, x, y + 20 * s, 0.82 * s, a, fl, t)
    for k, dx in enumerate((-180, -90, 90, 180)):
        knob(c, x + dx * s, y + 115 * s, 26 * s, 0, a)
    knob(c, x, y + 115 * s, 30 * s, knob_ang, a)

def wellhead(c, x, gy, s=1.0, a=1.0, glow=0.0):
    """'christmas tree' wellhead standing on ground y"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    if glow > 0: c.drawCircle(0, -90, 120, paint(GAS, a * glow * 0.35, blur=40))
    rr(c, -46, -20, 46, 0, 4, paint((110, 116, 130), a))
    grad_rr(c, -18, -190, 18, -20, 4, (210, 70, 60), (160, 50, 44), a, (90, 30, 30), 2)
    for yy in (-60, -130):
        grad_rr(c, -34, yy - 18, 34, yy + 18, 6, (230, 90, 70), (170, 56, 46), a, (90, 30, 30), 2)
        c.drawCircle(-52, yy, 16, paint((250, 210, 70), a, stroke=6)); c.drawLine(-34, yy, -52, yy, paint((250, 210, 70), a, stroke=5))
    rr(c, 18, -110, 80, -92, 4, paint((210, 70, 60), a))  # side outlet
    c.drawCircle(0, -200, 16, paint((250, 210, 70), a, stroke=6))
    c.restore()

def tiny_well(c, x, y, s=1.0, a=1.0):
    """map-view well marker"""
    if a <= 0.003: return
    c.drawCircle(x, y, 22 * s, paint((20, 30, 56), a)); c.drawCircle(x, y, 22 * s, paint((230, 90, 70), a, stroke=4 * s))
    rr(c, x - 5 * s, y - 13 * s, x + 5 * s, y + 13 * s, 2 * s, paint((230, 90, 70), a))
    c.drawLine(x - 11 * s, y - 4 * s, x + 11 * s, y - 4 * s, paint((250, 210, 70), a, stroke=4 * s))

def plant_icon(c, x, gy, s=1.0, a=1.0, t=0.0, glow=0.0):
    """processing plant: towers + tanks + building, standing on ground y"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    if glow > 0: c.drawCircle(0, -120, 220, paint(GAS, a * glow * 0.25, blur=60))
    grad_rr(c, -200, -110, 40, 0, 6, (70, 84, 120), (46, 56, 86), a, (120, 140, 190), 2)
    for k in range(4): rr(c, -180 + k * 54, -80, -150 + k * 54, -54, 3, paint(LIT, a * 0.7))
    for dx, h in ((70, 250), (120, 300), (170, 220)):
        grad_rr(c, dx - 20, -h, dx + 20, 0, 10, (180, 190, 208), (120, 130, 150), a, (200, 210, 230), 2)
        for yy in range(-h + 40, -10, 50): c.drawLine(dx - 20, yy, dx + 20, yy, paint((100, 110, 130), a, stroke=2))
    for dx in (-150, -70):
        c.drawOval(skia.Rect(dx - 40, -170, dx + 40, -110), paint((200, 206, 220), a))
        c.drawRect(skia.Rect(dx - 40, -140, dx + 40, -110), paint((200, 206, 220), a))
    c.drawLine(-200, 0, 210, 0, paint((110, 140, 200), a * 0.6, stroke=2))
    # flare/stack plume
    for k in range(3):
        ph = (t * 0.3 + k / 3) % 1
        c.drawCircle(120 + ph * 30, -320 - ph * 90, 12 + ph * 26, paint((200, 210, 230), a * 0.22 * (1 - ph), blur=8))
    c.restore()

def compressor(c, x, gy, s=1.0, a=1.0, t=0.0, glow=0.0, on=1.0):
    """compressor station building on ground y"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    if glow > 0: c.drawCircle(0, -70, 150, paint(GAS, a * glow * 0.35, blur=40))
    grad_rr(c, -110, -120, 110, 0, 4, (196, 202, 214), (140, 148, 164), a, (220, 226, 236), 2)
    roof = poly_path([(-120, -120), (0, -160), (120, -120)])
    c.drawPath(roof, paint((90, 100, 124), a))
    for dx in (-70, 70):
        rr(c, dx - 10, -210, dx + 10, -130, 3, paint((120, 128, 146), a))
        for k in range(2):
            ph = (t * 0.6 + k / 2) % 1
            c.drawCircle(dx + ph * 16, -220 - ph * 60, 8 + ph * 16, paint((210, 220, 236), a * 0.3 * (1 - ph) * on, blur=6))
    # fan icon
    c.drawCircle(0, -60, 34, paint((40, 50, 74), a)); 
    for k in range(3):
        an = t * 7 * on + k * 2 * math.pi / 3
        c.drawLine(0, -60, 28 * math.cos(an), -60 + 28 * math.sin(an), paint(GAS, a, stroke=8))
    c.drawCircle(0, -60, 7, paint(WHITE, a))
    c.restore()

def marker_post(c, x, gy, s=1.0, a=1.0):
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    rr(c, -9, -150, 9, 0, 3, paint((250, 206, 40), a))
    rr(c, -14, -170, 14, -140, 5, paint((255, 150, 40), a))
    for yy in (-120, -100): c.drawLine(-9, yy, 9, yy, paint((40, 40, 40), a, stroke=4))
    c.restore()

def tree(c, x, gy, s=1.0, a=1.0, shade=0.0):
    if a <= 0.003: return
    c.drawRect(skia.Rect(x - 6 * s, gy - 40 * s, x + 6 * s, gy), paint((90, 64, 40), a))
    cc = lerpc((60, 130, 80), (30, 70, 50), shade)
    c.drawPath(poly_path([(x - 40 * s, gy - 30 * s), (x, gy - 140 * s), (x + 40 * s, gy - 30 * s)]), paint(cc, a))

def regulator(c, x, y, s=1.0, a=1.0, glow=0.0, color=(150, 160, 178)):
    """bell-shaped service regulator; (x,y) = centre of the pipe body"""
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    if glow > 0: c.drawCircle(0, -30, 90, paint(GAS, a * glow * 0.45, blur=30))
    grad_rr(c, -26, -14, 26, 22, 6, (170, 178, 194), (110, 118, 134), a, (70, 76, 92), 2)
    bell = skia.Path(); bell.moveTo(-62, -18); bell.cubicTo(-62, -90, 62, -90, 62, -18); bell.close()
    sh = skia.GradientShader.MakeLinear([(-62, 0), (62, 0)], [col((200, 206, 220), a), col(color, a), col((100, 108, 124), a)], [0, 0.45, 1])
    c.drawPath(bell, skia.Paint(AntiAlias=True, Shader=sh)); c.drawPath(bell, paint((70, 76, 92), a, stroke=2.5))
    rr(c, -66, -22, 66, -12, 4, paint((120, 128, 146), a))
    # vent
    rr(c, 50, -60, 92, -46, 4, paint((120, 128, 146), a)); c.drawCircle(96, -53, 10, paint((90, 98, 116), a))
    c.restore()

def valve(c, x, y, s=1.0, a=1.0, ang=0.0, glow=0.0, color=(250, 200, 60)):
    """inline quarter-turn valve body + lever handle; ang=0 -> handle along pipe (open)"""
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    if glow > 0: c.drawCircle(0, -10, 60, paint(color, a * glow * 0.5, blur=22))
    grad_rr(c, -22, -18, 22, 18, 6, (200, 170, 90), (150, 120, 60), a, (90, 70, 30), 2)
    c.drawCircle(0, -22, 7, paint((90, 70, 30), a))
    c.save(); c.rotate(math.degrees(ang))
    rr(c, -4, -26, 56, -16, 4, paint(color, a)); c.restore()
    c.restore()

def gas_meter(c, x, y, s=1.0, a=1.0, t=0.0, spin=0.0, glow=0.0):
    """diaphragm gas meter box; (x,y) centre"""
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    if glow > 0: rr(c, -100, -110, 100, 110, 30, paint(GAS, a * glow * 0.4, blur=30))
    grad_rr(c, -80, -90, 80, 90, 14, (196, 202, 214), (140, 148, 164), a, (90, 98, 116), 3)
    rr(c, -64, -60, 64, 10, 8, paint((235, 238, 244), a)); rr(c, -64, -60, 64, 10, 8, paint((90, 98, 116), a, stroke=2))
    for k in range(4):
        cx = -45 + k * 30; cy = -25
        c.drawCircle(cx, cy, 13, paint((255, 255, 255), a)); c.drawCircle(cx, cy, 13, paint((60, 66, 80), a, stroke=2))
        an = t * spin * (2.2 / (k + 1)) * (1 if k % 2 == 0 else -1) - math.pi / 2
        c.drawLine(cx, cy, cx + 10 * math.cos(an), cy + 10 * math.sin(an), paint(RED, a, stroke=2.5))
    rr(c, -40, 30, 40, 60, 6, paint((110, 118, 134), a))
    # inlet/outlet stubs on top
    for dx in (-50, 50): rr(c, dx - 12, -112, dx + 12, -88, 4, paint((150, 158, 176), a))
    c.restore()

def tank(c, x, gy, w, h, a=1.0, color=(200, 206, 220), lbl=None, lc=WHITE):
    if a <= 0.003: return
    grad_rr(c, x - w / 2, gy - h, x + w / 2, gy, w * 0.25, lerpc(color, (255, 255, 255), 0.15), lerpc(color, (0, 0, 0), 0.3), a, lerpc(color, (0, 0, 0), 0.5), 2)

def drop_icon(c, x, y, r, a=1.0, color=WATER):
    if a <= 0.003: return
    p = skia.Path(); p.moveTo(x, y - r * 1.6); p.cubicTo(x + r * 0.4, y - r * 0.9, x + r, y - r * 0.4, x + r, y + r * 0.1)
    p.cubicTo(x + r, y + r * 0.7, x + r * 0.5, y + r, x, y + r); p.cubicTo(x - r * 0.5, y + r, x - r, y + r * 0.7, x - r, y + r * 0.1)
    p.cubicTo(x - r, y - r * 0.4, x - r * 0.4, y - r * 0.9, x, y - r * 1.6); p.close()
    c.drawPath(p, paint(color, a))

def methane(c, x, y, s=1.0, a=1.0, t=0.0):
    """CH4 ball-and-stick"""
    if a <= 0.003: return
    for k in range(4):
        an = t * 0.8 + k * math.pi / 2 + 0.4
        hx, hy = x + 70 * s * math.cos(an), y + 70 * s * math.sin(an) * 0.8
        c.drawLine(x, y, hx, hy, paint((200, 210, 230), a, stroke=8 * s))
    for k in range(4):
        an = t * 0.8 + k * math.pi / 2 + 0.4
        hx, hy = x + 70 * s * math.cos(an), y + 70 * s * math.sin(an) * 0.8
        c.drawCircle(hx, hy, 22 * s, paint((240, 244, 252), a)); text(c, 'H', hx, hy + 9 * s, 26 * s, (40, 50, 80), a, 'bold')
    c.drawCircle(x, y, 36 * s, paint((60, 70, 90), a)); c.drawCircle(x, y, 36 * s, paint(GAS, a, stroke=4 * s))
    text(c, 'C', x, y + 12 * s, 34 * s, WHITE, a, 'bold')

def nose(c, x, y, s=1.0, a=1.0):
    if a <= 0.003: return
    p = skia.Path(); p.moveTo(x - 10 * s, y - 70 * s); p.cubicTo(x + 10 * s, y - 30 * s, x + 40 * s, y + 10 * s, x + 44 * s, y + 30 * s)
    p.cubicTo(x + 46 * s, y + 46 * s, x + 20 * s, y + 52 * s, x, y + 44 * s)
    c.drawPath(p, paint(WHITE, a, stroke=7 * s))
    c.drawCircle(x + 14 * s, y + 38 * s, 6 * s, paint(WHITE, a))

def stink(c, x, y, s=1.0, a=1.0, t=0.0, color=ODOR):
    if a <= 0.003: return
    for k in range(3):
        ph = (t * 0.5 + k / 3) % 1
        xx = x + (k - 1) * 34 * s; yy = y - ph * 70 * s
        pts = [(xx + 10 * s * math.sin(j * 0.9 + t * 3 + k), yy - j * 8 * s) for j in range(9)]
        c.drawPath(polyline_path(pts), paint(color, a * math.sin(math.pi * ph), stroke=6 * s))

def egg(c, x, y, s=1.0, a=1.0):
    if a <= 0.003: return
    c.drawOval(skia.Rect(x - 34 * s, y - 46 * s, x + 34 * s, y + 40 * s), paint((240, 232, 210), a))
    c.drawPath(polyline_path([(x - 30 * s, y - 6 * s), (x - 14 * s, y - 18 * s), (x, y - 4 * s), (x + 14 * s, y - 18 * s), (x + 30 * s, y - 6 * s)]), paint((140, 120, 80), a, stroke=4 * s))

def tire(c, x, y, r, a=1.0):
    if a <= 0.003: return
    c.drawCircle(x, y, r, paint((36, 38, 46), a)); c.drawCircle(x, y, r, paint((90, 94, 106), a, stroke=r * 0.08))
    for k in range(16):
        an = k * math.pi / 8
        c.drawLine(x + r * 0.86 * math.cos(an), y + r * 0.86 * math.sin(an), x + r * 0.98 * math.cos(an), y + r * 0.98 * math.sin(an), paint((70, 74, 86), a, stroke=r * 0.07))
    c.drawCircle(x, y, r * 0.55, paint((170, 176, 190), a)); c.drawCircle(x, y, r * 0.18, paint((110, 116, 130), a))
    for k in range(5):
        an = k * 2 * math.pi / 5
        c.drawCircle(x + r * 0.36 * math.cos(an), y + r * 0.36 * math.sin(an), r * 0.07, paint((110, 116, 130), a))

def bicycle(c, x, y, s=1.0, a=1.0, t=0.0, color=(230, 236, 250)):
    """bike centred at (x,y) (y = axle height)"""
    if a <= 0.003: return
    p = paint(color, a, stroke=6 * s)
    for wx in (-60, 60):
        c.drawCircle(x + wx * s, y, 40 * s, p)
        an = t * 6
        c.drawLine(x + wx * s - 36 * s * math.cos(an), y - 36 * s * math.sin(an), x + wx * s + 36 * s * math.cos(an), y + 36 * s * math.sin(an), paint(color, a * 0.6, stroke=3 * s))
    fr = [(-60, 0), (-10, 0), (30, -60), (-30, -60), (-60, 0)]
    c.drawPath(polyline_path([(x + px * s, y + py * s) for px, py in fr]), p)
    c.drawLine(x - 10 * s, y, x - 30 * s, y - 60 * s, p)
    c.drawLine(x + 30 * s, y - 60 * s, x + 60 * s, y, p)
    c.drawLine(x + 30 * s, y - 60 * s, x + 24 * s, y - 80 * s, p); c.drawLine(x + 14 * s, y - 80 * s, x + 40 * s, y - 80 * s, p)
    c.drawLine(x - 30 * s, y - 60 * s, x - 34 * s, y - 72 * s, p); c.drawLine(x - 48 * s, y - 72 * s, x - 20 * s, y - 72 * s, p)
    # rider
    c.drawCircle(x - 6 * s, y - 150 * s, 16 * s, paint(color, a))
    c.drawPath(polyline_path([(x - 30 * s, y - 74 * s), (x - 10 * s, y - 132 * s), (x + 22 * s, y - 84 * s)]), paint(color, a, stroke=10 * s))
    lp = t * 6
    c.drawPath(polyline_path([(x - 30 * s, y - 74 * s), (x - 10 * s + 14 * s * math.cos(lp), y - 30 * s), (x - 10 * s + 18 * s * math.cos(lp), y + 0 * s + 10 * s * math.sin(lp))]), paint(color, a, stroke=8 * s))

def sun(c, x, y, r, a=1.0, t=0.0):
    if a <= 0.003: return
    c.drawCircle(x, y, r * 1.6, paint((255, 200, 80), a * 0.25, blur=r * 0.6))
    for k in range(10):
        an = k * math.pi / 5 + t * 0.3
        c.drawLine(x + r * 1.25 * math.cos(an), y + r * 1.25 * math.sin(an), x + r * 1.6 * math.cos(an), y + r * 1.6 * math.sin(an), paint((255, 200, 80), a, stroke=r * 0.14))
    c.drawCircle(x, y, r, paint((255, 206, 90), a))

def snowflake(c, x, y, r, a=1.0, t=0.0):
    if a <= 0.003: return
    p = paint((200, 230, 255), a, stroke=r * 0.14)
    for k in range(6):
        an = k * math.pi / 3 + t * 0.2
        ex, ey = x + r * math.cos(an), y + r * math.sin(an)
        c.drawLine(x, y, ex, ey, p)
        for sgn in (-1, 1):
            mx, my = x + r * 0.6 * math.cos(an), y + r * 0.6 * math.sin(an)
            c.drawLine(mx, my, mx + r * 0.3 * math.cos(an + sgn * 0.8), my + r * 0.3 * math.sin(an + sgn * 0.8), p)

def phone(c, x, y, s=1.0, a=1.0):
    if a <= 0.003: return
    rr(c, x - 30 * s, y - 55 * s, x + 30 * s, y + 55 * s, 10 * s, paint((40, 46, 60), a)); rr(c, x - 30 * s, y - 55 * s, x + 30 * s, y + 55 * s, 10 * s, paint((200, 210, 230), a, stroke=3 * s))
    rr(c, x - 22 * s, y - 42 * s, x + 22 * s, y + 38 * s, 4 * s, paint((90, 170, 255), a * 0.8))

def light_switch(c, x, y, s=1.0, a=1.0):
    if a <= 0.003: return
    rr(c, x - 40 * s, y - 64 * s, x + 40 * s, y + 64 * s, 8 * s, paint((236, 232, 220), a))
    rr(c, x - 12 * s, y - 30 * s, x + 12 * s, y + 30 * s, 4 * s, paint((210, 204, 190), a)); rr(c, x - 12 * s, y - 30 * s, x + 12 * s, y + 30 * s, 4 * s, paint((150, 144, 130), a, stroke=2))

def match(c, x, y, s=1.0, a=1.0, t=0.0):
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.rotate(20)
    rr(c, -5 * s, -10 * s, 5 * s, 90 * s, 3 * s, paint((220, 190, 140), a)); c.drawOval(skia.Rect(-9 * s, -24 * s, 9 * s, -2 * s), paint((200, 60, 50), a))
    c.restore()
    fire_flame(c, x - 4 * s, y - 20 * s, 0.6 * s, a, t)

def door(c, x, gy, s=1.0, a=1.0, open_=0.0):
    if a <= 0.003: return
    rr(c, x - 60 * s, gy - 220 * s, x + 60 * s, gy, 4 * s, paint((20, 26, 44), a))
    w = 120 * s * (1 - 0.7 * open_)
    grad_rr(c, x - 60 * s, gy - 220 * s, x - 60 * s + w, gy, 4 * s, (140, 100, 70), (100, 70, 50), a, (70, 50, 36), 2)
    c.drawCircle(x - 60 * s + w - 16 * s, gy - 110 * s, 6 * s, paint((240, 210, 120), a))

def arrow_r(c, x0, y, x1, color, a=1.0, w=6):
    arrow(c, (x0, y), (x1, y), color, w, a, glow=False)

# ---------------------------------------------------------------- pressure staircase
STAGES = [('Pipeline', 'up to ~1,500', 1500), ('City gate', '≤ ~300', 300), ('Street', '≤ ~60', 60), ('Home', '~¼', 0.25)]
def _py(p, y0, y1, lo=0.1, hi=2500):
    return y1 - (math.log10(p) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (y1 - y0)

def stairs(c, x0, y0, x1, y1, a=1.0, upto=0.0, t=0.0, tire_a=0.0, title=True, big=False, xs=None, names=True, hl=None):
    """log-scale pressure staircase in box (x0,y0)-(x1,y1). upto: float stage progress (0..3), partial drops animate."""
    if a <= 0.003: return
    pad = 22 if not big else 30
    card(c, x0, y0, x1, y1, a, (70, 95, 150), (10, 18, 40))
    ts = 26 if not big else 30
    if title: text(c, 'GAS PRESSURE (psi)', x0 + pad, y0 + pad + ts * 0.8, ts - 2, MUTED, a, 'semi', 'left')
    gy0 = y0 + pad + (44 if title else 10) + (8 if big else 0); gy1 = y1 - (54 if names else 20)
    n = len(STAGES)
    if xs is None:
        sw = (x1 - x0 - 2 * pad) / n
        xs = [(x0 + pad + i * sw, x0 + pad + (i + 1) * sw) for i in range(n)]
    lo, hi = 0.12, 2600
    Y = lambda p: _py(p, gy0 + 34, gy1, lo, hi)
    # baseline
    c.drawLine(x0 + pad, gy1, x1 - pad, gy1, paint((90, 110, 160), a * 0.6, stroke=2))
    if tire_a > 0.003:
        ty = Y(35)
        for xx in np.arange(x0 + pad, x1 - pad, 22):
            c.drawLine(xx, ty, min(xx + 12, x1 - pad), ty, paint((255, 214, 102), a * tire_a * 0.9, stroke=3))
        text(c, 'car tire ~35', x0 + pad + 4, ty + 30, 24, (255, 214, 102), a * tire_a, 'semi', 'left')
    pts = []
    vs = ts if not big else 32
    # ghost of the whole staircase
    gp = []
    for i, (nm, val, p) in enumerate(STAGES):
        gp += [(xs[i][0], Y(p)), (xs[i][1], Y(p))]
    gpath = polyline_path(gp)
    c.drawPath(gpath, paint((120, 150, 200), a * 0.22, stroke=3))
    for i, (nm, val, p) in enumerate(STAGES):
        if names and upto <= i - 1: text(c, nm, (xs[i][0] + xs[i][1]) / 2, y1 - 20, 24 if not big else 28, (120, 140, 180), a * 0.45, 'semi')
    for i, (nm, val, p) in enumerate(STAGES):
        u = clamp(upto - i + 1) if i > 0 else clamp(upto + 1)
        if u <= 0: break
        xa, xb = xs[i]
        yv = Y(p)
        if i > 0:
            yprev = Y(STAGES[i - 1][2])
            yy = lerp(yprev, yv, eio(u))
            pts += [(xa, yy)]
        else: yy = yv
        pts += [(xa, yy), (xb, yy)]
        cur = (hl == i) if hl is not None else (i == int(min(3, math.floor(upto + 1e-6))))
        ca = a * (0.3 + 0.7 * smooth(u))
        colr = GAS if cur else (150, 190, 230)
        text(c, val, (xa + xb) / 2, yy - 16, vs, WHITE if cur else (190, 205, 235), ca, 'bold')
        if names: text(c, nm, (xa + xb) / 2, y1 - 20, 24 if not big else 28, colr, ca, 'semi')
    if len(pts) >= 2:
        P = polyline_path(pts)
        c.drawPath(P, paint(GAS, a * 0.45, stroke=14, blur=8)); c.drawPath(P, paint(GAS, a, stroke=6))
        ex, ey = pts[-1]
        c.drawCircle(ex, ey, 10, paint(WHITE, a))
