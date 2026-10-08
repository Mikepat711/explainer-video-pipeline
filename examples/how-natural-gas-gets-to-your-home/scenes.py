import math, skia, numpy as np
from lib import *
from art import rr, grad_rr, label, card, flow_cont, sag, house_icon, person, xmark, tick, bump, HOUSE_W, HOUSE_E, ROOF, LIT, RED, WATER
from art import flame as fire_flame
from art_gas import *
from art_pro import *

def F(t, a, d=0.5): return smooth(prog(t, a, d))
def FO(t, a, d=0.5, out=None, dout=0.5): return fade(t, a, d, out, dout)
def popin(t, a, d=0.45): return eback(prog(t, a, d))

def scaled(c, x, y, s, fn):
    c.save(); c.translate(x, y); c.scale(s, s); c.translate(-x, -y); fn(); c.restore()

def sky(c, y1, a=1.0):
    sh = skia.GradientShader.MakeLinear([(0, 100), (0, y1)], [col((20, 34, 70), 0), col((34, 56, 104), a * 0.5)])
    c.drawRect(skia.Rect(0, 100, W, y1), skia.Paint(AntiAlias=True, Shader=sh))

# ======================================================================= 0 hook
HW_STOVE = (1640, 598)          # world position of stove top (scale 0.08)
HOOK_PATH = [(1652, 600), (1652, 636), (1700, 636), (1700, 652), (1795, 652), (1795, 600), (1830, 600)]
def hook_world(c, t, flow, fl):
    GYW = 640
    # sky + ground
    soil(c, -200, GYW, 2200, 980, 1.0)
    # far landscape: hills
    hp = skia.Path(); hp.moveTo(-200, GYW)
    for x in range(-200, 2201, 40): hp.lineTo(x, GYW - 40 - 30 * math.sin(x / 170) - 18 * math.sin(x / 61))
    hp.lineTo(2200, GYW); hp.close(); c.drawPath(hp, paint((30, 46, 82), 1.0))
    # well, plant, compressors, city gate
    wellhead(c, 110, GYW, 0.45)
    plant_icon(c, 360, GYW, 0.5, 1.0, t)
    compressor(c, 700, GYW, 0.45, 1.0, t)
    compressor(c, 1010, GYW, 0.45, 1.0, t)
    mini_station(c, 1180, 1300, GYW, 64, 1.0, 0.36)
    # pipe network (underground)
    path = [(110, GYW), (110, 760), (360, 760), (360, 740), (1240, 740), (1240, 700), (1500, 700), (1500, 668), (1640, 668), (1640, 637)]
    pipe(c, path, 10, 1.0, 'steel', 1.0, flow, t, 34, 90, GAS, glow=0.6 * flow)
    hook_house(c)
    stove(c, HW_STOVE[0], HW_STOVE[1], 0.08, 1.0, -math.pi / 2 if fl > 0 else 0, fl, t)

def hook_house(c):
    x0, x1 = 1520, 1880; GYW = 640; ow = 0.5
    contact(c, 1700, GYW, 200, 6, 1.0, 0.4)
    # chimney + roof
    box(c, 1790, 372, 1814, 430, (150, 82, 70), 1.0, 1, ow=ow)
    roof = poly_path([(x0 - 30, 470), ((x0 + x1) / 2, 360), (x1 + 30, 470)])
    c.drawPath(roof, lin((0, 360), (0, 470), [(98, 66, 96), (64, 42, 70)]))
    c.save(); c.clipPath(roof, skia.ClipOp.kIntersect, True)
    for k in range(1, 8): c.drawLine(x0 - 40, 360 + k * 14, x1 + 40, 360 + k * 14, paint((40, 24, 46), 0.5, stroke=1.2))
    c.restore()
    c.drawPath(polyline_path([(x0 - 34, 473), ((x0 + x1) / 2, 356), (x1 + 34, 473)]), paint((210, 200, 220), 1, stroke=4))
    # exterior wall with siding
    wall = skia.Rect(x0, 470, x1, GYW)
    c.drawRect(wall, lin((0, 470), (0, GYW), [(64, 88, 140), (44, 62, 104)]))
    for yy in range(478, GYW, 10): c.drawLine(x0, yy, x1, yy, paint((30, 44, 80), 0.5, stroke=1))
    c.drawRect(wall, paint((24, 34, 64), 1, stroke=1.5))
    # outside window (lit)
    c.drawRect(skia.Rect(1714, 514, 1806, 586), paint(LIT, 0.35, blur=10))
    c.drawRect(skia.Rect(1720, 520, 1800, 580), lin((0, 520), (0, 580), [(255, 228, 150), (255, 190, 100)]))
    c.drawRect(skia.Rect(1720, 520, 1800, 580), paint((236, 236, 244), 1, stroke=3))
    c.drawLine(1760, 520, 1760, 580, paint((236, 236, 244), 1, stroke=2)); c.drawLine(1720, 550, 1800, 550, paint((236, 236, 244), 1, stroke=2))
    # kitchen cutaway
    c.drawRect(skia.Rect(1580, 490, 1700, GYW), lin((0, 490), (0, GYW), [(84, 92, 128), (62, 70, 104)]))
    c.drawRect(skia.Rect(1580, 490, 1700, GYW), paint((24, 34, 64), 1, stroke=1.2))
    # backsplash tiles
    c.drawRect(skia.Rect(1580, 548, 1700, 594), paint((150, 170, 196)))
    for j in range(8):
        yy = 548 + j * 5.75
        c.drawLine(1580, yy, 1700, yy, paint((110, 128, 156), 1, stroke=0.4))
        for k in range(14):
            xx = 1580 + k * 9 + (4.5 if j % 2 else 0)
            c.drawLine(xx, yy, xx, yy + 5.75, paint((110, 128, 156), 1, stroke=0.4))
    # lower cabinets + counters
    for xa, xb in ((1584, 1618), (1662, 1698)):
        box(c, xa, 599, xb, 637, (214, 200, 176), 1.0, 0.8, ow=ow, k=0.08)
        xm = (xa + xb) / 2
        c.drawLine(xm, 601, xm, 635, paint((150, 136, 112), 1, stroke=0.5))
        for hx in (xm - 2.5, xm + 2.5): c.drawLine(hx, 606, hx, 612, paint((90, 96, 110), 1, stroke=0.9))
        c.drawRect(skia.Rect(xa - 1.5, 593.5, xb + 1.5, 599), lin((0, 593.5), (0, 599), [(246, 244, 238), (196, 192, 184)]))
        c.drawLine(xa - 1.5, 599, xb + 1.5, 599, paint((120, 116, 108), 1, stroke=0.5))
        # upper cabinets
        box(c, xa, 500, xb, 546, (214, 200, 176), 1.0, 0.8, ow=ow, k=0.08)
        c.drawLine(xm, 502, xm, 544, paint((150, 136, 112), 1, stroke=0.5))
        for hx in (xm - 2.5, xm + 2.5): c.drawLine(hx, 536, hx, 542, paint((90, 96, 110), 1, stroke=0.9))
    # stainless hood
    box(c, 1632, 490, 1648, 524, (196, 202, 214), 1.0, 0.5, ow=ow, k=0.15)
    hood = poly_path([(1628, 524), (1652, 524), (1664, 538), (1616, 538)])
    c.drawPath(hood, lin((0, 524), (0, 538), [(226, 230, 238), (160, 166, 180)])); c.drawPath(hood, paint((100, 106, 120), 1, stroke=ow))
    c.drawRect(skia.Rect(1620, 538, 1660, 552), paint((255, 236, 180), 0.25, blur=4))
    # floor
    c.drawRect(skia.Rect(1580, 637, 1700, 641), lin((0, 637), (0, 641), [(150, 104, 66), (110, 74, 46)]))

def hook(c, t, T):
    S = T.s
    tk = T.w('turn', 0.75)
    ang = -math.pi / 2 * eio(prog(t, tk + 0.1, 0.6))
    tf = T.w('flame', 2.6) - 0.15
    fl = smooth(prog(t, tf, 0.35))
    zu = eio(prog(t, S[1] + 0.2, 4.2))
    Z = math.exp(lerp(math.log(15.0), 0.0, zu))
    px_, py_ = lerp(960, HW_STOVE[0], zu), lerp(420, HW_STOVE[1], zu)   # stove's screen position
    c.save(); c.translate(px_ - Z * HW_STOVE[0], py_ - Z * HW_STOVE[1]); c.scale(Z, Z)
    hook_world(c, t, F(t, S[1] + 1.6, 1.2), fl)
    # override knob angle on the stove itself
    stove(c, HW_STOVE[0], HW_STOVE[1], 0.08, 1.0, ang, fl, t)
    c.restore()
    ta = F(t, S[2] - 0.1, 0.8)
    if ta > 0:
        c.drawRect(skia.Rect(0, 140, W, 330), paint((6, 11, 26), 0.55 * ta, blur=30))
        text(c, 'How Natural Gas', 960, 215, 76, WHITE, ta, 'bold')
        text(c, 'Gets to Your Home', 960, 305, 76, GAS, ta, 'bold')

# ======================================================================= 1 source
LAYERS = [((150, 120, 92), (120, 94, 70)), ((170, 140, 100), (140, 112, 78)), ((120, 100, 86), (96, 80, 68)), ((160, 130, 96), (126, 100, 74))]
def source(c, t, T):
    S = T.s
    aA = 1 - F(t, S[3] - 0.5, 0.6)
    aB = F(t, S[3] - 0.5, 0.6)
    if aA > 0.003:
        sea_top, bed = 130, 470
        # water
        sh = skia.GradientShader.MakeLinear([(0, sea_top), (0, bed)], [col((40, 110, 170), aA * 0.55), col((20, 60, 110), aA * 0.8)])
        c.drawRect(skia.Rect(0, sea_top, W, bed), skia.Paint(AntiAlias=True, Shader=sh))
        for k in range(5):
            yy = sea_top + 8 + 6 * math.sin(t * 1.5 + k)
            c.drawLine(0 + k * 400, yy, 260 + k * 400, yy, paint((160, 210, 255), aA * 0.35, stroke=3))
        bury = eio(prog(t, S[1] + 1.4, 4.0))
        org_y = lerp(bed, bed + 240, bury)
        # sediment layers stacking on top of the organic layer
        nl = 4
        for i in range(nl):
            u = eio(prog(t, S[1] + 1.4 + i * 0.95, 1.1))
            if u <= 0: continue
            th = 60
            ytop = org_y - (i + 1) * th
            ytop = lerp(sea_top + 10, ytop, u)
            top, bot = LAYERS[i % 4]
            sh = skia.GradientShader.MakeLinear([(0, ytop), (0, ytop + th)], [col(top, aA), col(bot, aA)])
            pth = skia.Path(); pth.moveTo(0, ytop)
            for x in range(0, W + 1, 60): pth.lineTo(x, ytop + 5 * math.sin(x / 140 + i))
            pth.lineTo(W, ytop + th); pth.lineTo(0, ytop + th); pth.close()
            c.drawPath(pth, skia.Paint(AntiAlias=True, Shader=sh))
        # mud below
        soil(c, 0, org_y + 26, W, 900, aA, grass=False, top=(70, 56, 44), bot=(36, 28, 24))
        # organic layer -> gas
        cook = smooth(prog(t, S[2] + 0.6, 2.0))
        oc = lerpc((60, 130, 70), (50, 50, 58), cook)
        c.drawRect(skia.Rect(0, org_y, W, org_y + 26), paint(oc, aA))
        # drifting organisms
        rng = np.random.default_rng(5)
        for k in range(46):
            x0 = rng.uniform(40, W - 40); y0 = rng.uniform(sea_top + 30, bed - 40); ph = rng.uniform(0, 6)
            sink = smooth(prog(t, 0.6 + rng.uniform(0, 1.6), 2.6))
            x = x0 + 10 * math.sin(t * 0.8 + ph); y = lerp(y0, bed - 4, sink)
            aa = aA * (1 - F(t, S[1] + 1.4 + rng.uniform(0, 1.0), 0.6))
            if k % 3 == 0:
                c.drawOval(skia.Rect(x - 12, y - 5, x + 12, y + 5), paint((110, 210, 120), aa))
            elif k % 3 == 1:
                c.drawCircle(x, y, 6, paint((150, 230, 200), aa)); c.drawCircle(x, y, 9, paint((150, 230, 200), aa * 0.5, stroke=2))
            else:
                c.drawPath(polyline_path([(x - 8, y), (x, y - 8), (x + 8, y), (x, y + 8), (x - 8, y)]), paint((200, 240, 160), aa, stroke=2.5))
        label(c, 'Tiny plants and animals', 960, 330, (150, 230, 170), aA * FO(t, 0.9, 0.5, S[1] + 1.4, 0.5), 30)
        label(c, 'Millions of years', 960, 200, GOLD, aA * FO(t, S[1] + 0.3, 0.5, S[2] - 0.3), 32)
        # heat and pressure
        ha = aA * F(t, S[2] - 0.1, 0.6)
        if ha > 0:
            gl = skia.GradientShader.MakeLinear([(0, 900), (0, org_y)], [col(HEAT, ha * 0.55), col(HEAT, 0)])
            c.drawRect(skia.Rect(0, org_y, W, 900), skia.Paint(AntiAlias=True, Shader=gl))
            for k, x in enumerate((420, 960, 1500)):
                arrow(c, (x, 120 + 10 * math.sin(t * 3 + k)), (x, 200 + 10 * math.sin(t * 3 + k)), WHITE, 10, ha, glow=False)
            label(c, 'Pressure', 600, 160, WHITE, ha, 30)
            for k, x in enumerate((300, 760, 1200, 1660)):
                ph = (t * 0.7 + k * 0.3) % 1
                pts = [(x + 10 * math.sin(j * 0.8 + t * 4), 860 - ph * 60 - j * 10) for j in range(8)]
                c.drawPath(polyline_path(pts), paint(HEAT, ha * math.sin(math.pi * ph), stroke=6))
            label(c, 'Heat', 1360, 850, HEAT, ha, 30)
            # gas bubbles from the cooked layer
            for k in range(26):
                x = (k * 73.3) % W
                ph = (t * 0.4 + k * 0.137) % 1
                ba = ha * cook * math.sin(math.pi * ph)
                c.drawCircle(x + 6 * math.sin(t * 3 + k), org_y + 13 - ph * 14, 5 + 3 * ph, paint(GAS, ba))
            label(c, 'Gas', 1660, org_y - 24 if org_y > 600 else org_y + 60, GAS, ha * cook, 30)
    if aB > 0.003:
        a = aB; GY = 300
        sky(c, GY, a)
        hp = skia.Path(); hp.moveTo(0, GY)
        for x in range(0, W + 1, 40): hp.lineTo(x, GY - 26 - 20 * math.sin(x / 210) - 10 * math.sin(x / 71))
        hp.lineTo(W, GY); hp.close(); c.drawPath(hp, paint((30, 46, 82), a))
        bands = [(GY, 380, (96, 74, 54)), (380, 470, (128, 104, 80)), (470, 560, (104, 88, 76)), (560, 650, (140, 116, 88)), (650, 740, (64, 62, 70)), (740, 900, (92, 76, 62))]
        for i, (y0, y1, cc) in enumerate(bands):
            pth = skia.Path(); pth.moveTo(0, y0 + (4 * math.sin(i) if i else 0))
            for x in range(0, W + 1, 60): pth.lineTo(x, y0 + (6 * math.sin(x / 190 + i * 2) if i else 0))
            for x in range(W, -1, -60): pth.lineTo(x, y1 + (6 * math.sin(x / 190 + i * 2 + 2) if i < len(bands) - 1 else 0))
            pth.close(); c.drawPath(pth, paint(cc, a))
        c.drawLine(0, GY, W, GY, paint(GRASS, a, stroke=6))
        # shale layer highlight
        sh_a = a * F(t, S[4] - 0.1, 0.6)
        if sh_a > 0:
            c.drawRect(skia.Rect(0, 652, W, 738), paint((180, 200, 255), sh_a * 0.12))
            c.drawLine(0, 652, W, 652, paint((180, 200, 255), sh_a * 0.6, stroke=2)); c.drawLine(0, 738, W, 738, paint((180, 200, 255), sh_a * 0.6, stroke=2))
            label(c, 'Shale', 240, 695, WHITE, sh_a, 30, border=(180, 200, 255))
        # gas in rock
        ga = a * F(t, S[3] - 0.1, 0.8)
        rng = np.random.default_rng(11)
        for k in range(90):
            x = rng.uniform(380, 1880); y = rng.uniform(664, 728)
            c.drawCircle(x, y, rng.uniform(3, 6), paint(GAS, ga * (0.55 + 0.3 * math.sin(t * 2 + k))))
        # trapped pocket in sandstone (conventional)
        pocket = skia.Path(); pocket.moveTo(1180, 640); pocket.cubicTo(1260, 560, 1460, 560, 1540, 640); pocket.close()
        c.drawPath(pocket, paint(GAS, ga * 0.45)); c.drawPath(pocket, paint(GAS, ga * 0.9, stroke=2.5))
        label(c, 'Gas trapped in rock', 1360, 520, GAS, ga * FO(t, S[3] + 0.2, 0.5, S[5] - 0.2), 28)
        # depth bracket
        da = a * F(t, T.w('mile', S[3] + 1.4) - 0.1)
        if da > 0:
            c.drawLine(1820, GY + 6, 1820, 694, paint(WHITE, da, stroke=3))
            for yy in (GY + 6, 694): c.drawLine(1804, yy, 1836, yy, paint(WHITE, da, stroke=3))
            label(c, 'A mile or more', 1640, 460, WHITE, da, 28)
        # well: vertical then horizontal
        wx = 560
        wg = eio(prog(t, S[5] - 0.2, 2.0))
        wpath = [(wx, GY), (wx, 640), (wx + 30, 690), (wx + 120, 696), (1500, 696)]
        if wg > 0:
            P = partial_polyline(wpath, wg)
            c.drawPath(polyline_path(P), paint((30, 34, 44), a, stroke=16)); c.drawPath(polyline_path(P), paint((180, 190, 210), a, stroke=8))
            bx, by = P[-1]
            if wg < 1: c.drawCircle(bx, by, 14, paint(WHITE, a * 0.9, blur=6))
        fa = a * FO(t, T.w('water', S[5] + 2.2) - 0.1, 0.4, S[6] + 0.5, 0.8)
        if fa > 0:
            flow_cont(c, wpath, t, (90, 170, 255), 42, 260, 5, fa)
            crack = smooth(prog(t, T.w('crack', S[5] + 3.6) - 0.1, 1.0))
            rng2 = np.random.default_rng(4)
            for k in range(16):
                x = 760 + k * 46
                ln = 28 * crack
                for sg in (-1, 1):
                    pts = [(x, 696), (x + rng2.uniform(-8, 8), 696 + sg * ln * 0.5), (x + rng2.uniform(-10, 10), 696 + sg * ln)]
                    c.drawPath(polyline_path(pts), paint(WHITE, fa * crack * 0.8, stroke=2.5))

        label(c, 'Fracking: water and sand crack the shale', 1060, 800, (130, 190, 255), a * FO(t, T.w('fracking', S[5] + 1.0) - 0.1, 0.5, S[6] + 0.4), 28)
        # gas up the well + wellhead
        ua = a * F(t, S[6] - 0.1, 0.6)
        if ua > 0:
            flow_cont(c, wpath[::-1], t, GAS, 40, 220, 5.5, ua)
        wa = a * popin(t, T.w('wellhead', S[6] + 1.6) - 0.3)
        ra = a * FO(t, S[5] - 0.6, 0.5, T.w('wellhead', S[6] + 1.6) - 0.6, 0.4)
        if ra > 0: drill_rig(c, wx, GY, 0.5, ra, t, run=1.0)
        if wa > 0:
            scaled(c, wx, GY, clamp(wa, 0, 1.2), lambda: wellhead(c, wx, GY, 0.7, a, glow=0.6))
            label(c, 'Wellhead', wx + 190, GY - 90, (255, 150, 120), a * F(t, T.w('wellhead', S[6] + 1.6)), 30)

# ======================================================================= 2 gathering
G_T1 = [(200, 260), (420, 330), (640, 390), (860, 470), (1100, 525), (1330, 545)]
G_T2 = [(230, 730), (470, 650), (690, 565), (860, 470)]
G_T3 = [(640, 840), (830, 720), (1000, 610), (1100, 525)]
G_SP = [((390, 165), (420, 330)), ((610, 230), (640, 390)), ((800, 290), (860, 470)), ((380, 830), (470, 650)), ((560, 470), (690, 565)),
        ((1010, 790), (1000, 610)), ((1040, 360), (1100, 525)), ((180, 470), (420, 330))]
def gathering(c, t, T):
    S = T.s
    a = 1.0
    grad_rr(c, 110, 125, 1810, 890, 26, (26, 48, 46), (18, 34, 38), a, (60, 100, 90), 2)
    rng = np.random.default_rng(2)
    for k in range(70):
        x, y = rng.uniform(140, 1780), rng.uniform(150, 870)
        c.drawCircle(x, y, rng.uniform(4, 10), paint((50, 80, 66), 0.6))
    wells = [G_T1[0], G_T2[0], G_T3[0]] + [s for s, _ in G_SP]
    lg = eio(prog(t, S[1] - 0.1, 2.0)); fl = F(t, S[1] + 1.4, 0.8)
    for s_, e_ in G_SP: pipe(c, [s_, e_], 6, a, 'steel', lg, fl, t, 30, 70)
    pipe(c, G_T2, 9, a, 'steel', lg, fl, t, 34, 90); pipe(c, G_T3, 9, a, 'steel', lg, fl, t, 34, 90)
    pipe(c, G_T1, 12, a, 'steel', lg, fl, t, 36, 110)
    mg = eio(prog(t, S[2] - 0.2, 1.2))
    pipe(c, [G_T1[-1], (1520, 545)], 16, a, 'steel', mg, F(t, S[2] + 0.6), t, 40, 120)
    for i, (x, y) in enumerate(wells):
        pa = popin(t, S[0] + 0.15 * i - 0.2)
        if pa > 0: tiny_well(c, x, y, clamp(pa, 0, 1.3), min(1, pa))
    label(c, 'Wells', 300, 170, (255, 150, 120), F(t, S[0] + 0.6), 30)
    label(c, 'Gathering lines', 760, 470 - 70, GAS, F(t, S[1] + 0.8), 30)
    pa = popin(t, S[2] + 0.3)
    if pa > 0:
        grad_rr(c, 1500, 380, 1760, 680, 22, (30, 46, 80), (20, 30, 56), min(1, pa), (110, 140, 200), 2)
        scaled(c, 1630, 620, clamp(pa, 0, 1.2), lambda: plant_icon(c, 1650, 620, 0.55, min(1, pa), t))
        label(c, 'Processing plant', 1630, 730, WHITE, F(t, S[2] + 0.6), 30)

# ======================================================================= 3 processing
PAL = [GAS, GAS, (90, 150, 255), GAS, (255, 150, 60), GAS, (160, 160, 170), GAS, (250, 220, 80), GAS]
def mixed_flow(c, pts, t, a, spacing=34, speed=120, r=7, onlygas=False):
    d = [0]
    for i in range(1, len(pts)): d.append(d[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    L = d[-1]; n = int(L / spacing) + 1
    base = t * speed
    for k in range(-2, n + 2):
        idx = int(math.floor(base / spacing)) - k
        s = (base % spacing) + k * spacing
        if s < 0 or s > L: continue
        i = max(1, min(len(pts) - 1, int(np.searchsorted(d, s))))
        kk = (s - d[i - 1]) / max(d[i] - d[i - 1], 1e-9)
        x = lerp(pts[i - 1][0], pts[i][0], kk); y = lerp(pts[i - 1][1], pts[i][1], kk) + 5 * math.sin(idx * 2.1)
        cc = GAS if onlygas else PAL[idx % len(PAL)]
        ea = min(1, s / 40, (L - s) / 40)
        c.drawCircle(x, y, r * 2, paint(cc, a * ea * 0.35, blur=r)); c.drawCircle(x, y, r, paint(cc, a * ea))

def processing(c, t, T):
    S = T.s
    GY = 660
    c.drawLine(0, GY, W, GY, paint((110, 140, 200), 0.5, stroke=2))
    pipe(c, [(-20, 600), (760, 600)], 30, 1, 'steel')
    mixed_flow(c, [(-20, 600), (760, 600)], t, 1.0)
    label(c, 'Raw gas: a messy mix', 380, 520, WHITE, FO(t, 0.2, 0.5, S[2] + 0.5), 28)
    pipe(c, [(1160, 600), (1940, 600)], 30, 1, 'steel', glow=0.6 * F(t, S[2]))
    mixed_flow(c, [(1160, 600), (1940, 600)], t, F(t, S[2] - 0.3, 0.8), onlygas=True)
    plant_icon(c, 960, GY, 1.05, 1, t, glow=F(t, S[0]) * 0.5)
    # outputs
    wa = F(t, T.w('water', S[0] + 1.0) - 0.1)
    if wa > 0:
        pipe(c, [(820, 660), (820, 770), (640, 770)], 12, wa, 'dark')
        for k in range(3):
            ph = (t * 0.8 + k / 3) % 1
            drop_icon(c, 600 - ph * 0, 760 + ph * 60, 12, wa * (1 - ph), WATER)
        label(c, 'Water', 530, 770, WATER, wa, 28, align='right')
    ia = F(t, T.w('impurities', S[0] + 1.7) - 0.1)
    if ia > 0:
        pipe(c, [(900, 660), (900, 850), (640, 850)], 12, ia, 'dark')
        for k in range(7): c.drawCircle(600 - (k % 4) * 14, 856 - (k // 4) * 12, 7, paint((160, 160, 170), ia))
        label(c, 'Impurities', 530, 850, (190, 190, 200), ia, 28, align='right')
    pa = F(t, S[1] + 0.3)
    if pa > 0:
        pipe(c, [(1060, 660), (1060, 790), (1240, 790)], 12, pa, 'dark')
        tank(c, 1300, 850, 90, 130, pa, (255, 150, 60)); tank(c, 1410, 850, 90, 130, pa, (250, 210, 80))
        text(c, 'Propane', 1290, 705, 26, (255, 170, 90), pa, 'semi'); text(c, 'Butane', 1420, 705, 26, (250, 220, 100), pa, 'semi')
        label(c, 'Sold separately', 1640, 810, GOLD, F(t, T.w('sold', S[1] + 2.4) - 0.1), 28)
    ma = F(t, S[2] - 0.1)
    if ma > 0:
        methane(c, 1560, 330, 1.0, ma, t)
        label(c, 'Mostly methane', 1560, 480, GAS, ma, 30)
    na = F(t, S[3] - 0.1)
    if na > 0:
        card(c, 200, 140, 700, 420, na, (120, 140, 190))
        face_profile(c, 300, 286, 0.95, na, outfit=3)
        smell_toward(c, 500, 286, 392, 292, na * 0.9, t, (150, 200, 230))
        no_sign(c, 452, 290, 46, na)
        text(c, 'No smell', 600, 270, 34, WHITE, na, 'bold'); text(c, 'at all', 600, 315, 30, MUTED, na, 'semi')

# ======================================================================= 4 transmission
def transmission(c, t, T):
    S = T.s
    aA = 1 - F(t, S[1] - 0.4, 0.6)
    aB = FO(t, S[1] - 0.4, 0.6, S[2] - 0.45, 0.6)
    aC = F(t, S[2] - 0.45, 0.6)
    if aA > 0.003:
        a = aA; GY = 520
        soil(c, 0, GY, W, 900, a)
        cx, cy, R = 760, 720, 100
        dig = F(t, 0.3, 0.6)
        tr = skia.Path(); tr.moveTo(620, GY); tr.lineTo(900, GY); tr.lineTo(880, 850); tr.lineTo(640, 850); tr.close()
        c.drawPath(tr, paint((60, 46, 36), a * dig))
        pa = popin(t, T.w('transmission', 1.5) - 0.1)
        if pa > 0:
            rr_ = R * clamp(pa, 0, 1.15)
            c.drawCircle(cx + 4, cy + 10, rr_ + 6, paint((0, 0, 0), a * 0.5, blur=12))
            c.drawCircle(cx, cy, rr_, lin((cx - rr_, cy - rr_), (cx + rr_, cy + rr_), [(226, 232, 244), (160, 170, 188), (96, 104, 124)], a, [0, 0.45, 1]))
            c.drawCircle(cx, cy, rr_, paint((60, 66, 84), a, stroke=3))
            c.drawCircle(cx, cy, rr_ * 0.9, lin((cx, cy - rr_), (cx, cy + rr_), [(14, 22, 44), (34, 54, 92)], a))
            c.drawCircle(cx, cy, rr_ * 0.9, paint((70, 78, 98), a, stroke=3))
            c.drawCircle(cx, cy, rr_ * 0.9, paint(GAS, a * 0.35 * (0.8 + 0.2 * math.sin(t * 3))))
            rng = np.random.default_rng(1)
            for k in range(22):
                an = rng.uniform(0, 6.28); rd = rng.uniform(0, rr_ * 0.8)
                c.drawCircle(cx + rd * math.cos(an + t * 0.3), cy + rd * math.sin(an + t * 0.3), 5, paint(GAS, a * 0.9))
            label(c, 'Big steel pipe', cx, 470 - 20, WHITE, a * F(t, T.w('steel', 3.2) - 0.2), 30)
        da = a * F(t, T.w('four', 4.0) - 0.1)
        if da > 0:
            c.drawLine(600, cy - R, 600, cy + R, paint(GOLD, da, stroke=3))
            for yy in (cy - R, cy + R): c.drawLine(586, yy, 614, yy, paint(GOLD, da, stroke=3))
            label(c, 'Up to ~4 ft wide', 430, cy, GOLD, da, 28)
        pe = a * F(t, T.w('four', 4.0) + 0.3)
        if pe > 0:
            human(c, 1120, GY, 1.1, pe, outfit=0, hat=(250, 200, 40), vest=True)
            label(c, 'A 6-ft person', 1120, GY - 352, (170, 185, 215), pe, 26)
        ba = a * F(t, T.w('buried', 6.0) - 0.1)
        label(c, 'Buried', 1060, 760, (220, 190, 150), ba, 28)
    if aB > 0.003:
        a = aB; GY = 520
        off = (t - S[1]) * 260
        sky(c, GY, a)
        hp = skia.Path(); hp.moveTo(0, GY)
        for x in range(0, W + 41, 40):
            X = x + off * 0.5
            hp.lineTo(x, GY - 60 - 50 * math.sin(X / 230) - 20 * math.sin(X / 77))
        hp.lineTo(W, GY); hp.close(); c.drawPath(hp, paint((30, 46, 82), a))
        soil(c, 0, GY, W, 900, a)
        for k in range(-1, 12):
            x = (k * 220 - off) % 2400 - 200
            tr_ = (k * 37) % 3
            if tr_ == 0: marker_post(c, x, GY, 0.55, a)
            else:
                tree(c, x, GY, 0.8, a, shade=0.3 * tr_)
        pipe(c, [(-20, 640), (1940, 640)], 34, a, 'steel', 1, 1, t, 60, 200, glow=0.4)
        miles = clamp((t - S[1]) / 4.0) * 1000
        label(c, f'{int(miles // 50 * 50):,} miles', 960, 760, WHITE, a, 34)
        label(c, 'Hundreds to thousands of miles', 960, 200, GAS, a * F(t, T.w('hundreds', S[1] + 1.2) - 0.1), 30)
    if aC > 0.003:
        a = aC
        base, top = 820, 300
        hmax = base - top
        # pipeline bar
        pu = eout(prog(t, T.w('squeezed', S[2] + 1.2), 2.2))
        bx = 760
        h = hmax * pu
        c.drawRect(skia.Rect(bx - 80, base - h, bx + 80, base), paint(GAS, a * 0.85))
        c.drawRect(skia.Rect(bx - 80, base - h, bx + 80, base), paint(WHITE, a * 0.6, stroke=2))
        seg_lo = base - hmax * 200 / 1500
        ra_ = a * F(t, T.w('squeezed', S[2] + 1.2) + 2.0)
        if ra_ > 0:
            c.drawLine(870, base - hmax, 870, seg_lo, paint(WHITE, ra_, stroke=3))
            for yy in (base - hmax, seg_lo): c.drawLine(858, yy, 882, yy, paint(WHITE, ra_, stroke=3))
            text(c, 'Typical range:', 896, 430, 26, MUTED, ra_, 'semi', 'left')
            text(c, 'several hundred', 896, 466, 26, WHITE, ra_, 'semi', 'left')
            text(c, 'to ~1,500 psi', 896, 502, 26, WHITE, ra_, 'semi', 'left')
        text(c, f'{int(round(1500 * pu / 50) * 50):,} psi' if pu < 0.999 else 'up to ~1,500 psi', bx, base - h - 22, 40, WHITE, a * F(t, T.w('squeezed', S[2] + 1.2)), 'bold')
        text(c, 'Transmission pipeline', bx, base + 44, 28, GAS, a, 'semi')
        # car tire bar
        ta = a * F(t, S[3] - 0.1)
        tx = 1160
        th = hmax * 35 / 1500
        c.drawRect(skia.Rect(tx - 80, base - th * ta, tx + 80, base), paint(GOLD, ta))
        text(c, '~35 psi', tx, base - th - 22, 36, GOLD, ta, 'bold')
        tire(c, tx, base - 170, 90, ta)
        text(c, 'Car tire', tx, base + 44, 28, GOLD, ta, 'semi')
        c.drawLine(560, base, 1360, base, paint((110, 140, 200), a * 0.7, stroke=3))
        stairs(c, 1290, 110, 1860, 380, a * F(t, S[2] + 0.4, 0.6), upto=0.0, t=t, title=True)
        if False: pass

# ======================================================================= 5 compressors
def compressors(c, t, T):
    S = T.s
    aA = 1 - F(t, S[3] - 0.4, 0.6)
    aB = F(t, S[3] - 0.4, 0.6)
    if aA > 0.003:
        a = aA; GY = 440; py = 560
        sky(c, GY, a)
        soil(c, 0, GY, W, 640, a)
        st = [560, 1360]
        sa = [popin(t, S[1] + 0.4 + 0.5 * i) for i in range(2)]
        for i, x in enumerate(st):
            if sa[i] > 0:
                scaled(c, x, GY, clamp(sa[i], 0, 1.2), lambda x=x: compressor(c, x, GY, 0.7, a, t, glow=0.5 * bump(prog(t, S[1] + 0.4 + 0.5 * i, 1.5))))
                pipe(c, [(x - 40, GY), (x - 40, py), ], 10, a * min(1, sa[i]), 'steel')
                pipe(c, [(x + 40, GY), (x + 40, py)], 10, a * min(1, sa[i]), 'steel')
        pipe(c, [(-20, py), (1940, py)], 30, a, 'steel', 1, 1, t, 56, 170)
        # friction marks
        fa = a * FO(t, T.w('friction', 0.8), 0.5, S[1] + 0.2)
        for k in range(14):
            x = (k * 140 + t * 170) % (W + 100) - 50
            for sg in (-1, 1):
                c.drawLine(x, py + sg * 15, x - 22, py + sg * 15, paint(HEAT, fa * 0.9, stroke=3))
        label(c, 'Friction slowly drains pressure', 960, 320, HEAT, fa, 30)
        # pressure graph
        gx0, gx1, gy0, gy1 = 100, 1820, 680, 880
        ga = a * F(t, 0.6)
        card(c, gx0 - 20, gy0 - 20, gx1 + 20, gy1 + 10, ga, (60, 85, 140), (10, 18, 40))
        text(c, 'Pressure', gx0 + 10, gy0 + 22, 26, MUTED, ga, 'semi', 'left')
        hi, lo_ = gy0 + 50, gy1 - 30
        su = smooth(prog(t, S[1] + 0.4, 1.2))
        pts_a = [(x, lerp(hi, lo_, (x - gx0) / (gx1 - gx0))) for x in range(gx0, gx1 + 1, 20)]
        pts_b = []
        for x in range(gx0, gx1 + 1, 10):
            seg0 = gx0
            for sx in st:
                if x >= sx: seg0 = sx
            pts_b.append((x, lerp(hi, lo_, (x - seg0) / 1100)))
        dg = clamp(prog(t, 0.8, 2.6))
        P = [(x, lerp(ya, yb, su)) for (x, ya), (_, yb) in zip(pts_a[::1], [pts_b[i * 2] for i in range(len(pts_a))])]
        P = partial_polyline(P, dg) if dg < 1 else P
        if len(P) > 1:
            c.drawPath(polyline_path(P), paint(GAS, ga * 0.4, stroke=12, blur=6)); c.drawPath(polyline_path(P), paint(GAS, ga, stroke=5))
        for sx in st:
            label(c, 'Compressor station', sx, 170, WHITE, a * F(t, S[1] + 0.9), 28)
        ba = a * F(t, T.w('100', S[1] + 1.8, after=S[1]) - 0.2)
        if ba > 0:
            c.drawLine(600, 260, 1320, 260, paint(GOLD, ba, stroke=3))
            for xx in (600, 1320): c.drawLine(xx, 246, xx, 274, paint(GOLD, ba, stroke=3))
            label(c, 'Every ~40–100 miles', 960, 260, GOLD, ba, 28)
        bk = a * F(t, S[2] - 0.1)
        if bk > 0:
            bx = -100 + ((t - S[2] + 0.3) * 170) % (W + 200)
            bicycle(c, bx, GY - 42, 0.85, bk, t)
            label(c, 'About bicycle speed', 960, 360, WHITE, bk * FO(t, S[2] + 0.4, 0.5, S[3] - 0.4), 30)
    if aB > 0.003:
        a = aB
        x0, y0, x1, y1 = 110, 125, 1810, 890
        grad_rr(c, x0, y0, x1, y1, 26, (26, 52, 42), (20, 40, 36), a, (60, 100, 90), 2)
        def sy(x): return 470 + (x - 960) * 0.06
        # road
        rd = poly_path([(820, y0), (920, y0), (980, y1), (880, y1)])
        c.drawPath(rd, paint((70, 74, 84), a))
        for k in range(10):
            yy = y0 + 20 + k * 80
            xx = lerp(870, 930, (yy - y0) / (y1 - y0))
            c.drawLine(xx, yy, xx + 3, yy + 40, paint((240, 220, 120), a * 0.8, stroke=4))
        # field patch
        rr(c, 140, 620, 760, 860, 14, paint((70, 96, 52), a * 0.8))
        for k in range(8): c.drawLine(160, 640 + k * 28, 740, 640 + k * 28, paint((90, 120, 64), a * 0.8, stroke=3))
        # forest everywhere outside strip/road/field
        rng = np.random.default_rng(9)
        hw = 70
        sa = F(t, S[4] - 0.2, 0.8)
        for k in range(520):
            x, y = rng.uniform(x0 + 20, x1 - 20), rng.uniform(y0 + 20, y1 - 20)
            if abs(y - sy(x)) < hw + 14: continue
            if 790 < x < 1010: continue
            if 130 < x < 780 and 600 < y < 880: continue
            r = rng.uniform(14, 24)
            map_tree(c, x, y, r, a, k % 3)
        # strip
        strip = poly_path([(x0, sy(x0) - hw), (x1, sy(x1) - hw), (x1, sy(x1) + hw), (x0, sy(x0) + hw)])
        c.drawPath(strip, paint((110, 160, 96), a * 0.55))
        if sa > 0:
            c.drawPath(strip, paint(GOLD, a * sa * 0.12)); c.drawPath(strip, paint(GOLD, a * sa, stroke=3))
            label(c, 'Cleared right-of-way', 1400, sy(1400) - hw - 36, GOLD, a * sa, 30)
        # buried pipe (dashed)
        for xx in range(x0 + 10, x1 - 10, 36):
            c.drawLine(xx, sy(xx), xx + 20, sy(xx + 20), paint(GAS, a * 0.8, stroke=6))
        # posts (plan view)
        pa_ = F(t, S[3] - 0.1)
        posts = [(790, sy(790) - 40), (1010, sy(1010) + 40), (400, sy(400) - 48), (1300, sy(1300) - 48), (1640, sy(1640) - 48)]
        for i, (px, py_) in enumerate(posts):
            pp = popin(t, S[3] + 0.2 + i * 0.15)
            if pp > 0:
                rp = 13 * clamp(pp, 0, 1.3)
                c.drawCircle(px + 3, py_ + 4, rp, paint((0, 0, 0), a * 0.45, blur=3))
                c.drawCircle(px, py_, rp, rad(px - rp * 0.3, py_ - rp * 0.4, rp * 1.4, [(255, 200, 120), (250, 130, 40)], a)); c.drawCircle(px, py_, rp, paint((250, 210, 60), a, stroke=4))
        if pa_ > 0:
            card(c, 1460, 560, 1780, 870, a * pa_, (250, 206, 40))
            marker_post(c, 1540, 820, 1.25, a * pa_)
            text(c, 'Pipeline', 1670, 690, 28, WHITE, a * pa_, 'semi'); text(c, 'marker', 1670, 726, 28, WHITE, a * pa_, 'semi')
            c.drawLine(1460, 600, 1010 + 14, sy(1010) + 40 + 10, paint((250, 206, 40), a * pa_ * 0.6, stroke=2.5))

# ======================================================================= 6 storage
def storage(c, t, T):
    S = T.s
    GY = 380
    sky(c, GY)
    soil(c, 0, GY, W, 900, 1.0)
    winter = smooth(prog(t, S[3] - 0.2, 0.8))
    fill = lerp(0.15, 0.95, smooth(prog(t, S[1] + 0.3, S[3] - S[1] - 0.3))) if winter <= 0 else lerp(0.95, 0.35, smooth(prog(t, S[3] + 0.2, 2.2)))
    # depleted field: dome
    dome = skia.Path(); dome.moveTo(200, 800); dome.cubicTo(300, 560, 760, 560, 860, 800); dome.close()
    cap = skia.Path(); cap.moveTo(170, 800); cap.cubicTo(280, 520, 780, 520, 890, 800); cap.lineTo(860, 800); cap.cubicTo(760, 560, 300, 560, 200, 800); cap.close()
    c.drawPath(cap, paint((70, 66, 74))); c.drawPath(dome, paint((150, 122, 88)))
    rng = np.random.default_rng(3)
    for k in range(160):
        x = rng.uniform(220, 840); y = rng.uniform(600, 795)
        yy = 800 - (800 - y)
        inside = (y > 800 - (1 - ((x - 530) / 330) ** 2) * 200)
        if not inside: continue
        lvl = 800 - fill * 200
        c.drawCircle(x, y, 5, paint(GAS if y > lvl else (110, 90, 66), 0.9))
    # salt dome + cavern
    salt = skia.Path(); salt.moveTo(1150, 900); salt.cubicTo(1150, 520, 1250, 430, 1400, 430); salt.cubicTo(1550, 430, 1650, 520, 1650, 900); salt.close()
    c.drawPath(salt, paint(SALT, 0.9))
    cav = skia.RRect.MakeRectXY(skia.Rect(1330, 540, 1470, 840), 70, 70)
    c.drawRRect(cav, paint((30, 40, 60)))
    lvl = 840 - fill * 300
    c.save(); c.clipRRect(cav, True)
    c.drawRect(skia.Rect(1330, lvl, 1470, 840), paint(GAS, 0.8))
    c.restore(); c.drawRRect(cav, paint((140, 150, 170), stroke=3))
    # wells + surface pipe
    for wx, wy in ((530, 650), (1400, 560)):
        pipe(c, [(wx, GY - 10), (wx, wy)], 10, 1, 'steel')
    pipe(c, [(-20, GY - 30), (1400, GY - 30)], 16, 1, 'steel', 1, 1, t, 40, 120 * (1 - 2 * winter))
    for wx, wy in ((530, 650), (1400, 560)):
        wellhead(c, wx, GY, 0.3, 1.0)
    # flow arrows in wells
    for wx, wy in ((530, 650), (1400, 560)):
        dirn = 1 - 2 * winter
        for k in range(3):
            ph = (t * 0.9 + k / 3) % 1
            y = lerp(GY + 10, wy - 20, ph if dirn > 0 else 1 - ph)
            c.drawCircle(wx, y, 7, paint(GAS, 0.9 * math.sin(math.pi * ph)))
        aw = F(t, S[1] + 0.2) 
        if aw > 0:
            if winter < 0.5: arrow(c, (wx + 50, 440), (wx + 50, 540), GAS, 9, aw * (1 - 2 * winter), glow=False)
            else: arrow(c, (wx + 50, 540), (wx + 50, 440), GAS, 9, (2 * winter - 1), glow=False)
    label(c, 'Old gas field', 530, 860, WHITE, F(t, T.w('fields', S[2] + 1.0) - 0.3), 30)
    label(c, 'Salt cavern', 1400, 870, WHITE, F(t, T.w('salt', S[2] + 2.2) - 0.2), 30)
    # season + demand chart
    ca = FO(t, 0.4, 0.5, S[1] + 0.2)
    if ca > 0:
        card(c, 620, 100, 1300, 365, ca)
        use = [9, 8, 6, 4, 2.5, 2, 2, 2, 2.5, 4, 6.5, 8.5]
        for i, u in enumerate(use):
            x = 680 + i * 46; h = u * 14
            c.drawRect(skia.Rect(x, 318 - h, x + 32, 318), paint((255, 140, 90) if u > 5 else (120, 170, 230), ca))
        text(c, 'Home gas use, month by month', 960, 140, 26, MUTED, ca, 'semi')
        text(c, 'Winter', 742, 352, 24, (255, 160, 110), ca, 'semi'); text(c, 'Summer', 960, 352, 24, (140, 190, 240), ca, 'semi'); text(c, 'Winter', 1192, 352, 24, (255, 160, 110), ca, 'semi')
    sa_ = F(t, S[1] - 0.1) * (1 - winter)
    if sa_ > 0:
        sun(c, 900, 200, 50, sa_, t); label(c, 'Summer: fill up', 1110, 200, GOLD, sa_, 30, align='left')
    if winter > 0:
        snowflake(c, 900, 200, 55, winter, t); label(c, 'Winter: draw out', 1110, 200, (200, 230, 255), winter, 30, align='left')

# ======================================================================= 7 city gate
def citygate(c, t, T):
    S = T.s
    GY = 760; py = 600
    c.save(); c.translate(950, 610); c.scale(1.18, 1.18); c.translate(-950, -610)
    c.drawLine(-200, GY, W + 200, GY, paint((110, 140, 200), 0.5, stroke=2))
    fa = F(t, 0.3, 0.6)
    c.drawPath(rpath(280, 400, 1620, GY, 10), lin((0, 400), (0, GY), [(24, 38, 70), (18, 28, 54)], fa))
    c.drawRect(skia.Rect(280, GY - 22, 1620, GY), paint((70, 76, 92), fa * 0.8))
    # chain-link fence
    c.save(); c.clipRect(skia.Rect(280, 400, 1620, GY - 22))
    fp = paint((110, 130, 170), fa * 0.16, stroke=1.2)
    for k in range(0, 1800, 18):
        c.drawLine(280 + k, 400, 280 + k - 360, GY, fp); c.drawLine(280 + k - 360, 400, 280 + k, GY, fp)
    c.restore()
    for x in range(280, 1621, 134):
        c.drawLine(x, 396, x, GY - 22, paint((40, 50, 74), fa, stroke=7)); c.drawLine(x, 396, x, GY - 22, paint((140, 156, 196), fa, stroke=4))
    c.drawLine(280, 400, 1620, 400, paint((140, 156, 196), fa * 0.9, stroke=4)); c.drawLine(280, 430, 1620, 430, paint((110, 130, 170), fa * 0.4, stroke=2))
    label(c, 'City gate station', 950, 400, WHITE, F(t, T.w('gate', 3.0) - 0.2), 30)
    reg_t = S[1]; heat_t = S[2]; meas_t = T.w('measured', S[3] + 0.6); odor_t = T.w('mercaptan', S[3] + 2.4)
    drop = smooth(prog(t, reg_t + 0.3, 1.2))
    odor = smooth(prog(t, odor_t, 1.4))
    # pipes
    pipe(c, [(-200, py), (900, py)], 36, 1, 'steel', 1, 1, t, 44, 160, glow=0.25)
    out_c = lerpc(GAS, ODOR, odor)
    pipe(c, [(900, py), (1360, py)], 26, 1, 'steel', 1, 1, t, 64, 160 * (1 - 0.3 * drop) + 0.001)
    pipe(c, [(1360, py), (2140, py)], 26, 1, 'steel', 1, 1, t, 64, 112, dotc=out_c)
    # heater
    ha = F(t, heat_t - 0.1)
    line_heater(c, 470, 550, 630, 650, 1, t, ha)
    text(c, 'Heater', 550, 690, 28, HEAT if ha > 0.5 else WHITE, 1, 'semi')
    # regulators
    ra = bump(prog(t, reg_t - 0.2, 2.6))
    regulator(c, 780, py, 1.2, 1, glow=ra)
    regulator(c, 880, py, 0.9, 1, glow=ra)
    text(c, 'Regulators', 830, 690, 28, GAS if ra > 0.3 else WHITE, 1, 'semi')
    # frost after the regulators
    fr = F(t, heat_t + 0.2) * (1 - 0.6 * F(t, heat_t + 2.4, 1.0))
    if fr > 0:
        for k in range(12):
            x = 930 + k * 14; yy = py + (-1 if k % 2 else 1) * 18
            c.drawLine(x - 6, yy - 6, x + 6, yy + 6, paint((220, 240, 255), fr, stroke=3)); c.drawLine(x - 6, yy + 6, x + 6, yy - 6, paint((220, 240, 255), fr, stroke=3))
        label(c, 'Expanding gas gets cold', 1010, 462, (200, 230, 255), fr * (1 - F(t, S[3] - 0.3)), 26)
    # meter
    ma = bump(prog(t, meas_t - 0.3, 2.2))
    gas_meter(c, 1120, py - 10, 0.7, 1, t, spin=4 * F(t, meas_t - 0.3), glow=ma)
    text(c, 'Meter', 1120, 690, 28, GAS if ma > 0.3 else WHITE, 1, 'semi')
    # odorizer
    oa = bump(prog(t, odor_t - 0.3, 2.6))
    odorizer(c, 1360, py, 1, t, odor, oa)
    text(c, 'Odorant', 1360, 690, 28, ODOR if odor > 0.3 else WHITE, 1, 'semi')
    label(c, 'Mercaptan added', 1360, 434, ODOR, F(t, odor_t), 26)
    c.restore()
    # handoff
    la = FO(t, T.w('local', S[0] + 3.0) - 0.2, 0.5, S[1] + 2.0)
    label(c, 'Local gas company takes over', 1500, 860, GAS, la, 28)
    # smell
    sa = F(t, S[4] - 0.1)
    if sa > 0:
        egg(c, 1790, 800, 0.9, sa)
        stink(c, 1790, 730, 1.0, sa, t)
        label(c, 'Rotten-egg smell', 1720, 800, ODOR, sa, 30, align='right')
    stairs(c, 1290, 70, 1860, 340, F(t, 0.6), upto=drop, t=t)

# ======================================================================= 8 mains
def mains(c, t, T):
    S = T.s
    GY = 470
    # houses
    for i, x in enumerate((260, 600, 940)):
        house_icon(c, x, GY - 20, 0.62, 1.0, lit=0.6)
    c.drawRect(skia.Rect(0, GY - 20, W, GY), paint((150, 156, 170)))  # sidewalk/curb
    c.drawRect(skia.Rect(0, GY, W, GY + 26), paint((60, 64, 76)))      # road
    for k in range(12): c.drawLine(40 + k * 170, GY + 13, 120 + k * 170, GY + 13, paint((240, 220, 120), 0.8, stroke=4))
    soil(c, 0, GY + 26, W, 900, 1.0, grass=False)
    my = 580
    reg = smooth(prog(t, S[3] + 0.2, 1.0))
    # vault + feed
    vx0, vx1, vy0, vy1 = 300, 520, 630, 820
    va = bump(prog(t, S[3] - 0.2, 3.0))
    pipe(c, [(-20, 725), (vx0 + 30, 725)], 22, 1, 'steel', 1, 1, t, 40, 150)
    if va > 0: rr(c, vx0 - 16, vy0 - 16, vx1 + 16, vy1 + 16, 18, paint(GAS, va * 0.35, blur=20))
    c.drawPath(rpath(vx0 - 10, vy0 - 10, vx1 + 10, vy1 + 10, 14), lin((0, vy0), (0, vy1), [(150, 154, 166), (110, 114, 126)]))
    c.drawPath(rpath(vx0, vy0, vx1, vy1, 8), lin((0, vy0), (0, vy1), [(34, 40, 58), (48, 56, 78)]))
    c.drawPath(rpath(vx0 - 10, vy0 - 10, vx1 + 10, vy1 + 10, 14), paint((80, 86, 100), 1, stroke=2.5))
    for k in range(6): c.drawLine(vx1 - 22, vy0 + 14 + k * 26, vx1 - 8, vy0 + 14 + k * 26, paint((120, 130, 150), 0.8, stroke=3))
    c.drawLine(vx1 - 22, vy0 + 6, vx1 - 22, vy1 - 6, paint((120, 130, 150), 0.8, stroke=2.5)); c.drawLine(vx1 - 8, vy0 + 6, vx1 - 8, vy1 - 6, paint((120, 130, 150), 0.8, stroke=2.5))
    pipe(c, [(vx0 + 30, 725), (vx1 - 50, 725), (vx1 - 50, my)], 18, 1, 'steel')
    regulator(c, 400, 725, 0.85, 1, glow=va)
    c.drawLine(vx0 + 20, GY + 26, vx0 + 20, vy0, paint((120, 130, 160), 1, stroke=3))
    # main
    pipe(c, [(vx1 - 50, my), (1180, my)], 20, 1, 'pe', 1, 1, t, 46, 120)
    pipe(c, [(1180, my), (1940, my)], 20, 1, 'iron', 1, 1, t, 46, 120)
    for x in (260, 600, 940):
        pipe(c, [(x + 40, my - 10), (x + 40, GY - 20)], 6, 1, 'pe')
    label(c, 'Distribution main', 820, my + 56, PE_Y, FO(t, T.w('distribution', 2.2) - 0.2, 0.5, S[1] + 0.2), 28)
    label(c, 'District regulator station', 410, 610 - 0, GAS, F(t, S[3] + 0.3) , 26) if False else None
    da = F(t, S[3] + 0.3)
    label(c, 'District regulator', 410, 860, GAS, da, 26)
    # material cards
    ca = F(t, S[1] - 0.1)
    if ca > 0:
        card(c, 640, 660, 1160, 880, ca, PE_Y)
        pipe(c, [(690, 790), (1110, 790)], 34, ca, 'pe')
        c.drawOval(skia.Rect(1094, 773, 1126, 807), paint((40, 34, 20), ca)); 
        text(c, 'Newer: yellow plastic', 900, 712, 28, PE_Y, ca, 'semi')
        text(c, '(polyethylene)', 900, 858, 26, (230, 220, 180), ca, 'med')
    cb = F(t, S[2] - 0.1)
    if cb > 0:
        card(c, 1220, 660, 1800, 880, cb, (190, 150, 130))
        pipe(c, [(1270, 780), (1500, 780)], 34, cb, 'steel'); pipe(c, [(1540, 780), (1750, 780)], 34, cb, 'iron')
        text(c, 'Older: steel or cast iron', 1510, 712, 28, (220, 190, 170), cb, 'semi')
        text(c, 'Steel', 1385, 852, 26, WHITE, cb, 'med'); text(c, 'Cast iron', 1645, 852, 26, WHITE, cb, 'med')
    tire_a = F(t, S[4] - 0.1)
    stairs(c, 1290, 110, 1860, 380, 1.0, upto=1.0 + reg, t=t, tire_a=tire_a)

# ======================================================================= 9 service
def service(c, t, T):
    S = T.s
    GY = 520
    sky(c, GY)
    c.drawRect(skia.Rect(0, GY - 8, 560, GY + 18), paint((60, 64, 76)))
    c.drawRect(skia.Rect(560, GY - 14, 600, GY + 18), paint((170, 176, 190)))
    c.drawRect(skia.Rect(600, GY - 10, 800, GY + 6), paint((150, 156, 170)))
    soil(c, 0, GY + 6, W, 900, 1.0, grass=False)
    c.drawLine(800, GY, 1530, GY, paint(GRASS, 1, stroke=8))
    # house wall
    c.drawRect(skia.Rect(1530, 170, 1920, GY), lin((0, 170), (0, GY), [(64, 88, 140), (44, 62, 104)]))
    for yy in range(184, GY, 18): c.drawLine(1530, yy, 1920, yy, paint((30, 44, 80), 0.55, stroke=2)); c.drawLine(1530, yy + 2, 1920, yy + 2, paint((110, 140, 200), 0.15, stroke=1))
    c.drawRect(skia.Rect(1530, 170, 1920, GY), paint((24, 34, 64), 1, stroke=3))
    c.drawRect(skia.Rect(1530, GY - 22, 1920, GY), paint((90, 94, 108)))
    c.drawRect(skia.Rect(1626, 236, 1794, 394), paint(LIT, 0.3, blur=18))
    c.drawRect(skia.Rect(1640, 250, 1780, 380), lin((0, 250), (0, 380), [(255, 228, 150), (255, 190, 100)]))
    c.drawRect(skia.Rect(1640, 250, 1780, 380), paint((236, 236, 244), 1, stroke=7))
    c.drawLine(1710, 250, 1710, 380, paint((236, 236, 244), 1, stroke=4)); c.drawLine(1640, 315, 1780, 315, paint((236, 236, 244), 1, stroke=4))
    rr(c, 1630, 378, 1790, 390, 3, paint((236, 236, 244)))
    text(c, 'Street', 280, GY - 30, 26, MUTED, 1, 'semi'); text(c, 'Sidewalk', 700, GY - 30, 26, MUTED, 1, 'semi'); text(c, 'Yard', 1160, GY - 30, 26, MUTED, 1, 'semi')
    # main end-view
    mx, my = 300, 720
    c.drawCircle(mx, my, 46, paint(PE_Y)); c.drawCircle(mx, my, 46, paint((120, 96, 30), stroke=4)); c.drawCircle(mx, my, 32, paint((40, 34, 20)))
    for k in range(6):
        an = k * 1.05 + t
        c.drawCircle(mx + 18 * math.cos(an), my + 18 * math.sin(an), 5, paint(GAS))
    label(c, 'Main', mx - 120, my, PE_Y, 1, 28)
    # service line
    sp = [(mx, my - 46), (mx, 620), (1480, 620), (1480, 380), (1530, 380)]
    g = eio(prog(t, 0.5, 2.6))
    pipe(c, sp, 13, 1, 'pe', g, F(t, 2.6), t, 40, 140)
    if g > 0.98:
        gas_meter(c, 1480, 320, 0.45, 1, t, spin=2)
    label(c, 'Service line', 1050, 680, PE_Y, F(t, T.w('service', 1.4) - 0.2), 28)
    # hose comparison
    ha = FO(t, S[1] - 0.1, 0.5, S[3] - 0.3)
    if ha > 0:
        card(c, 640, 150, 1220, 420, ha)
        for k in range(4):
            c.drawOval(skia.Rect(700 + k * 10, 200 + k * 6, 900 - k * 10, 360 - k * 6), paint((70, 170, 90), ha, stroke=13))
        pipe(c, [(950, 260), (1170, 260)], 14, ha, 'pe')
        c.drawPath(polyline_path([(950, 320), (1060, 320), (1060, 360), (1170, 360)]), paint((70, 170, 90), ha, stroke=13))
        text(c, 'Garden hose', 1060, 400, 26, (120, 210, 140), ha, 'semi')
        text(c, 'Service line', 1060, 232, 26, PE_Y, ha, 'semi')
    da = F(t, S[2] + 0.6)
    if da > 0:
        x = 1240
        c.drawLine(x, GY, x, 620, paint(WHITE, da, stroke=3))
        for yy in (GY, 620): c.drawLine(x - 14, yy, x + 14, yy, paint(WHITE, da, stroke=3))
        label(c, 'Often just 1–2 ft down', x + 30, 790, WHITE, da, 28)
        c.drawLine(x, 620, x + 30, 770, paint(WHITE, da * 0.5, stroke=2))
    # 811
    ba = popin(t, T.w('8', S[3] + 0.9, after=S[3]) - 0.15)
    if ba > 0:
        bb = clamp(ba, 0, 1.15)
        badge_811(c, 900, 290, 120 * bb, min(1, ba))
        label(c, 'Call before you dig', 1230, 230, WHITE, F(t, S[3] + 0.8), 30, align='left')
        label(c, "It's free", 1230, 310, GOLD, F(t, S[4] - 0.1), 28, align='left')
    # flags
    fa = F(t, T.w('mark', S[4] + 1.0) - 0.2)
    for i, x in enumerate(range(860, 1460, 100)):
        pp = popin(t, T.w('mark', S[4] + 1.0) - 0.2 + i * 0.1)
        if pp > 0:
            hh = 60 * clamp(pp, 0, 1.1)
            flag(c, x, GY, hh, 1, t)
    label(c, 'Yellow flags = gas', 1160, 424, PE_Y, fa, 26)

# ======================================================================= 10 house
def house(c, t, T):
    S = T.s
    aA = 1 - F(t, S[6] - 0.5, 0.6)
    aB = F(t, S[6] - 0.5, 0.6)
    if aA > 0.003:
        a = aA; GY = 760
        c.drawRect(skia.Rect(0, 120, 1180, GY), paint((40, 56, 96), a))
        for k in range(18): c.drawLine(0, 140 + k * 36, 1180, 140 + k * 36, paint((60, 80, 124), a * 0.8, stroke=2))
        c.drawLine(1180, 120, 1180, GY, paint(HOUSE_E, a * 0.5, stroke=3))
        soil(c, 0, GY, 1180, 900, a)
        rx = 300; hy = 470
        pipe(c, [(rx, 920), (rx, hy), (1180, hy)], 22, a, 'steel', 1, 1, t, 44, 110)
        # valve
        va = a * F(t, S[1] - 0.1)
        valve(c, rx, 640, 1.3, a, ang=0.0, glow=bump(prog(t, S[1] - 0.1, 2.0)))
        label(c, 'Shutoff valve', rx + 200, 660, (250, 200, 60), va, 28, align='left')
        ga = bump(prog(t, S[2] - 0.1, 2.6))
        regulator(c, 520, hy, 1.4, a, glow=ga)
        label(c, 'Regulator', 520, 290, GAS, a * F(t, S[2] + 0.4), 30)
        mg = bump(prog(t, S[5] - 0.1, 2.0))
        gas_meter(c, 840, hy + 20, 1.25, a, t, spin=3 * F(t, S[5] - 0.2), glow=mg)
        label(c, 'Meter', 840, 300, WHITE, a * F(t, S[5] - 0.1), 30)
        c.drawCircle(1180, hy, 20, paint((20, 26, 44), a))
        stairs(c, 1260, 110, 1860, 400, a * F(t, 0.4), upto=2.0 + smooth(prog(t, S[3] + 0.4, 1.4)), t=t, tire_a=0.0)
        sa = a * F(t, S[4] - 0.1)
        if sa > 0:
            card(c, 1260, 450, 1860, 700, sa)
            c.save(); c.translate(1400, 590); c.rotate(-14)
            rr(c, -100, -9, 100, 9, 9, paint((240, 240, 250), sa))
            for k in range(5): c.drawLine(-90 + k * 40, -9, -70 + k * 40, 9, paint((255, 90, 120), sa, stroke=6))
            c.restore()
            for k in range(3):
                ph = (t * 0.6 + k / 3) % 1
                c.drawCircle(1505 + ph * 50, 560 - ph * 26, 6 + ph * 10, paint((200, 230, 255), sa * (1 - ph) * 0.8, stroke=3))
            text(c, 'Less push than', 1700, 560, 28, WHITE, sa, 'semi')
            text(c, 'gently blowing', 1700, 600, 28, WHITE, sa, 'semi')
            text(c, 'through a straw', 1700, 640, 28, WHITE, sa, 'semi')
    if aB > 0.003:
        a = aB
        FL = 520; BF = 860
        roof = poly_path([(130, 190), (960, 105), (1790, 190)])
        c.drawPath(roof, paint(ROOF, a))
        c.drawRect(skia.Rect(160, 190, 1760, FL), paint((36, 52, 90), a)); c.drawRect(skia.Rect(160, FL, 1760, BF), paint((28, 38, 66), a))
        c.drawRect(skia.Rect(160, 190, 1760, BF), paint(HOUSE_E, a * 0.6, stroke=3)); c.drawLine(160, FL, 1760, FL, paint(HOUSE_E, a * 0.8, stroke=8))
        c.drawLine(1300, 190, 1300, FL, paint(HOUSE_E, a * 0.4, stroke=4))
        text(c, 'Basement', 1736, BF - 18, 24, MUTED, a, 'semi', 'right'); text(c, 'Kitchen', 924, 228, 24, MUTED, a, 'semi', 'left'); text(c, 'Laundry', 1324, 228, 24, MUTED, a, 'semi', 'left')
        py = 580
        pipe(c, [(40, py), (1560, py)], 14, a, 'steel', 1, 1, t, 40, 110)
        apps = [('Furnace', 380), ('Water heater', 760), ('Stove', 1120), ('Dryer', 1540)]
        va = F(t, S[7] - 0.1)
        for i, (nm, x) in enumerate(apps):
            ap = popin(t, T.w(nm.split()[0].lower(), S[6] + 0.5 + i * 0.6, after=S[6] - 0.5) - 0.2)
            if ap <= 0: continue
            aa = a * min(1, ap)
            if nm in ('Stove', 'Dryer'):
                pipe(c, [(x, py), (x, FL - 60)], 10, aa, 'steel', 1, 1, t, 30, 80)
                valve(c, x, FL - 20, 0.85, aa, glow=va)
                if nm == 'Stove':
                    stove(c, x - 120, FL - 141, 0.3, aa, 0, 1.0, t)
                    text(c, nm, x - 120, FL - 210, 30, WHITE, aa, 'semi')
                else:
                    dryer(c, x - 120, FL, 1.0, aa, t, 1.0)
                    text(c, nm, x - 120, FL - 196, 30, WHITE, aa, 'semi')
                    pipe(c, [(x, FL - 60), (x - 40, FL - 60)], 10, aa, 'steel')
                if nm == 'Stove': pipe(c, [(x, FL - 60), (x - 40, FL - 60)], 10, aa, 'steel')
                continue
            pipe(c, [(x, py), (x, 680)], 10, aa, 'steel', 1, 1, t, 30, 80)
            valve(c, x, 640, 0.85, aa, glow=va)
            if nm == 'Furnace':
                furnace(c, x, BF, 1.0, aa, t, 1.0)
            else:
                water_heater(c, x, BF, 1.0, aa, t, 1.0)
            text(c, nm, x + 120 if nm == 'Furnace' else x + 90, 760, 30, WHITE, aa, 'semi', 'left')
        if va > 0: label(c, 'Each has its own shutoff valve', 530, 330, (250, 200, 60), va * a, 30)

# ======================================================================= 11 safety
def safety(c, t, T):
    S = T.s
    cards = [(110, 630), (700, 1220), (1290, 1810)]
    titles = [('1', 'Leave first'), ('2', 'No switches, no flames'), ('3', 'Call from outside')]
    starts = [S[0] + T.w('leave', 1.5, after=S[0]) - S[0] - 0.4, S[1] - 0.1, S[2] - 0.1]
    sm = F(t, 0.3)
    stink(c, 960, 210, 1.6, sm, t); egg(c, 840, 200, 1.0, sm)
    label(c, 'Smell rotten eggs?', 1180, 190, ODOR, sm, 32)
    for i, ((x0, x1), (n, tt_), st) in enumerate(zip(cards, titles, starts)):
        a = popin(t, st)
        if a <= 0: continue
        aa = min(1, a)
        c.save(); cx = (x0 + x1) / 2; c.translate(cx, 560); s_ = clamp(a, 0, 1.06); c.scale(s_, s_); c.translate(-cx, -560)
        card(c, x0, 300, x1, 860, aa, (120, 140, 190))
        c.drawCircle(x0 + 50, 350, 26, paint(GAS, aa)); text(c, n, x0 + 50, 361, 30, (10, 20, 40), aa, 'bold')
        text(c, tt_, cx + 20, 362, 30, WHITE, aa, 'bold')
        if i == 0:
            door(c, cx + 140, 780, 1.4, aa, open_=1.0, t=t)
            wk = prog(t, st + 0.4, 1.8)
            px = cx - 150 + 315 * smooth(wk)
            human(c, px, 780, 0.8, aa * (1 - smooth(prog(t, st + 1.9, 0.5))), outfit=1, pose='walk', phase=(t - st) * 7.5 if 0 < wk < 1 else 0.0)
            arrow(c, (cx - 190, 470), (cx + 20, 470), GAS, 10, aa, glow=False)
        elif i == 1:
            light_switch(c, cx - 110, 610, 1.3, aa); no_sign(c, cx - 110, 610, 92, aa)
            match(c, cx + 120, 620, 1.3, aa, t); no_sign(c, cx + 120, 610, 92, aa)
        else:
            house_icon(c, cx - 110, 800, 0.55, aa)
            human(c, cx + 140, 800, 0.85, aa, outfit=2, pose='phone')
            for k in range(3):
                c.drawArc(skia.Rect(cx + 150 - 18 - k * 12, 568 - 18 - k * 12, cx + 150 + 18 + k * 12, 568 + 18 + k * 12), -60, 50, False,
                          paint(GAS, aa * (0.5 + 0.5 * math.sin(t * 5 - k)), stroke=4))
            text(c, 'Gas company or 911', cx, 470, 28, GOLD, aa, 'semi')
        c.restore()

# ======================================================================= 12 close
CL_GY = 450
STOPS = [('Well', 120), ('Processing', 330), ('Compressors', 660), ('City gate', 1000), ('Regulator', 1290), ('Home', 1660)]
def close_world(c, t, glow_all, hl, fl, path_grow, flow):
    GY = CL_GY
    sky(c, GY)
    soil(c, -400, GY, 2400, 520, 1.0)
    hp = skia.Path(); hp.moveTo(-400, GY)
    for x in range(-400, 2401, 40): hp.lineTo(x, GY - 30 - 24 * math.sin(x / 170) - 12 * math.sin(x / 61))
    hp.lineTo(2400, GY); hp.close(); c.drawPath(hp, paint((30, 46, 82)))
    path = [(120, GY), (120, 495), (330, 495), (1000, 495), (1000, 488), (1660, 488), (1660, 440)]
    pipe(c, path, 12, 1, 'steel', path_grow, flow, 0 + c_t[0], 34, 120, glow=0.5 * glow_all)
    wellhead(c, 120, GY, 0.42, 1, glow=hl[0])
    plant_icon(c, 330, GY, 0.42, 1, c_t[0], glow=hl[1])
    compressor(c, 560, GY, 0.42, 1, c_t[0], glow=hl[2]); compressor(c, 780, GY, 0.42, 1, c_t[0], glow=hl[2])
    mini_station(c, 940, 1060, GY, 70, 1, 0.4, hl[3], c_t[0])
    mini_station(c, 1252, 1328, GY, 44, 1, 0.28, hl[4], c_t[0])
    house_icon(c, 1660, GY, 0.62, 1, lit=0.5 + 0.5 * hl[5])
    c.drawCircle(1620, 386, 22, paint((80, 140, 255), 0.7 * fl, blur=10))
    for k in range(3):
        fire = skia.Path(); fx_ = 1610 + k * 10; fy_ = 397
        fire.moveTo(fx_ - 4, fy_); fire.quadTo(fx_ - 2, fy_ - 10, fx_, fy_ - 16 - 2 * math.sin(c_t[0] * 15 + k)); fire.quadTo(fx_ + 2, fy_ - 10, fx_ + 4, fy_); fire.close()
        c.drawPath(fire, paint((90, 150, 255), fl))
c_t = [0.0]

def close(c, t, T):
    S = T.s; c_t[0] = t
    zu = eio(prog(t, 0.3, 3.0))
    Z = math.exp(lerp(math.log(2.6), 0.0, zu))
    fx, fy = lerp(1660, 960, zu), lerp(370, 540, zu)
    sx, sy = 960, lerp(500, 540, zu)
    hl = [0] * 6
    def HL(i, t0, d=1.6): hl[i] = max(hl[i], bump(prog(t, t0, d)))
    HL(0, T.w('rock', S[1] + 0.3, after=S[1] - 0.3) - 0.2); HL(1, T.w('rock', S[1] + 0.3, after=S[1] - 0.3) + 0.4)
    HL(2, T.w('steel', S[1] + 2.0, after=S[1]) - 0.6, 2.0)
    HL(3, T.w('gate', S[2] + 1.0, after=S[2] - 0.3) - 0.4); HL(4, T.w('street', S[2] + 1.8, after=S[2] - 0.3) - 0.4); HL(5, T.w('home', S[2] + 2.6, after=S[2] - 0.3) - 0.4)
    c.save(); c.translate(sx, sy); c.scale(Z, Z); c.translate(-fx, -fy)
    close_world(c, t, 1.0, hl, 1.0, 1.0, 1.0)
    c.restore()
    la = F(t, 2.4, 0.8)
    endf = F(t, S[5] + 1.6, 1.0)
    for i, (nm, x) in enumerate(STOPS):
        y = 170 if i % 2 == 0 else 220
        label(c, nm, x, y, GAS if hl[i] > 0.3 else WHITE, la * (1 - endf), 26)
        c.drawLine(x, y + 22, x, CL_GY - 60, paint((150, 170, 210), la * (1 - endf) * 0.5, stroke=2))
    sa = F(t, S[3] - 0.3, 0.8) * (1 - endf)
    xs = [(330, 1000), (1000, 1290), (1290, 1560), (1560, 1820)]
    up = 3 * smooth(prog(t, T.w('steps', S[3] + 0.8, after=S[3] - 0.3), 5.0)) if sa > 0 else 0
    stairs(c, 100, 540, 1840, 900 - 10, sa, upto=up, t=t, tire_a=0.0, big=True, xs=xs)
    ma = FO(t, S[4] - 0.1, 0.6, S[5] + 1.6)
    if ma > 0:
        label(c, '2,000,000+ miles of gas pipe in the US', 960, 300 - 0, GOLD, ma, 32)
    if endf > 0:
        c.drawRect(skia.Rect(0, 0, W, H), paint((6, 11, 26), endf * 0.85))
        burner(c, 960, 520, 1.5, endf, 1.0, t)
        text(c, 'How Natural Gas Gets to Your Home', 960, 760, 56, WHITE, endf, 'bold')

SCENE_FUNCS = dict(hook=hook, source=source, gathering=gathering, processing=processing, transmission=transmission, compressors=compressors,
                   storage=storage, citygate=citygate, mains=mains, service=service, house=house, safety=safety, close=close)

def sfx_events(TM, words=None):
    """(scene_id, local_time, kind). `words` is {scene_id: [[word, start, end], ...]} when ASR ran."""
    Wd = words or {}
    def w(sid, word, default, after=0.0):
        for item in Wd.get(sid, []):
            wd, a = item[0], item[1]
            if a >= after and str(wd).startswith(word): return a
        return default
    g = lambda k: [x['start'] for x in TM[k]['sentences']]
    ev = []
    tk = w('hook', 'turn', 0.75)
    ev += [('hook', tk + 0.25, 'tick'), ('hook', tk + 0.5, 'tick'), ('hook', tk + 0.75, 'tick')]
    ev.append(('hook', w('hook', 'flame', 2.6) - 0.15, 'whoosh'))
    s = g('source'); ev.append(('source', s[5] - 0.2, 'rumble'))
    ev.append(('source', w('source', 'crack', s[5] + 3.6) - 0.1, 'crack'))
    ev.append(('source', w('source', 'wellhead', s[6] + 1.6) - 0.3, 'blip'))
    s = g('gathering'); ev.append(('gathering', s[2] + 0.3, 'blip'))
    s = g('processing'); ev.append(('processing', s[3] - 0.1, 'blip'))
    s = g('compressors'); ev.append(('compressors', s[1] + 0.4, 'blip')); ev.append(('compressors', s[1] + 0.9, 'blip_lo'))
    s = g('storage'); ev.append(('storage', s[3] - 0.2, 'whoosh_soft'))
    s = g('citygate'); ev.append(('citygate', s[1] + 0.2, 'hiss'))
    ev.append(('citygate', w('citygate', 'mercaptan', s[3] + 2.4) + 0.1, 'drip'))
    s = g('mains'); ev.append(('mains', s[3] + 0.2, 'hiss'))
    s = g('service'); ev.append(('service', w('service', '8', s[3] + 0.9, after=s[3]) - 0.15, 'chime'))
    s = g('house'); ev.append(('house', s[1] - 0.1, 'click')); ev.append(('house', s[2] + 0.1, 'hiss'))
    s = g('safety'); ev += [('safety', s[1] - 0.1, 'blip'), ('safety', s[2] - 0.1, 'blip')]
    s = g('close'); ev.append(('close', s[5] + 1.6, 'whoosh'))
    return ev
