# Polished flat / semi-flat illustration helpers (skia). Shared look: gradient fills, darker outline of the same hue,
# a soft top highlight and a soft contact shadow. All coordinates in 1920x1080 space unless noted.
import math, skia, numpy as np
from .lib import *

OUTW = 2.4  # standard outline weight (screen px at s=1)

def sh(c_, k):
    """k<0 darker, k>0 lighter"""
    return lerpc(c_, (0, 0, 0), -k) if k < 0 else lerpc(c_, (255, 255, 255), k)

def lin(p0, p1, cols, a=1.0, pos=None):
    return skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear([p0, p1], [col(x, a) for x in cols], pos))

def rad(cx, cy, r, cols, a=1.0, pos=None):
    return skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeRadial((cx, cy), max(r, 0.01), [col(x, a) for x in cols], pos))

def rpath(x0, y0, x1, y1, r):
    p = skia.Path(); p.addRRect(skia.RRect.MakeRectXY(skia.Rect(x0, y0, x1, y1), r, r)); return p

def opath(cx, cy, rx, ry):
    p = skia.Path(); p.addOval(skia.Rect(cx - rx, cy - ry, cx + rx, cy + ry)); return p

def fillv(c, path, top, bot, a=1.0, ol=True, ow=None, olc=None, hl=0.0):
    """vertical-gradient fill + outline (+ optional inner top highlight)"""
    if a <= 0.003: return
    b = path.getBounds()
    c.drawPath(path, lin((0, b.top()), (0, b.bottom()), [top, bot], a))
    if hl > 0:
        c.save(); c.clipPath(path, skia.ClipOp.kIntersect, True)
        c.drawPath(path, paint((255, 255, 255), a * hl * 0.5, stroke=(ow or OUTW) * 2.2, blur=1.2)); c.restore()
    if ol: c.drawPath(path, paint(olc or sh(bot, -0.45), a, stroke=ow or OUTW))

def fillh(c, path, left, mid, right, a=1.0, ol=True, ow=None, olc=None):
    """horizontal (cylinder) shading"""
    if a <= 0.003: return
    b = path.getBounds()
    c.drawPath(path, lin((b.left(), 0), (b.right(), 0), [left, mid, right], a, [0, 0.38, 1]))
    if ol: c.drawPath(path, paint(olc or sh(right, -0.4), a, stroke=ow or OUTW))

def contact(c, x, y, rx, ry=None, a=1.0, k=0.35):
    if a <= 0.003: return
    ry = ry or rx * 0.18
    c.drawOval(skia.Rect(x - rx, y - ry, x + rx, y + ry), paint((0, 0, 0), a * k, blur=max(2, ry * 0.8)))

def _seg_path(p, p0, p1, w0, w1):
    x0, y0 = p0; x1, y1 = p1; dx, dy = x1 - x0, y1 - y0; L = math.hypot(dx, dy) or 1e-6
    nx, ny = -dy / L, dx / L
    p.moveTo(x0 + nx * w0 / 2, y0 + ny * w0 / 2); p.lineTo(x1 + nx * w1 / 2, y1 + ny * w1 / 2)
    p.lineTo(x1 - nx * w1 / 2, y1 - ny * w1 / 2); p.lineTo(x0 - nx * w0 / 2, y0 - ny * w0 / 2); p.close()
    p.addCircle(x0, y0, w0 / 2); p.addCircle(x1, y1, w1 / 2)

def limb(c, pts, ws, col_, a=1.0, ol=True, olc=None, ow=None, extra=None):
    """joined tapered chain through pts with widths ws (same length); outline drawn once -> no seams"""
    if a <= 0.003: return
    b = skia.OpBuilder()
    for i in range(len(pts) - 1):
        q = skia.Path(); _seg_path(q, pts[i], pts[i + 1], ws[i], ws[i + 1])
        for j in range(3):  # split into convex pieces so direction never cancels
            pass
        q1 = skia.Path(); x0, y0 = pts[i]; x1, y1 = pts[i + 1]
        dx, dy = x1 - x0, y1 - y0; L = math.hypot(dx, dy) or 1e-6; nx, ny = -dy / L, dx / L
        w0, w1 = ws[i], ws[i + 1]
        q1.moveTo(x0 + nx * w0 / 2, y0 + ny * w0 / 2); q1.lineTo(x1 + nx * w1 / 2, y1 + ny * w1 / 2)
        q1.lineTo(x1 - nx * w1 / 2, y1 - ny * w1 / 2); q1.lineTo(x0 - nx * w0 / 2, y0 - ny * w0 / 2); q1.close()
        b.add(q1, skia.PathOp.kUnion_PathOp)
        for (cx, cy, r) in ((x0, y0, w0 / 2), (x1, y1, w1 / 2)):
            q2 = skia.Path(); q2.addCircle(cx, cy, r); b.add(q2, skia.PathOp.kUnion_PathOp)
    if extra is not None: b.add(extra, skia.PathOp.kUnion_PathOp)
    p = b.resolve()
    if ol: c.drawPath(p, paint(olc or sh(col_, -0.45), a, stroke=(ow or OUTW) * 2))
    c.drawPath(p, paint(col_, a))

def capsule(c, p0, p1, w0, w1, col_, a=1.0, ol=True, olc=None, ow=None):
    limb(c, [p0, p1], [w0, w1], col_, a, ol, olc, ow)

def ik2(hip, foot, l1, l2, bend=1):
    """two-bone IK: returns knee position"""
    dx, dy = foot[0] - hip[0], foot[1] - hip[1]; d = min(math.hypot(dx, dy), l1 + l2 - 0.01)
    a = math.atan2(dy, dx)
    cosb = clamp((l1 * l1 + d * d - l2 * l2) / (2 * l1 * d), -1, 1)
    b = math.acos(cosb)
    return (hip[0] + l1 * math.cos(a - bend * b), hip[1] + l1 * math.sin(a - bend * b))

# ------------------------------------------------------------------ people
OUTFITS = [  # shirt, pants, hair, skin, shoes
    dict(shirt=(64, 168, 176), pants=(52, 66, 112), hair=(46, 32, 28), skin=(232, 186, 150), shoe=(40, 40, 50)),
    dict(shirt=(236, 132, 76), pants=(64, 92, 150), hair=(120, 72, 42), skin=(196, 138, 98), shoe=(60, 44, 40)),
    dict(shirt=(132, 112, 204), pants=(44, 52, 80), hair=(24, 22, 26), skin=(150, 100, 72), shoe=(34, 34, 40)),
    dict(shirt=(94, 160, 236), pants=(70, 74, 96), hair=(214, 170, 100), skin=(240, 200, 168), shoe=(70, 50, 40)),
]

def _head_front(c, o, a, hat=None, hairstyle=0):
    skin, hair = o['skin'], o['hair']
    capsule(c, (0, -216), (0, -198), 15, 16, sh(skin, -0.12), a, ol=False)
    for ex in (-21, 21):
        c.drawOval(skia.Rect(ex - 5, -241, ex + 5, -225), paint(sh(skin, -0.1), a))
    head = opath(0, -236, 21, 24)
    c.drawPath(head, rad(-6, -246, 34, [sh(skin, 0.12), skin, sh(skin, -0.12)], a, [0, 0.6, 1]))
    c.drawPath(head, paint(sh(skin, -0.45), a, stroke=OUTW))
    if hat is None:
        hp = skia.Path(); hp.moveTo(-23, -232)
        if hairstyle == 0:
            hp.cubicTo(-26, -268, 26, -270, 23, -234); hp.cubicTo(18, -250, 4, -254, -6, -248); hp.cubicTo(-14, -246, -18, -240, -23, -232)
        else:
            hp.cubicTo(-30, -272, 30, -272, 24, -226); hp.lineTo(26, -212); hp.cubicTo(22, -250, 6, -256, -4, -250)
            hp.cubicTo(-14, -244, -20, -236, -26, -212); hp.close()
        hp.close()
        c.drawPath(hp, lin((0, -265), (0, -230), [sh(hair, 0.15), hair], a)); c.drawPath(hp, paint(sh(hair, -0.4), a, stroke=OUTW * 0.8))
    else:
        dome = skia.Path(); dome.moveTo(-25, -246); dome.cubicTo(-25, -276, 25, -276, 25, -246); dome.close()
        c.drawPath(dome, lin((0, -276), (0, -246), [sh(hat, 0.25), hat], a)); c.drawPath(dome, paint(sh(hat, -0.45), a, stroke=OUTW))
        c.drawLine(0, -272, 0, -248, paint(sh(hat, -0.25), a, stroke=4))
        brim = rpath(-31, -250, 31, -242, 4); c.drawPath(brim, paint(sh(hat, -0.1), a)); c.drawPath(brim, paint(sh(hat, -0.45), a, stroke=OUTW))
    # face
    for ex in (-8, 8):
        c.drawCircle(ex, -233, 2.8, paint((34, 30, 40), a))
        c.drawCircle(ex + 0.9, -234, 0.9, paint((255, 255, 255), a * 0.8))
        c.drawLine(ex - 4, -241, ex + 4, -242 + (1 if ex > 0 else 0), paint(sh(hair, -0.1), a, stroke=2))
    c.drawPath(polyline_path([(0, -230), (-2, -223), (1, -222)]), paint(sh(skin, -0.3), a, stroke=1.8))
    m = skia.Path(); m.moveTo(-6, -216); m.quadTo(0, -211, 6, -216)
    c.drawPath(m, paint((150, 70, 70), a, stroke=2.2))
    for ex in (-12, 12): c.drawCircle(ex, -222, 3.5, paint((240, 120, 120), a * 0.25, blur=1.5))

def human(c, x, y, s=1.0, a=1.0, outfit=0, pose='stand', phase=0.0, hat=None, vest=False, facing=1):
    """flat-style person; feet at (x,y); ~280*s px tall. pose: 'stand' (front), 'phone' (front, phone to ear), 'walk' (side, facing)."""
    if a <= 0.003: return
    o = OUTFITS[outfit % len(OUTFITS)]
    c.save(); c.translate(x, y); c.scale(s * facing, s)
    contact(c, 0, 0, 40, 7, a, 0.4)
    shirt, pants, skin, shoe = o['shirt'], o['pants'], o['skin'], o['shoe']
    if pose in ('stand', 'phone'):
        # legs
        for sx in (-1, 1):
            limb(c, [(13 * sx, -128), (14 * sx, -66), (15 * sx, -16)], [25, 21, 17], pants if sx < 0 else sh(pants, -0.12), a)
            sp = skia.Path(); sp.moveTo(15 * sx - 12, -4); sp.cubicTo(15 * sx - 13, -22, 15 * sx + 12, -22, 15 * sx + 14 * 1, -4); sp.close()
            sp = rpath(15 * sx - 14, -18, 15 * sx + 14, -1, 7)
            fillv(c, sp, sh(shoe, 0.2), shoe, a)
        # torso
        tp = skia.Path(); tp.moveTo(-12, -202); tp.lineTo(-30, -196); tp.cubicTo(-38, -193, -36, -180, -34, -170)
        tp.lineTo(-27, -124); tp.lineTo(27, -124); tp.lineTo(34, -170); tp.cubicTo(36, -180, 38, -193, 30, -196); tp.lineTo(12, -202); tp.close()
        c.drawPath(tp, lin((-34, 0), (34, 0), [sh(shirt, 0.1), shirt, sh(shirt, -0.18)], a, [0, 0.45, 1]))
        if vest:
            vy = (196, 230, 60)
            for sx in (-1, 1):
                vp = skia.Path(); vp.moveTo(5 * sx, -200); vp.lineTo(27 * sx, -195); vp.lineTo(30 * sx, -126); vp.lineTo(5 * sx, -126); vp.close()
                c.drawPath(vp, paint(vy if sx < 0 else sh(vy, -0.1), a))
                for yy in (-168, -146): c.drawRect(skia.Rect(min(6 * sx, 29 * sx), yy, max(6 * sx, 29 * sx), yy + 6), paint((220, 226, 236), a))
        c.drawPath(tp, paint(sh(shirt, -0.45), a, stroke=OUTW))
        c.drawRect(skia.Rect(-27, -132, 27, -124), paint(sh(pants, -0.25), a))
        # arms
        limb(c, [(-38, -150), (-41, -116), (-41, -110)], [14, 12, 16], skin, a)
        limb(c, [(-31, -188), (-38, -150)], [17, 15], sh(shirt, 0.05), a)
        if pose == 'phone':
            limb(c, [(31, -188), (44, -162)], [17, 15], sh(shirt, -0.12), a)
            _head_front(c, o, a, hat, outfit % 2)
            c.save(); c.translate(22, -232); c.rotate(-18)
            fillv(c, rpath(-7, -18, 7, 18, 4), (60, 66, 84), (30, 34, 46), a)
            c.drawRect(skia.Rect(-5, -14, 5, 12), paint((110, 190, 255), a * 0.9))
            c.restore()
            limb(c, [(44, -162), (28, -218), (25, -226)], [14, 12, 16], sh(skin, -0.06), a)
        else:
            limb(c, [(38, -150), (41, -116), (41, -110)], [14, 12, 16], sh(skin, -0.06), a)
            limb(c, [(31, -188), (38, -150)], [17, 15], sh(shirt, -0.12), a)
            _head_front(c, o, a, hat, outfit % 2)
    else:  # side walk, facing +x
        sw = math.sin(phase)
        hip = (0, -128)
        def leg(th, dark):
            pc = sh(pants, -0.22) if dark else pants
            knee = (hip[0] + 62 * math.sin(th), hip[1] + 62 * math.cos(th))
            bend = 0.55 * max(0.0, math.sin(th * -1 + 0.3)) if False else 0.35 * (0.5 - 0.5 * math.cos(th * 2))
            th2 = th - bend
            ank = (knee[0] + 56 * math.sin(th2), knee[1] + 56 * math.cos(th2))
            limb(c, [hip, knee, ank], [24, 20, 16], pc, a)
            sp = skia.Path(); sp.moveTo(ank[0] - 9, ank[1] - 6); sp.lineTo(ank[0] + 22, ank[1] - 2); sp.quadTo(ank[0] + 26, ank[1] + 8, ank[0] + 18, ank[1] + 9)
            sp.lineTo(ank[0] - 10, ank[1] + 9); sp.close()
            c.drawPath(sp, paint(sh(shoe, -0.2) if dark else shoe, a)); c.drawPath(sp, paint(sh(shoe, -0.5), a, stroke=OUTW))
        def arm(th, dark):
            sc_ = sh(shirt, -0.22) if dark else shirt; sk = sh(skin, -0.2) if dark else skin
            sho = (6, -188); el = (sho[0] + 38 * math.sin(th), sho[1] + 38 * math.cos(th))
            th2 = th + 0.35 + 0.25 * max(0, th)
            wr = (el[0] + 34 * math.sin(th2), el[1] + 34 * math.cos(th2))
            limb(c, [el, wr, (wr[0], wr[1] + 4)], [13, 11, 15], sk, a)
            limb(c, [sho, el], [17, 15], sc_, a)
        leg(-0.42 * sw, True); arm(0.45 * sw, True)
        tp = skia.Path(); tp.moveTo(-10, -202); tp.cubicTo(-24, -196, -22, -170, -20, -150); tp.lineTo(-18, -124); tp.lineTo(20, -124)
        tp.lineTo(22, -160); tp.cubicTo(26, -186, 24, -200, 12, -204); tp.close()
        c.drawPath(tp, lin((-22, 0), (24, 0), [sh(shirt, -0.12), shirt, sh(shirt, 0.08)], a)); c.drawPath(tp, paint(sh(shirt, -0.45), a, stroke=OUTW))
        c.drawRect(skia.Rect(-19, -132, 20, -124), paint(sh(pants, -0.25), a))
        leg(0.42 * sw, False)
        # head (side)
        capsule(c, (4, -216), (4, -198), 15, 16, sh(skin, -0.12), a, ol=False)
        hd = skia.Path(); hd.addOval(skia.Rect(-18, -260, 26, -212))
        c.drawPath(hd, rad(6, -246, 32, [sh(skin, 0.1), skin, sh(skin, -0.12)], a, [0, 0.6, 1]))
        nz = skia.Path(); nz.moveTo(24, -242); nz.quadTo(33, -232, 25, -228); nz.close(); c.drawPath(nz, paint(skin, a))
        c.drawPath(hd, paint(sh(skin, -0.45), a, stroke=OUTW))
        c.drawPath(nz, paint(sh(skin, -0.45), a, stroke=OUTW * 0.8))
        hp = skia.Path(); hp.moveTo(-20, -226); hp.cubicTo(-26, -262, 18, -276, 26, -244); hp.cubicTo(14, -250, 4, -246, 0, -238)
        hp.cubicTo(-4, -232, -10, -228, -20, -226); hp.close()
        c.drawPath(hp, lin((0, -270), (0, -228), [sh(o['hair'], 0.15), o['hair']], a)); c.drawPath(hp, paint(sh(o['hair'], -0.4), a, stroke=OUTW * 0.8))
        c.drawOval(skia.Rect(-2, -238, 8, -224), paint(sh(skin, -0.12), a))
        c.drawCircle(15, -238, 2.8, paint((34, 30, 40), a))
        m = skia.Path(); m.moveTo(14, -220); m.quadTo(19, -218, 22, -221); c.drawPath(m, paint((150, 70, 70), a, stroke=2))
        arm(-0.45 * sw, False)
    c.restore()

# ------------------------------------------------------------------ bicycle with rider
def bicycle(c, x, y, s=1.0, a=1.0, t=0.0, color=None, outfit=1):
    """side-view bike + rider facing +x; (x,y) = axle height centre"""
    if a <= 0.003: return
    o = OUTFITS[outfit]
    fr = (236, 84, 84)
    c.save(); c.translate(x, y); c.scale(s, s)
    contact(c, 0, 42, 110, 8, a, 0.35)
    ang = t * 7.0
    R, Fw, BB = (-62, 0), (62, 0), (-4, 6)
    S, Ht, Hb = (-24, -60), (40, -62), (46, -44)
    def wheel(cx):
        c.drawCircle(cx, 0, 40, paint((28, 30, 38), a, stroke=8))
        c.drawCircle(cx, 0, 35, paint((190, 198, 214), a, stroke=2.5))
        for k in range(16):
            an = ang + k * math.pi / 8
            c.drawLine(cx + 4 * math.cos(an + 0.3), 4 * math.sin(an + 0.3), cx + 34 * math.cos(an), 34 * math.sin(an), paint((200, 208, 222), a * 0.85, stroke=1.2))
        c.drawCircle(cx, 0, 5, paint((150, 158, 176), a)); c.drawCircle(cx, 0, 5, paint((60, 64, 80), a, stroke=1.5))
    # far leg first
    def leg(theta, dark):
        pc = sh(o['pants'], -0.25) if dark else o['pants']
        hip = (-26, -72)
        pd = (BB[0] + 17 * math.cos(theta), BB[1] + 17 * math.sin(theta))
        kn = ik2(hip, pd, 52, 50, bend=1)
        if kn[0] < hip[0] + 6: kn = ik2(hip, pd, 52, 50, bend=-1)
        limb(c, [hip, kn, pd], [18, 15, 12], pc, a)
        sp = rpath(pd[0] - 8, pd[1] - 6, pd[0] + 14, pd[1] + 4, 4); c.drawPath(sp, paint(sh(o['shoe'], -0.2) if dark else o['shoe'], a))
    leg(ang + math.pi, True)
    wheel(R[0]); wheel(Fw[0])
    tube = lambda p, q, w=6.5: c.drawLine(p[0], p[1], q[0], q[1], paint(fr, a, stroke=w))
    for p, q in ((R, BB), (R, S)): c.drawLine(p[0], p[1], q[0], q[1], paint(sh(fr, -0.15), a, stroke=5))
    tube(BB, S); tube(S, Ht); tube(BB, Hb, 7.5); tube(Ht, Hb, 9)
    c.drawLine(Hb[0], Hb[1], Fw[0], Fw[1], paint((170, 178, 194), a, stroke=5))
    for p, q in ((BB, S), (S, Ht)): c.drawLine(p[0], p[1] - 1.5, q[0], q[1] - 1.5, paint((255, 255, 255), a * 0.35, stroke=1.5))
    c.drawLine(Ht[0], Ht[1], 40, -76, paint((60, 64, 80), a, stroke=4))
    hb = skia.Path(); hb.moveTo(34, -76); hb.lineTo(52, -78); hb.quadTo(60, -78, 58, -68); c.drawPath(hb, paint((50, 54, 66), a, stroke=4.5))
    c.drawLine(S[0], S[1], -26, -70, paint((150, 158, 176), a, stroke=4))
    sd = skia.Path(); sd.moveTo(-42, -74); sd.quadTo(-26, -80, -12, -73); sd.lineTo(-30, -68); sd.close(); c.drawPath(sd, paint((40, 40, 48), a))
    c.drawCircle(BB[0], BB[1], 11, paint((150, 158, 176), a, stroke=3))
    pd2 = (BB[0] + 17 * math.cos(ang), BB[1] + 17 * math.sin(ang)); c.drawLine(BB[0], BB[1], pd2[0], pd2[1], paint((90, 96, 110), a, stroke=4))
    # rider body
    shirt = o['shirt']; skin = o['skin']
    tp = skia.Path(); tp.moveTo(-40, -70); tp.cubicTo(-40, -104, -16, -134, 8, -142); tp.cubicTo(20, -144, 28, -132, 24, -122)
    tp.cubicTo(6, -112, -6, -96, -10, -70); tp.close()
    c.drawPath(tp, lin((-30, -130), (20, -80), [sh(shirt, 0.1), sh(shirt, -0.15)], a)); c.drawPath(tp, paint(sh(shirt, -0.45), a, stroke=OUTW))
    leg(ang, False)
    limb(c, [(32, -100), (50, -80), (52, -78)], [11, 10, 13], skin, a)
    limb(c, [(14, -130), (32, -100)], [15, 12], shirt, a)
    # head with helmet
    c.drawCircle(26, -152, 16, rad(22, -158, 20, [sh(skin, 0.1), skin], a)); c.drawCircle(26, -152, 16, paint(sh(skin, -0.45), a, stroke=OUTW))
    hm = skia.Path(); hm.moveTo(8, -152); hm.cubicTo(6, -178, 40, -182, 44, -156); hm.lineTo(30, -158); hm.close()
    c.drawPath(hm, lin((0, -180), (0, -152), [(120, 210, 255), (40, 130, 210)], a)); c.drawPath(hm, paint((20, 60, 110), a, stroke=OUTW))
    c.drawCircle(35, -151, 2.4, paint((34, 30, 40), a))
    c.restore()

# ------------------------------------------------------------------ smell / face / egg / prohibition
def face_profile(c, x, y, s=1.0, a=1.0, outfit=0):
    """head in profile facing +x, centre ~ (x,y), ~200*s tall"""
    if a <= 0.003: return
    o = OUTFITS[outfit]; skin = o['skin']; hair = o['hair']
    c.save(); c.translate(x, y); c.scale(s, s)
    p = skia.Path()
    p.moveTo(-40, 100); p.cubicTo(-46, 70, -70, 40, -66, -10); p.cubicTo(-62, -70, -20, -98, 18, -92)
    p.cubicTo(44, -88, 56, -64, 54, -36); p.cubicTo(54, -28, 56, -22, 58, -16)
    p.cubicTo(66, -2, 78, 10, 80, 18); p.cubicTo(82, 26, 72, 28, 62, 28)
    p.cubicTo(64, 34, 64, 38, 60, 41); p.cubicTo(64, 46, 62, 52, 58, 54)
    p.cubicTo(60, 66, 54, 78, 40, 82); p.cubicTo(30, 85, 22, 84, 18, 86); p.lineTo(20, 100); p.close()
    contact(c, -10, 104, 50, 6, a, 0.25)
    c.drawPath(p, rad(10, -30, 120, [sh(skin, 0.15), skin, sh(skin, -0.15)], a, [0, 0.55, 1]))
    c.drawPath(p, paint(sh(skin, -0.45), a, stroke=OUTW * 1.2))
    hp = skia.Path(); hp.moveTo(-66, 10); hp.cubicTo(-80, -60, -30, -112, 24, -96); hp.cubicTo(46, -90, 58, -70, 56, -50)
    hp.cubicTo(40, -66, 10, -68, -8, -56); hp.cubicTo(-22, -44, -30, -24, -40, 12); hp.close()
    c.drawPath(hp, lin((0, -110), (0, 10), [sh(hair, 0.18), hair], a)); c.drawPath(hp, paint(sh(hair, -0.4), a, stroke=OUTW))
    c.drawOval(skia.Rect(-30, -22, -8, 12), paint(sh(skin, -0.12), a)); c.drawOval(skia.Rect(-30, -22, -8, 12), paint(sh(skin, -0.45), a, stroke=OUTW))
    c.drawArc(skia.Rect(-25, -14, -13, 4), 250, 200, False, paint(sh(skin, -0.4), a, stroke=2))
    # closed eye + brow
    e = skia.Path(); e.moveTo(28, -30); e.quadTo(36, -24, 44, -30); c.drawPath(e, paint((40, 30, 36), a, stroke=3))
    b = skia.Path(); b.moveTo(24, -46); b.quadTo(36, -52, 48, -44); c.drawPath(b, paint(sh(hair, -0.1), a, stroke=4))
    c.drawPath(polyline_path([(66, 18), (70, 22), (64, 24)]), paint(sh(skin, -0.4), a, stroke=2))
    c.drawCircle(42, 2, 9, paint((240, 120, 120), a * 0.22, blur=3))
    c.restore()

def stink(c, x, y, s=1.0, a=1.0, t=0.0, color=(170, 220, 80), n=3, spread=34, length=80):
    if a <= 0.003: return
    for k in range(n):
        ph = (t * 0.45 + k / n) % 1
        xx = x + (k - (n - 1) / 2) * spread * s; yy = y - ph * 40 * s
        pts = [(xx + 11 * s * math.sin(j * 0.75 + t * 3 + k), yy - j * length / 12 * s) for j in range(13)]
        fa = a * math.sin(math.pi * ph) ** 0.8
        c.drawPath(polyline_path(pts), paint(color, fa * 0.35, stroke=12 * s, blur=4 * s))
        c.drawPath(polyline_path(pts), paint(color, fa, stroke=5.5 * s))

def smell_toward(c, x0, y0, x1, y1, a=1.0, t=0.0, color=(170, 220, 80)):
    """wavy smell lines drifting horizontally from (x0,y0) toward (x1,y1)"""
    if a <= 0.003: return
    for k in range(3):
        ph = (t * 0.5 + k / 3) % 1
        oy = (k - 1) * 22
        pts = []
        for j in range(16):
            u = j / 15
            px = lerp(x0, x1, u * (0.55 + 0.45 * ph)); py = lerp(y0, y1, u) + oy * (1 - u * 0.6) + 8 * math.sin(u * 9 + t * 4 + k)
            pts.append((px, py))
        fa = a * (0.4 + 0.6 * math.sin(math.pi * ph))
        c.drawPath(polyline_path(pts), paint(color, fa, stroke=5))

def egg(c, x, y, s=1.0, a=1.0, cracked=True):
    """cracked rotten egg centred at (x,y)"""
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    contact(c, 0, 42, 36, 7, a, 0.4)
    p = skia.Path(); p.moveTo(0, -48); p.cubicTo(28, -48, 38, -4, 36, 14); p.cubicTo(34, 36, 18, 44, 0, 44); p.cubicTo(-18, 44, -34, 36, -36, 14)
    p.cubicTo(-38, -4, -28, -48, 0, -48); p.close()
    c.drawPath(p, rad(-10, -20, 70, [(255, 252, 236), (236, 226, 196), (196, 180, 140)], a, [0, 0.55, 1]))
    c.drawPath(p, paint((120, 100, 70), a, stroke=OUTW))
    c.drawOval(skia.Rect(-22, -34, -8, -12), paint((255, 255, 255), a * 0.6, blur=2))
    for (sx, sy, r) in ((14, 18, 4), (-10, 26, 3), (20, -6, 2.5)): c.drawCircle(sx, sy, r, paint((170, 160, 110), a * 0.6))
    if cracked:
        cr = polyline_path([(-35, -2), (-24, -10), (-14, 2), (-4, -12), (6, 0), (16, -14), (26, -2), (35, -8)])
        c.drawPath(cr, paint((90, 70, 50), a, stroke=3.2))
        c.drawPath(poly_path([(-4, -12), (6, 0), (16, -14), (8, -20)]), paint((40, 34, 30), a * 0.85))
        c.drawPath(polyline_path([(6, 0), (2, 10)]), paint((90, 70, 50), a, stroke=2.2))
        # little shell chip on the side
        for sp_ in ([(42, 38), (54, 33), (56, 42)], [(-50, 40), (-40, 36), (-42, 44)]):
            c.drawPath(poly_path(sp_), paint((236, 226, 196), a)); c.drawPath(poly_path(sp_), paint((120, 100, 70), a, stroke=1.6))
    c.restore()

def no_sign(c, x, y, r, a=1.0):
    """red prohibition ring with slash"""
    if a <= 0.003: return
    c.drawCircle(x, y, r, paint((255, 70, 80), a * 0.25, stroke=r * 0.3, blur=6))
    c.drawCircle(x, y, r, paint((236, 60, 70), a, stroke=r * 0.16))
    d = r * 0.7
    c.drawLine(x - d, y - d, x + d, y + d, paint((236, 60, 70), a, stroke=r * 0.16, cap='butt'))

# ================================================================== equipment
# Palette used by the polished equipment drawers (also re-exported for bundles).
GAS = (110, 220, 255)
PE_Y = (246, 198, 58)
STEEL_C = (150, 160, 178)
RUST = (150, 96, 70)
ODOR = (190, 230, 90)
HEAT = (255, 110, 60)
GRASS = (88, 150, 92)
SALT = (226, 230, 238)
from .art import flow_cont, LIT, RED, WATER, rr, grad_rr

def cyl_v(c, x0, y0, x1, y1, base, a=1.0, r=0.0, ol=True):
    """vertical cylinder (lit from upper-left)"""
    if a <= 0.003: return
    p = rpath(x0, y0, x1, y1, r)
    c.drawPath(p, lin((x0, 0), (x1, 0), [sh(base, -0.02), sh(base, 0.32), base, sh(base, -0.38)], a, [0, 0.22, 0.55, 1]))
    if ol: c.drawPath(p, paint(sh(base, -0.5), a, stroke=OUTW))

def cyl_h(c, x0, y0, x1, y1, base, a=1.0, r=0.0, ol=True):
    """horizontal cylinder"""
    if a <= 0.003: return
    p = rpath(x0, y0, x1, y1, r)
    c.drawPath(p, lin((0, y0), (0, y1), [sh(base, 0.05), sh(base, 0.35), base, sh(base, -0.38)], a, [0, 0.2, 0.5, 1]))
    if ol: c.drawPath(p, paint(sh(base, -0.5), a, stroke=OUTW))

def box(c, x0, y0, x1, y1, base, a=1.0, r=4.0, ol=True, ow=None, k=0.18):
    """flat panel with gentle top-light gradient + rim highlight"""
    if a <= 0.003: return
    p = rpath(x0, y0, x1, y1, r)
    c.drawPath(p, lin((0, y0), (0, y1), [sh(base, k), sh(base, -k)], a))
    c.save(); c.clipPath(p, skia.ClipOp.kIntersect, True)
    c.drawLine(x0, y0 + 1.5, x1, y0 + 1.5, paint((255, 255, 255), a * 0.35, stroke=2))
    c.restore()
    if ol: c.drawPath(p, paint(sh(base, -0.5), a, stroke=ow or OUTW))

def hexnut(c, x, y, w, h, base, a=1.0):
    if a <= 0.003: return
    p = rpath(x - w / 2, y - h / 2, x + w / 2, y + h / 2, 2)
    c.drawPath(p, lin((x - w / 2, 0), (x + w / 2, 0), [sh(base, 0.25), base, sh(base, 0.1), sh(base, -0.3)], a, [0, 0.33, 0.66, 1]))
    for fx in (-w / 6, w / 6): c.drawLine(x + fx, y - h / 2 + 1, x + fx, y + h / 2 - 1, paint(sh(base, -0.35), a * 0.6, stroke=1.2))
    c.drawPath(p, paint(sh(base, -0.5), a, stroke=OUTW * 0.8))

def handwheel(c, x, y, r, a=1.0, color=(250, 196, 54)):
    if a <= 0.003: return
    c.drawCircle(x, y, r, paint(sh(color, -0.45), a, stroke=r * 0.42))
    c.drawCircle(x, y, r, paint(color, a, stroke=r * 0.26))
    for k in range(4):
        an = k * math.pi / 4 * 2 + 0.4
        c.drawLine(x, y, x + r * math.cos(an), y + r * math.sin(an), paint(sh(color, -0.15), a, stroke=r * 0.16))
    c.drawCircle(x, y, r * 0.22, paint(sh(color, -0.3), a))

def puff(c, x, y, t, a=1.0, n=3, rise=70, r0=8, r1=24, drift=16, col_=(210, 220, 236), speed=0.5):
    for k in range(n):
        ph = (t * speed + k / n) % 1
        c.drawCircle(x + ph * drift, y - ph * rise, r0 + ph * (r1 - r0), paint(col_, a * 0.28 * (1 - ph) * min(1, ph * 6), blur=r0 * 0.7 + ph * 6))

# ------------------------------------------------------------------ pipe (cylindrical shading)
def pipe(c, pts, w, a=1.0, kind='steel', grow=1.0, flow=0.0, t=0.0, spacing=None, speed=140, dotc=GAS, glow=0.0, r=None):
    if a <= 0.003 or grow <= 0.001: return
    P = partial_polyline(pts, grow) if grow < 1 else pts
    if len(P) < 2: return
    body = {'steel': (156, 166, 186), 'pe': (246, 198, 58), 'iron': (150, 96, 70), 'dark': (74, 84, 106), 'gas': (90, 150, 190)}[kind]
    path = polyline_path(P)
    if glow > 0: c.drawPath(path, paint(dotc, a * glow * 0.45, stroke=w * 2.6, blur=w * 0.9))
    if w >= 10:
        c.save(); c.translate(0, w * 0.22); c.drawPath(path, paint((0, 0, 0), a * 0.28, stroke=w + 6, blur=w * 0.25 + 1.5)); c.restore()
    c.drawPath(path, paint(sh(body, -0.55), a, stroke=w + 4.5))
    c.drawPath(path, paint(sh(body, -0.2), a, stroke=w))
    c.drawPath(path, paint(body, a, stroke=w * 0.62))
    off = w * 0.17
    c.save(); c.translate(-off * 0.6, -off)
    c.drawPath(path, paint(sh(body, 0.55), a * 0.75, stroke=max(1.2, w * 0.16)))
    c.restore()
    if flow > 0.01:
        flow_cont(c, P, t, dotc, spacing or max(26, w * 2.2), speed, max(3, w * 0.2), a * flow)

# ------------------------------------------------------------------ flames
def blue_flame(c, px, py, h, wd, a=1.0):
    if a <= 0.003 or h <= 0.5: return
    p = skia.Path(); p.moveTo(px - wd, py); p.cubicTo(px - wd, py - h * 0.45, px - wd * 0.25, py - h * 0.7, px, py - h)
    p.cubicTo(px + wd * 0.25, py - h * 0.7, px + wd, py - h * 0.45, px + wd, py); p.close()
    c.drawPath(p, lin((0, py), (0, py - h), [(40, 80, 240), (70, 150, 255), (150, 210, 255)], a, [0, 0.55, 1]))
    q = skia.Path(); hq = h * 0.5; wq = wd * 0.5
    q.moveTo(px - wq, py); q.cubicTo(px - wq, py - hq * 0.5, px - wq * 0.2, py - hq * 0.8, px, py - hq)
    q.cubicTo(px + wq * 0.2, py - hq * 0.8, px + wq, py - hq * 0.5, px + wq, py); q.close()
    c.drawPath(q, paint((215, 240, 255), a * 0.9))

def fire_flame(c, x, y, s=1.0, a=1.0, t=0.0):
    """warm flame, base at (x,y)"""
    if a <= 0.003: return
    for cc, sc in (((255, 86, 40), 1.0), ((255, 160, 50), 0.7), ((255, 236, 170), 0.38)):
        fl = 1 + 0.08 * math.sin(t * 17 + sc * 5) + 0.05 * math.sin(t * 29)
        hh = 70 * s * sc * fl; ww = 32 * s * sc
        sway = 4 * s * math.sin(t * 9 + sc * 3)
        p = skia.Path(); p.moveTo(x + sway, y - hh)
        p.cubicTo(x + ww * 0.3, y - hh * 0.6, x + ww, y - hh * 0.45, x + ww * 0.8, y - hh * 0.1)
        p.cubicTo(x + ww * 0.6, y + hh * 0.12, x - ww * 0.6, y + hh * 0.12, x - ww * 0.8, y - hh * 0.1)
        p.cubicTo(x - ww, y - hh * 0.45, x - ww * 0.3, y - hh * 0.6, x + sway, y - hh)
        if sc == 1.0: c.drawPath(p, paint(cc, a * 0.5, blur=14 * s))
        c.drawPath(p, lin((0, y), (0, y - hh), [sh(cc, 0.1), cc], a))

# ------------------------------------------------------------------ stove
def burner(c, x, y, s=1.0, a=1.0, fl=0.0, t=0.0):
    if a <= 0.003: return
    rx, ry = 120 * s, 34 * s
    c.drawOval(skia.Rect(x - rx * 1.28, y - ry * 1.28, x + rx * 1.28, y + ry * 1.28), rad(x, y, rx * 1.3, [(48, 50, 60), (22, 24, 30)], a))
    if fl > 0.01:
        c.drawOval(skia.Rect(x - rx * 0.95, y - ry * 1.5 - 30 * s, x + rx * 0.95, y + ry * 0.7), paint((60, 120, 255), a * fl * 0.35, blur=26 * s))
    n = 22
    order = sorted(range(n), key=lambda k: math.sin(2 * math.pi * k / n))
    def flames(back):
        if fl <= 0.01: return
        for k in order:
            an = 2 * math.pi * k / n
            if (math.sin(an) < 0) != back: continue
            px = x + rx * 0.6 * math.cos(an); py = y + ry * 0.6 * math.sin(an)
            front = 0.6 + 0.4 * max(0, math.sin(an))
            h = (38 + 8 * math.sin(t * 19 + k * 1.7)) * s * fl
            blue_flame(c, px, py, h, 6.5 * s, a * fl * front)
    # burner base + cap
    c.drawOval(skia.Rect(x - rx * 0.68, y - ry * 0.68 + 3 * s, x + rx * 0.68, y + ry * 0.68 + 3 * s), paint((20, 20, 26), a))
    c.drawOval(skia.Rect(x - rx * 0.66, y - ry * 0.66, x + rx * 0.66, y + ry * 0.66), lin((0, y - ry), (0, y + ry), [(150, 154, 166), (86, 90, 102)], a))
    flames(True)
    c.drawOval(skia.Rect(x - rx * 0.46, y - ry * 0.46 - 4 * s, x + rx * 0.46, y + ry * 0.46 - 4 * s), lin((0, y - ry * 0.5), (0, y + ry * 0.5), [(96, 100, 112), (44, 46, 56)], a))
    c.drawOval(skia.Rect(x - rx * 0.3, y - ry * 0.32 - 6 * s, x + rx * 0.05, y - ry * 0.05 - 6 * s), paint((255, 255, 255), a * 0.18, blur=2 * s))
    flames(False)
    # cast-iron grate (on top)
    gc = (58, 60, 70)
    for k in range(8):
        an = k * math.pi / 4 + math.pi / 8
        x0_, y0_ = x + rx * 0.82 * math.cos(an), y + ry * 0.82 * math.sin(an)
        x1_, y1_ = x + rx * 1.26 * math.cos(an), y + ry * 1.26 * math.sin(an)
        c.drawLine(x0_, y0_, x1_, y1_, paint((20, 20, 26), a, stroke=9 * s))
        c.drawLine(x0_, y0_ - 1.5 * s, x1_, y1_ - 1.5 * s, paint(gc, a, stroke=6 * s))
        c.drawLine(x0_, y0_ - 3 * s, x1_, y1_ - 3 * s, paint((120, 124, 138), a * 0.5, stroke=1.6 * s))
    c.drawOval(skia.Rect(x - rx * 1.26, y - ry * 1.26, x + rx * 1.26, y + ry * 1.26), paint((20, 20, 26), a, stroke=9 * s))
    c.drawOval(skia.Rect(x - rx * 1.26, y - ry * 1.26 - 1.5 * s, x + rx * 1.26, y + ry * 1.26 - 1.5 * s), paint(gc, a, stroke=5.5 * s))

def knob(c, x, y, r, ang, a=1.0):
    if a <= 0.003: return
    c.drawCircle(x, y + r * 0.18, r * 1.12, paint((0, 0, 0), a * 0.45, blur=r * 0.25))
    c.drawCircle(x, y, r * 1.08, paint((70, 74, 86), a))
    c.drawCircle(x, y, r, rad(x - r * 0.35, y - r * 0.4, r * 1.5, [(250, 252, 255), (200, 204, 214), (130, 136, 150)], a, [0, 0.5, 1]))
    c.drawCircle(x, y, r * 0.7, rad(x - r * 0.2, y - r * 0.3, r, [(236, 238, 244), (170, 176, 188)], a))
    dx, dy = math.sin(ang), -math.cos(ang)
    c.drawLine(x - dx * r * 0.62, y - dy * r * 0.62, x + dx * r * 0.62, y + dy * r * 0.62, paint((60, 64, 78), a, stroke=r * 0.32))
    c.drawLine(x - dx * r * 0.62, y - dy * r * 0.62 - r * 0.05, x + dx * r * 0.62, y + dy * r * 0.62 - r * 0.05, paint((120, 126, 140), a, stroke=r * 0.1))
    c.drawCircle(x + dx * r * 0.82, y + dy * r * 0.82, r * 0.1, paint((255, 80, 70), a))

def stove(c, x, y, s=1.0, a=1.0, knob_ang=0.0, fl=0.0, t=0.0):
    """stainless range; top-surface centre (x,y); width 520s; bottom y+470s"""
    if a <= 0.003: return
    w = 520 * s; L, R = x - w / 2, x + w / 2
    contact(c, x, y + 470 * s, w * 0.52, 14 * s, a, 0.45)
    # back guard
    box(c, L + 30 * s, y - 132 * s, R - 30 * s, y - 88 * s, (176, 182, 196), a, 8 * s, ow=2 * s)
    top = poly_path([(L + 40 * s, y - 90 * s), (R - 40 * s, y - 90 * s), (R, y + 60 * s), (L, y + 60 * s)])
    c.drawPath(top, lin((0, y - 90 * s), (0, y + 60 * s), [(40, 44, 56), (24, 26, 34)], a))
    c.drawPath(top, paint((150, 156, 172), a, stroke=4 * s))
    c.save(); c.clipPath(top, skia.ClipOp.kIntersect, True)
    c.drawPath(poly_path([(L + 60 * s, y - 90 * s), (L + 160 * s, y - 90 * s), (L + 90 * s, y + 60 * s), (L - 10 * s, y + 60 * s)]), paint((255, 255, 255), a * 0.05))
    c.restore()
    burner(c, x - 120 * s, y - 32 * s, 0.62 * s, a, 0, t)
    burner(c, x + 120 * s, y - 32 * s, 0.62 * s, a, 0, t)
    burner(c, x, y + 20 * s, 0.82 * s, a, fl, t)
    # control panel
    box(c, L, y + 60 * s, R, y + 170 * s, (206, 210, 222), a, 6 * s, ow=2.4 * s, k=0.1)
    for k, dx in enumerate((-180, -90, 90, 180)):
        knob(c, x + dx * s, y + 115 * s, 26 * s, 0, a)
    knob(c, x, y + 115 * s, 30 * s, knob_ang, a)
    # oven body + door
    box(c, L, y + 170 * s, R, y + 470 * s, (198, 202, 214), a, 6 * s, ow=2.4 * s, k=0.12)
    c.drawPath(rpath(L + 70 * s, y + 182 * s, R - 70 * s, y + 200 * s, 9 * s), paint((0, 0, 0), a * 0.3, blur=3 * s))
    hb = rpath(L + 60 * s, y + 178 * s, R - 60 * s, y + 194 * s, 8 * s)
    c.drawPath(hb, lin((0, y + 178 * s), (0, y + 194 * s), [(240, 242, 248), (140, 146, 160)], a)); c.drawPath(hb, paint((100, 106, 120), a, stroke=1.6 * s))
    win = rpath(L + 50 * s, y + 216 * s, R - 50 * s, y + 380 * s, 14 * s)
    c.drawPath(win, lin((0, y + 216 * s), (0, y + 380 * s), [(40, 44, 58), (16, 18, 26)], a))
    c.drawPath(win, paint((90, 96, 112), a, stroke=3 * s))
    c.save(); c.clipPath(win, skia.ClipOp.kIntersect, True)
    c.drawPath(poly_path([(L + 90 * s, y + 216 * s), (L + 170 * s, y + 216 * s), (L + 110 * s, y + 380 * s), (L + 30 * s, y + 380 * s)]), paint((255, 255, 255), a * 0.07))
    c.drawLine(L + 70 * s, y + 330 * s, R - 70 * s, y + 330 * s, paint((70, 74, 88), a * 0.8, stroke=3 * s))
    c.restore()
    box(c, L + 20 * s, y + 400 * s, R - 20 * s, y + 456 * s, (186, 190, 204), a, 5 * s, ow=1.6 * s, k=0.08)
    c.drawLine(x - 50 * s, y + 412 * s, x + 50 * s, y + 412 * s, paint((120, 126, 140), a, stroke=4 * s))
    for fx in (L + 24 * s, R - 44 * s): rr(c, fx, y + 466 * s, fx + 20 * s, y + 476 * s, 2 * s, paint((30, 32, 40), a))

# ------------------------------------------------------------------ basement / laundry appliances
def furnace(c, x, gy, s=1.0, a=1.0, t=0.0, on=1.0):
    """upright furnace cabinet; bottom-centre (x,gy); 180x180 at s=1"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    contact(c, 0, 0, 100, 8, a, 0.45)
    box(c, -90, -180, 90, 0, (182, 188, 202), a, 8, k=0.12)
    c.drawLine(-90, -96, 90, -96, paint((110, 116, 132), a, stroke=2.5))
    for k in range(6):  # louvers
        yy = -164 + k * 10
        c.drawPath(rpath(-60, yy, 60, yy + 5, 2.5), paint((96, 102, 118), a))
        c.drawLine(-58, yy + 6.5, 58, yy + 6.5, paint((236, 240, 248), a * 0.6, stroke=1.2))
    # data plate + controls
    rr(c, 44, -88, 76, -70, 3, paint((236, 238, 244), a)); c.drawCircle(-66, -80, 5, paint((80, 220, 120) if on > 0.5 else (90, 96, 110), a))
    # viewport with flames
    vp = rpath(-46, -64, 46, -16, 8)
    c.drawPath(vp, lin((0, -64), (0, -16), [(30, 22, 30), (12, 10, 16)], a)); c.drawPath(vp, paint((80, 86, 100), a, stroke=3))
    if on > 0.01:
        c.save(); c.clipPath(vp, skia.ClipOp.kIntersect, True)
        c.drawRect(skia.Rect(-46, -40, 46, -16), paint((80, 140, 255), a * on * 0.35, blur=10))
        for k in range(6): blue_flame(c, -32 + k * 13, -20, (16 + 4 * math.sin(t * 17 + k * 2)) * on, 4.5, a * on)
        c.restore()
    c.save(); c.clipPath(vp, skia.ClipOp.kIntersect, True)
    c.drawPath(poly_path([(-36, -64), (-20, -64), (-36, -16), (-52, -16)]), paint((255, 255, 255), a * 0.08)); c.restore()
    c.drawRect(skia.Rect(-90, -6, 90, 0), paint((70, 76, 90), a))
    c.restore()

def water_heater(c, x, gy, s=1.0, a=1.0, t=0.0, on=1.0):
    """tank water heater; bottom-centre (x,gy); 120 wide x 180 tall"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    contact(c, 0, 0, 70, 7, a, 0.45)
    # flue + draft hood (behind the top)
    cyl_v(c, -38, -204, -18, -170, (150, 158, 176), a)
    c.drawPath(poly_path([(-44, -196), (-12, -196), (-18, -184), (-38, -184)]), paint((130, 138, 156), a))
    body = skia.Path(); body.moveTo(-60, -150); body.cubicTo(-60, -186, 60, -186, 60, -150); body.lineTo(60, -8); body.quadTo(60, 0, 52, 0)
    body.lineTo(-52, 0); body.quadTo(-60, 0, -60, -8); body.close()
    base = (210, 214, 226)
    c.drawPath(body, lin((-60, 0), (60, 0), [sh(base, -0.05), sh(base, 0.3), base, sh(base, -0.35)], a, [0, 0.25, 0.55, 1]))
    c.drawPath(body, paint(sh(base, -0.5), a, stroke=OUTW))
    for yy in (-150, -14): c.drawLine(-60, yy, 60, yy, paint(sh(base, -0.3), a, stroke=2))
    # hot/cold stubs on top
    for dx, cc in ((22, (220, 80, 70)), (40, (70, 140, 230))):
        cyl_v(c, dx - 5, -190, dx + 5, -170, (200, 150, 100), a); c.drawCircle(dx, -192, 4, paint(cc, a))
    # T&P valve + label
    cyl_h(c, 60, -128, 76, -118, (200, 160, 90), a, 3)
    rr(c, -28, -120, 28, -84, 4, paint((246, 248, 252), a)); rr(c, -28, -120, 28, -84, 4, paint((150, 156, 170), a, stroke=1.5))
    for k in range(3): c.drawLine(-20, -110 + k * 9, 14 - k * 8, -110 + k * 9, paint((150, 156, 170), a, stroke=2))
    # gas control valve
    box(c, -26, -72, 26, -44, (60, 66, 82), a, 5)
    c.drawCircle(0, -58, 8, paint((230, 70, 60), a)); c.drawCircle(-2, -60, 2.5, paint((255, 255, 255), a * 0.6))
    # burner access door
    door_ = rpath(-24, -36, 24, -10, 4)
    c.drawPath(door_, paint((22, 18, 24), a)); c.drawPath(door_, paint((90, 96, 110), a, stroke=2))
    if on > 0.01:
        c.save(); c.clipPath(door_, skia.ClipOp.kIntersect, True)
        for k in range(4): blue_flame(c, -14 + k * 9.5, -12, (12 + 3 * math.sin(t * 19 + k)) * on, 3.6, a * on)
        c.restore()
    c.restore()

def dryer(c, x, gy, s=1.0, a=1.0, t=0.0, on=1.0):
    """front-load gas dryer; bottom-centre (x,gy); 160 wide x 170 tall"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    contact(c, 0, 0, 90, 7, a, 0.45)
    box(c, -80, -170, 80, -4, (236, 238, 246), a, 10, k=0.1)
    box(c, -80, -170, 80, -138, (210, 214, 226), a, 10, k=0.08)
    rr(c, -66, -162, -10, -146, 4, paint((24, 30, 46), a))
    for k in range(3): c.drawCircle(-58 + k * 12, -154, 2.6, paint((90, 220, 255) if on > 0.5 else (70, 80, 100), a))
    knob(c, 50, -154, 10, 0.8, a)
    cx, cy = 0, -72
    c.drawCircle(cx, cy + 3, 54, paint((0, 0, 0), a * 0.25, blur=4))
    c.drawCircle(cx, cy, 52, rad(cx - 20, cy - 24, 80, [(250, 252, 255), (176, 182, 196), (120, 126, 140)], a, [0, 0.6, 1]))
    c.drawCircle(cx, cy, 52, paint((100, 106, 120), a, stroke=2))
    glass = opath(cx, cy, 38, 38)
    c.drawPath(glass, rad(cx, cy, 40, [(60, 76, 110), (26, 32, 52)], a))
    c.save(); c.clipPath(glass, skia.ClipOp.kIntersect, True)
    cols = [(240, 120, 90), (100, 180, 240), (250, 214, 100), (150, 120, 220)]
    for k in range(4):
        an = t * 3.0 * on + k * math.pi / 2
        bx, by = cx + 18 * math.cos(an), cy + 16 + 10 * math.sin(an) * 0.6 + (8 if math.sin(an) > 0 else 0)
        c.drawOval(skia.Rect(bx - 14, by - 9, bx + 14, by + 9), paint(cols[k], a * 0.9))
    c.drawPath(poly_path([(cx - 30, cy - 40), (cx - 10, cy - 40), (cx - 40, cy + 20), (cx - 50, cy)]), paint((255, 255, 255), a * 0.14))
    c.restore()
    c.drawPath(glass, paint((70, 76, 90), a, stroke=3))
    rr(c, 34, cy - 8, 44, cy + 8, 3, paint((150, 156, 170), a))
    for fx in (-70, 56): rr(c, fx, -6, fx + 14, 2, 2, paint((60, 64, 76), a))
    c.restore()

# ------------------------------------------------------------------ upstream
WH_RED = (214, 64, 54)
def _flange(c, x0, x1, y, h, base, a):
    box(c, x0, y - h / 2, x1, y + h / 2, base, a, 3, k=0.2)
    n = max(2, int((x1 - x0) / 16))
    for k in range(n):
        bx = x0 + 6 + k * (x1 - x0 - 12) / (n - 1)
        c.drawCircle(bx, y, 2.4, paint(sh(base, -0.5), a))

def wellhead(c, x, gy, s=1.0, a=1.0, glow=0.0):
    """'Christmas tree' valve stack standing on ground y"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    if glow > 0: c.drawCircle(0, -110, 140, paint(GAS, a * glow * 0.35, blur=44))
    contact(c, 0, 0, 80, 9, a, 0.5)
    box(c, -64, -14, 64, 2, (120, 126, 140), a, 3)
    red = WH_RED
    _flange(c, -46, 46, -24, 18, sh(red, -0.1), a)
    cyl_v(c, -30, -58, 30, -32, red, a, 3)
    _flange(c, -38, 38, -62, 10, sh(red, -0.12), a)
    # lower + upper master valves w/ handwheels on the left
    for yy in (-86, -126):
        cyl_v(c, -26, yy - 16, 26, yy + 16, red, a, 5)
        _flange(c, -34, 34, yy + 19, 7, sh(red, -0.12), a)
        c.drawLine(-26, yy, -50, yy, paint((150, 156, 170), a, stroke=5))
        handwheel(c, -56, yy, 17, a)
    # flow cross + wing valve + flowline to the right
    cyl_h(c, -34, -168, 34, -142, red, a, 4)
    cyl_h(c, 34, -164, 54, -146, sh(red, -0.05), a, 2)
    cyl_v(c, 54, -172, 84, -138, red, a, 5)
    c.drawLine(69, -172, 69, -186, paint((150, 156, 170), a, stroke=4)); handwheel(c, 69, -192, 11, a)
    pipe(c, [(84, -155), (128, -155), (128, 0)], 13, a, 'steel')
    # swab valve + cap + gauge
    cyl_v(c, -22, -200, 22, -172, red, a, 5)
    c.drawLine(-22, -186, -40, -186, paint((150, 156, 170), a, stroke=4)); handwheel(c, -46, -186, 12, a)
    cyl_v(c, -14, -218, 14, -200, sh(red, -0.1), a, 3)
    c.drawLine(0, -218, 0, -228, paint((150, 156, 170), a, stroke=4))
    c.drawCircle(0, -240, 14, paint((60, 64, 76), a)); c.drawCircle(0, -240, 11, paint((246, 248, 252), a))
    c.drawLine(0, -240, 7, -246, paint((220, 60, 50), a, stroke=2))
    c.restore()

def drill_rig(c, x, gy, s=1.0, a=1.0, t=0.0, run=1.0):
    """land drilling rig: derrick, drill floor, doghouse, pipe rack; base centre at (x, gy)"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    contact(c, 0, 0, 220, 10, a, 0.5)
    stl = (232, 236, 244); org = (240, 140, 50)
    # substructure
    box(c, -110, -62, 110, -46, org, a, 3)
    for lx in (-100, -40, 40, 100): cyl_v(c, lx - 7, -46, lx + 7, 0, sh(org, -0.15), a, 2)
    for k in range(3):
        xa = -100 + k * 70
        c.drawLine(xa, -46, xa + 60, 0, paint(sh(org, -0.3), a, stroke=3)); c.drawLine(xa + 60, -46, xa, 0, paint(sh(org, -0.3), a, stroke=3))
    # derrick (lattice)
    B, T_, top = 56, 16, -430
    legs = [(-B, -62), (-T_, top)], [(B, -62), (T_, top)]
    for (p0, p1) in legs: c.drawLine(p0[0], p0[1], p1[0], p1[1], paint(sh(stl, -0.5), a, stroke=8)); c.drawLine(p0[0], p0[1], p1[0], p1[1], paint(stl, a, stroke=5))
    n = 9
    for k in range(n):
        y0 = lerp(-62, top, k / n); y1 = lerp(-62, top, (k + 1) / n)
        w0 = lerp(B, T_, k / n); w1 = lerp(B, T_, (k + 1) / n)
        pp = paint(sh(stl, -0.15), a, stroke=2.4)
        c.drawLine(-w0, y0, w0, y0, pp); c.drawLine(-w0, y0, w1, y1, pp); c.drawLine(w0, y0, -w1, y1, pp)
    box(c, -26, top - 22, 26, top + 2, (190, 196, 210), a, 3)          # crown block
    # traveling block + drill pipe (moves while drilling)
    by = lerp(-330, -120, (t * 0.18 * run) % 1)
    c.drawLine(-4, top, -4, by, paint((90, 96, 110), a, stroke=1.6)); c.drawLine(4, top, 4, by, paint((90, 96, 110), a, stroke=1.6))
    cyl_v(c, -12, by, 12, by + 34, (250, 200, 60), a, 4)
    cyl_v(c, -5, by + 34, 5, -46, (150, 158, 176), a)
    # doghouse + mud tanks + pipe rack
    box(c, -210, -112, -118, -46, (70, 120, 200), a, 4)
    for wx in (-196, -160): rr(c, wx, -96, wx + 26, -76, 3, paint(LIT, a * 0.8))
    box(c, 120, -40, 230, 0, (110, 118, 136), a, 4)
    for k in range(5): cyl_h(c, 124, -52 - k * 9, 236, -45 - k * 9, (176, 184, 200), a, 3)
    c.restore()

def tiny_well(c, x, y, s=1.0, a=1.0):
    """map-view well badge (centre x,y)"""
    if a <= 0.003: return
    c.drawCircle(x, y + 3 * s, 25 * s, paint((0, 0, 0), a * 0.4, blur=4 * s))
    c.drawCircle(x, y, 24 * s, rad(x - 6 * s, y - 8 * s, 30 * s, [(250, 120, 100), (200, 56, 46)], a))
    c.drawCircle(x, y, 24 * s, paint((255, 236, 220), a, stroke=3 * s))
    W_ = (255, 255, 255)
    rr(c, x - 12 * s, y + 9 * s, x + 12 * s, y + 13 * s, 1 * s, paint(W_, a))          # base
    rr(c, x - 3.5 * s, y - 12 * s, x + 3.5 * s, y + 10 * s, 1 * s, paint(W_, a))        # stem
    for yy in (2, -7): rr(c, x - 7 * s, y + (yy - 2.5) * s, x + 7 * s, y + (yy + 2.5) * s, 1.2 * s, paint(W_, a))
    c.drawCircle(x - 10 * s, y + 2 * s, 3 * s, paint(W_, a, stroke=1.6 * s)); c.drawCircle(x - 10 * s, y - 7 * s, 3 * s, paint(W_, a, stroke=1.6 * s))
    c.drawLine(x + 3 * s, y - 2.5 * s, x + 12 * s, y - 2.5 * s, paint(W_, a, stroke=2.6 * s))
    c.drawCircle(x, y - 15 * s, 3 * s, paint(W_, a))

# ------------------------------------------------------------------ processing plant
def _tower(c, x, w, h, base, a, cap=True, ladder=True):
    cyl_v(c, x - w / 2, -h, x + w / 2, 0, base, a, w * 0.45 if cap else 4)
    for yy in range(int(-h + 50), -20, 56):
        c.drawLine(x - w / 2 - 6, yy, x + w / 2 + 6, yy, paint((60, 66, 84), a, stroke=3))
        c.drawLine(x - w / 2 - 6, yy - 10, x + w / 2 + 6, yy - 10, paint((120, 130, 150), a * 0.8, stroke=1.4))
    if ladder:
        c.drawLine(x + w / 2 + 3, -h + 30, x + w / 2 + 3, 0, paint((70, 78, 96), a, stroke=1.6))

def plant_icon(c, x, gy, s=1.0, a=1.0, t=0.0, glow=0.0):
    """gas processing plant on ground y (spans ~-205..+200, up to ~-330)"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    if glow > 0: c.drawCircle(0, -120, 230, paint(GAS, a * glow * 0.25, blur=60))
    contact(c, 0, 0, 215, 10, a, 0.45)
    # pipe rack (behind)
    for px in (-80, -10, 60, 130):
        c.drawLine(px, -150, px, 0, paint((84, 94, 118), a, stroke=5))
    c.drawLine(-90, -150, 190, -150, paint((84, 94, 118), a, stroke=5))
    for k, cc in enumerate(((180, 190, 208), (246, 198, 58), (150, 196, 230))):
        yy = -162 - k * 9
        c.drawLine(-90, yy, 190, yy, paint(sh(cc, -0.45), a, stroke=8)); c.drawLine(-90, yy, 190, yy, paint(cc, a, stroke=5))
        c.drawLine(-90, yy - 1.5, 190, yy - 1.5, paint(sh(cc, 0.5), a * 0.6, stroke=1.4))
    # towers
    _tower(c, 50, 42, 240, (200, 208, 222), a)
    _tower(c, 112, 50, 300, (214, 220, 232), a)
    _tower(c, 168, 36, 200, (190, 198, 214), a)
    # flare stack with small flame
    cyl_v(c, 190, -280, 198, 0, (150, 158, 176), a)
    fire_flame(c, 194, -280, 0.28, a, t)
    puff(c, 112, -310, t, a, 3, 80, 10, 30, 30)
    # sphere tank on legs
    for lx in (-58, -22): c.drawLine(lx, -70, lx, 0, paint((96, 104, 124), a, stroke=5))
    c.drawCircle(-40, -96, 44, rad(-56, -114, 64, [(250, 252, 255), (206, 212, 226), (136, 144, 162)], a, [0, 0.5, 1]))
    c.drawCircle(-40, -96, 44, paint((90, 98, 118), a, stroke=OUTW))
    c.drawLine(-84, -96, 4, -96, paint((150, 158, 176), a, stroke=2))
    # control building
    box(c, -205, -96, -92, 0, (74, 92, 136), a, 4, k=0.14)
    c.drawPath(rpath(-212, -106, -86, -94, 3), paint((50, 60, 92), a))
    for k in range(3):
        wx = -194 + k * 34
        rr(c, wx, -78, wx + 24, -52, 3, paint(LIT, a * 0.85)); rr(c, wx, -78, wx + 24, -52, 3, paint((40, 50, 80), a, stroke=2))
        c.drawLine(wx + 12, -78, wx + 12, -52, paint((40, 50, 80), a * 0.7, stroke=1.5))
    rr(c, -126, -42, -104, 0, 2, paint((40, 50, 80), a))
    c.restore()

# ------------------------------------------------------------------ compressor station
def compressor(c, x, gy, s=1.0, a=1.0, t=0.0, glow=0.0, on=1.0):
    """compressor station building on ground y (~±125 wide, stacks to ~-215)"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    if glow > 0: c.drawCircle(0, -80, 160, paint(GAS, a * glow * 0.35, blur=40))
    contact(c, 0, 0, 130, 10, a, 0.5)
    # exhaust stacks (behind roof)
    for dx in (-62, 62):
        cyl_v(c, dx - 10, -212, dx + 10, -130, (140, 148, 166), a, 2)
        rr(c, dx - 14, -218, dx + 14, -210, 2, paint((96, 104, 124), a))
        puff(c, dx, -224, t, a * on, 3, 64, 7, 20, 14, speed=0.6)
    roof = poly_path([(-122, -118), (-100, -150), (100, -150), (122, -118)])
    c.drawPath(roof, lin((0, -150), (0, -118), [(110, 122, 150), (76, 86, 110)], a)); c.drawPath(roof, paint((50, 58, 78), a, stroke=OUTW))
    box(c, -24, -164, 24, -150, (150, 158, 176), a, 2)
    # corrugated walls
    wall = rpath(-112, -120, 112, 0, 3)
    c.drawPath(wall, lin((-112, 0), (112, 0), [(214, 220, 232), (188, 196, 210), (160, 168, 186)], a))
    c.save(); c.clipPath(wall, skia.ClipOp.kIntersect, True)
    for xx in range(-108, 112, 9): c.drawLine(xx, -120, xx, 0, paint((140, 148, 166), a * 0.55, stroke=1.4))
    c.restore(); c.drawPath(wall, paint((90, 98, 118), a, stroke=OUTW))
    # roll-up door, man door, fan housing
    box(c, -94, -84, -32, 0, (170, 178, 194), a, 2, k=0.06)
    for yy in range(-78, 0, 8): c.drawLine(-92, yy, -34, yy, paint((130, 138, 156), a, stroke=1.4))
    rr(c, 76, -60, 98, 0, 2, paint((70, 90, 140), a)); c.drawCircle(80, -30, 2, paint((230, 200, 90), a))
    fx, fy, fr = 22, -62, 34
    c.drawCircle(fx, fy, fr + 6, paint((90, 98, 118), a)); c.drawCircle(fx, fy, fr, paint((36, 44, 66), a))
    if glow > 0: c.drawCircle(fx, fy, fr, paint(GAS, a * glow * 0.4))
    for k in range(5):
        an = t * 8 * on + k * 2 * math.pi / 5
        bl = skia.Path(); bl.moveTo(fx, fy)
        bl.quadTo(fx + fr * 0.9 * math.cos(an - 0.35), fy + fr * 0.9 * math.sin(an - 0.35), fx + fr * 0.92 * math.cos(an + 0.15), fy + fr * 0.92 * math.sin(an + 0.15)); bl.close()
        c.drawPath(bl, paint((170, 214, 240), a))
    c.drawCircle(fx, fy, 7, paint((240, 244, 252), a))
    for k in range(4): c.drawLine(fx - fr, fy - fr * 0.6 + k * fr * 0.4, fx + fr, fy - fr * 0.6 + k * fr * 0.4, paint((200, 208, 222), a * 0.35, stroke=1.2))
    c.restore()

# ------------------------------------------------------------------ markers / trees
def marker_post(c, x, gy, s=1.0, a=1.0):
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    contact(c, 0, 0, 22, 4, a, 0.45)
    c.drawOval(skia.Rect(-18, -6, 18, 4), paint((90, 70, 50), a))
    cyl_v(c, -10, -150, 10, 0, (252, 208, 46), a, 3)
    # decal band
    rr(c, -10, -128, 10, -82, 1, paint((250, 250, 252), a))
    for yy in (-124, -96): c.drawRect(skia.Rect(-10, yy, 10, yy + 9), paint((30, 30, 36), a))
    c.drawPath(poly_path([(0, -114), (6, -104), (-6, -104)]), paint((236, 80, 40), a))
    c.drawLine(-10, -60, 10, -60, paint((255, 255, 255), a * 0.7, stroke=5))
    cap = skia.Path(); cap.moveTo(-15, -146); cap.cubicTo(-15, -178, 15, -178, 15, -146); cap.close()
    c.drawPath(cap, lin((-15, 0), (15, 0), [(255, 170, 70), (250, 120, 40), (200, 80, 30)], a))
    c.drawPath(cap, paint((140, 60, 20), a, stroke=OUTW * 0.8))
    rr(c, -16, -150, 16, -142, 2, paint((210, 90, 30), a))
    c.drawOval(skia.Rect(-9, -168, -1, -158), paint((255, 255, 255), a * 0.45))
    c.restore()

def tree(c, x, gy, s=1.0, a=1.0, shade=0.0):
    if a <= 0.003: return
    contact(c, x, gy, 36 * s, 5 * s, a, 0.35)
    cyl_v(c, x - 6 * s, gy - 46 * s, x + 6 * s, gy, (110, 76, 48), a)
    g = lerpc((70, 150, 90), (40, 96, 64), shade)
    for k, (w_, y0, y1) in enumerate(((44, -34, -88), (36, -70, -118), (26, -102, -148))):
        p = skia.Path(); p.moveTo(x - w_ * s, gy + y0 * s); p.quadTo(x, gy + (y0 + 8) * s, x + w_ * s, gy + y0 * s)
        p.lineTo(x + 3 * s, gy + y1 * s); p.quadTo(x, gy + (y1 - 4) * s, x - 3 * s, gy + y1 * s); p.close()
        c.drawPath(p, lin((x - w_ * s, 0), (x + w_ * s, 0), [sh(g, 0.15), g, sh(g, -0.3)], a))
        c.drawPath(p, paint(sh(g, -0.5), a, stroke=1.6 * s))

def map_tree(c, x, y, r, a=1.0, tone=0):
    if a <= 0.003: return
    g = [(48, 112, 74), (60, 132, 86), (40, 98, 66)][tone % 3]
    c.drawCircle(x + r * 0.25, y + r * 0.3, r, paint((6, 18, 14), a * 0.55, blur=r * 0.25))
    c.drawCircle(x, y, r, rad(x - r * 0.35, y - r * 0.4, r * 1.4, [sh(g, 0.3), g, sh(g, -0.3)], a, [0, 0.5, 1]))

# ------------------------------------------------------------------ regulator / valve / meter
def regulator(c, x, y, s=1.0, a=1.0, glow=0.0, color=(170, 180, 198)):
    """service/district regulator; (x,y) = centre of the pipe body"""
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    if glow > 0: c.drawCircle(0, -34, 96, paint(GAS, a * glow * 0.45, blur=30))
    # body casting with union nuts
    for dx in (-34, 34): hexnut(c, dx, 2, 14, 34, (190, 196, 210), a)
    box(c, -28, -16, 28, 22, (150, 158, 176), a, 7)
    # lower diaphragm case
    low = skia.Path(); low.moveTo(-58, -24); low.lineTo(58, -24); low.cubicTo(50, -10, 30, -12, 22, -14); low.lineTo(-22, -14); low.cubicTo(-30, -12, -50, -10, -58, -24); low.close()
    c.drawPath(low, lin((-58, 0), (58, 0), [sh(color, 0.1), sh(color, 0.3), sh(color, -0.35)], a)); c.drawPath(low, paint(sh(color, -0.5), a, stroke=OUTW))
    # upper bell
    bell = skia.Path(); bell.moveTo(-62, -28); bell.cubicTo(-62, -92, 62, -92, 62, -28); bell.close()
    c.drawPath(bell, lin((-62, 0), (62, 0), [sh(color, 0.05), sh(color, 0.4), color, sh(color, -0.4)], a, [0, 0.28, 0.55, 1]))
    c.drawPath(bell, paint(sh(color, -0.5), a, stroke=OUTW))
    c.drawPath(rpath(-68, -31, 68, -21, 4), lin((0, -31), (0, -21), [sh(color, 0.2), sh(color, -0.3)], a))
    c.drawPath(rpath(-68, -31, 68, -21, 4), paint(sh(color, -0.5), a, stroke=OUTW * 0.8))
    for k in range(7): c.drawCircle(-56 + k * 18.7, -26, 2.4, paint(sh(color, -0.55), a))
    # spring cap / bonnet
    cyl_v(c, -13, -98, 13, -78, sh(color, -0.05), a, 3); c.drawPath(rpath(-16, -104, 16, -96, 3), paint(sh(color, -0.25), a))
    # vent: elbow pointing down with screen
    cyl_h(c, 46, -62, 82, -50, sh(color, -0.1), a, 3)
    cyl_v(c, 74, -62, 88, -38, sh(color, -0.1), a, 3)
    c.drawPath(rpath(70, -40, 92, -32, 3), paint((60, 66, 80), a))
    for k in range(4): c.drawLine(72 + k * 6, -39, 72 + k * 6, -33, paint((150, 158, 176), a, stroke=1))
    c.drawOval(skia.Rect(-42, -78, -14, -64), paint((255, 255, 255), a * 0.28, blur=3))
    c.restore()

def valve(c, x, y, s=1.0, a=1.0, ang=0.0, glow=0.0, color=(250, 200, 60)):
    """quarter-turn ball valve; ang=0 -> lever along the pipe (open)"""
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    if glow > 0: c.drawCircle(0, -10, 62, paint(color, a * glow * 0.5, blur=22))
    brass = (206, 166, 84)
    for dx in (-24, 24): hexnut(c, dx, 0, 14, 34, brass, a)
    body = skia.Path(); body.addRRect(skia.RRect.MakeRectXY(skia.Rect(-18, -17, 18, 17), 10, 10))
    c.drawPath(body, rad(-6, -8, 30, [sh(brass, 0.4), brass, sh(brass, -0.35)], a, [0, 0.5, 1])); c.drawPath(body, paint(sh(brass, -0.5), a, stroke=OUTW))
    rr(c, -6, -26, 6, -16, 2, paint(sh(brass, -0.2), a))
    c.save(); c.translate(0, -24); c.rotate(math.degrees(ang))
    lev = skia.Path(); lev.moveTo(-8, -6); lev.lineTo(30, -6); lev.lineTo(60, -9); lev.quadTo(66, -9, 66, -3); lev.quadTo(66, 3, 60, 3); lev.lineTo(30, 4); lev.lineTo(-8, 4); lev.close()
    c.drawPath(lev, lin((0, -9), (0, 4), [sh(color, 0.3), sh(color, -0.15)], a)); c.drawPath(lev, paint(sh(color, -0.5), a, stroke=OUTW * 0.8))
    c.drawCircle(0, -1, 5, paint((120, 126, 140), a)); c.drawCircle(0, -1, 5, paint((60, 64, 76), a, stroke=1.4))
    c.restore()
    c.restore()

def gas_meter(c, x, y, s=1.0, a=1.0, t=0.0, spin=0.0, glow=0.0):
    """residential diaphragm meter; (x,y) centre; ±80 x ±90, swivels on top at -112"""
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    if glow > 0: c.drawPath(rpath(-104, -116, 104, 112, 32), paint(GAS, a * glow * 0.4, blur=30))
    contact(c, 0, 92, 84, 8, a, 0.35)
    for dx in (-50, 50):
        hexnut(c, dx, -100, 28, 22, (190, 196, 210), a)
        cyl_v(c, dx - 9, -92, dx + 9, -84, (150, 158, 176), a)
    base = (206, 212, 224)
    box(c, -80, -88, 80, 90, base, a, 16, k=0.14)
    emb = rpath(-68, -76, 68, 78, 12)
    c.drawPath(emb, paint(sh(base, -0.12), a * 0.6, stroke=3)); c.save(); c.translate(-1.5, -1.5); c.drawPath(emb, paint((255, 255, 255), a * 0.45, stroke=1.5)); c.restore()
    # index window
    win = rpath(-60, -64, 60, 4, 10)
    c.drawPath(win, paint((70, 76, 92), a)); 
    face = rpath(-55, -59, 55, -1, 7)
    c.drawPath(face, lin((0, -59), (0, -1), [(252, 252, 255), (226, 230, 238)], a))
    for k in range(4):
        cx = -40 + k * 26.7; cy = -32
        c.drawCircle(cx, cy, 11.5, paint((255, 255, 255), a)); c.drawCircle(cx, cy, 11.5, paint((70, 76, 92), a, stroke=1.6))
        for j in range(10):
            an = j * math.pi / 5
            c.drawLine(cx + 8.5 * math.cos(an), cy + 8.5 * math.sin(an), cx + 11 * math.cos(an), cy + 11 * math.sin(an), paint((70, 76, 92), a, stroke=1))
        an = t * spin * (2.2 / (k + 1)) * (1 if k % 2 == 0 else -1) - math.pi / 2 + k * 0.9
        c.drawLine(cx, cy, cx + 9 * math.cos(an), cy + 9 * math.sin(an), paint((220, 50, 50), a, stroke=2.2))
        c.drawCircle(cx, cy, 2, paint((40, 40, 50), a))
    c.save(); c.clipPath(win, skia.ClipOp.kIntersect, True)
    c.drawPath(poly_path([(-40, -64), (-10, -64), (-40, 4), (-70, 4)]), paint((255, 255, 255), a * 0.25)); c.restore()
    # name plate + bottom rib
    rr(c, -36, 18, 36, 40, 4, paint((176, 182, 196), a)); rr(c, -36, 18, 36, 40, 4, paint((120, 126, 140), a, stroke=1.4))
    for k in range(2): c.drawLine(-26, 25 + k * 8, 18 - k * 14, 25 + k * 8, paint((110, 116, 130), a, stroke=2))
    c.drawPath(rpath(-64, 56, 64, 68, 5), paint(sh(base, -0.25), a))
    c.restore()

def tank(c, x, gy, w, h, a=1.0, color=(200, 206, 220), lbl=None, lc=WHITE):
    """vertical storage tank with dome top"""
    if a <= 0.003: return
    contact(c, x, gy, w * 0.6, 7, a, 0.4)
    body = skia.Path(); r_ = w * 0.5
    body.moveTo(x - w / 2, gy - h + r_ * 0.6); body.cubicTo(x - w / 2, gy - h - r_ * 0.15, x + w / 2, gy - h - r_ * 0.15, x + w / 2, gy - h + r_ * 0.6)
    body.lineTo(x + w / 2, gy - 6); body.quadTo(x + w / 2, gy, x + w / 2 - 6, gy); body.lineTo(x - w / 2 + 6, gy); body.quadTo(x - w / 2, gy, x - w / 2, gy - 6); body.close()
    c.drawPath(body, lin((x - w / 2, 0), (x + w / 2, 0), [sh(color, -0.05), sh(color, 0.35), color, sh(color, -0.38)], a, [0, 0.25, 0.55, 1]))
    c.drawPath(body, paint(sh(color, -0.5), a, stroke=OUTW))
    for yy in (gy - h * 0.62, gy - h * 0.22): c.drawLine(x - w / 2, yy, x + w / 2, yy, paint(sh(color, -0.3), a, stroke=2.2))
    cyl_v(c, x - 6, gy - h - r_ * 0.1 - 10, x + 6, gy - h - r_ * 0.1 + 2, (150, 158, 176), a, 2)

def line_heater(c, x0, y0, x1, y1, a=1.0, t=0.0, on=0.0):
    """indirect-fired line heater (horizontal vessel + stack + firebox window)"""
    if a <= 0.003: return
    cx = (x0 + x1) / 2
    if on > 0: c.drawPath(rpath(x0 - 10, y0 - 10, x1 + 10, y1 + 10, 40), paint(HEAT, a * on * 0.35, blur=24))
    # stack
    cyl_v(c, x0 + 22, y0 - 74, x0 + 40, y0 + 6, (110, 116, 132), a, 2)
    rr(c, x0 + 16, y0 - 80, x0 + 46, y0 - 72, 2, paint((80, 86, 100), a))
    if on > 0: puff(c, x0 + 31, y0 - 84, t, a * on, 3, 50, 6, 18, 10, col_=(255, 200, 160), speed=0.7)
    # saddles
    for sx in (x0 + 34, x1 - 34): c.drawPath(poly_path([(sx - 18, y1 - 6), (sx + 18, y1 - 6), (sx + 24, y1 + 12), (sx - 24, y1 + 12)]), paint((70, 76, 90), a))
    cyl_h(c, x0, y0, x1, y1, (150, 92, 76), a, (y1 - y0) / 2)
    for bx in (x0 + 60, x1 - 60): c.drawLine(bx, y0 + 2, bx, y1 - 2, paint((110, 64, 54), a, stroke=3))
    # firebox window
    fx, fy = x1 - 30, (y0 + y1) / 2 + 6
    c.drawCircle(fx, fy, 17, paint((70, 76, 90), a)); c.drawCircle(fx, fy, 13, paint((30, 18, 18), a))
    if on > 0:
        c.save(); c.clipPath(opath(fx, fy, 13, 13), skia.ClipOp.kIntersect, True)
        fire_flame(c, fx, fy + 12, 0.32, a * on, t); c.restore()
        c.drawCircle(fx, fy, 22, paint((255, 150, 60), a * on * 0.5, blur=10))

def odorizer(c, x, py, a=1.0, t=0.0, odor=0.0, glow=0.0):
    """odorant tank on legs with injection line into the pipe at y=py"""
    if a <= 0.003: return
    if glow > 0: c.drawPath(rpath(x - 70, py - 140, x + 70, py - 10, 24), paint(ODOR, a * glow * 0.4, blur=24))
    for lx in (x - 30, x + 30): c.drawLine(lx, py - 44, lx, py - 14, paint((90, 98, 118), a, stroke=6))
    tank(c, x, py - 40, 92, 84, a, (164, 186, 112))
    rr(c, x - 22, py - 98, x + 22, py - 76, 4, paint((250, 250, 244), a))
    c.drawPath(poly_path([(x, py - 96), (x + 9, py - 80), (x - 9, py - 80)]), paint((236, 120, 40), a))
    # injection line + sight glass
    c.drawLine(x, py - 40, x, py - 13, paint((60, 70, 50), a, stroke=7)); c.drawLine(x, py - 40, x, py - 13, paint((150, 170, 110), a, stroke=4))
    rr(c, x + 6, py - 36, x + 16, py - 18, 3, paint((220, 240, 255), a * 0.7))
    if odor > 0:
        ph = (t * 1.6) % 1
        c.drawCircle(x + 11, py - 34 + ph * 14, 3, paint(ODOR, a * odor * (1 - ph * 0.5)))

# ------------------------------------------------------------------ houses
def house_icon(c, x, gy, s=1.0, a=1.0, lit=0.0):
    """detailed small house standing on ground y (centre x); body 300s x 190s, roof +130s"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    contact(c, 0, 0, 175, 12, a, 0.45)
    # chimney (behind roof)
    box(c, 70, -296, 104, -220, (150, 82, 70), a, 2, k=0.15)
    for k in range(4): c.drawLine(70, -282 + k * 16, 104, -282 + k * 16, paint((110, 58, 50), a * 0.7, stroke=1.6))
    rr(c, 64, -304, 110, -294, 2, paint((100, 104, 120), a))
    # walls (lap siding)
    wall = rpath(-150, -192, 150, 0, 2)
    c.drawPath(wall, lin((0, -192), (0, 0), [(64, 88, 140), (44, 62, 104)], a))
    c.save(); c.clipPath(wall, skia.ClipOp.kIntersect, True)
    for yy in range(-184, 0, 14): c.drawLine(-150, yy, 150, yy, paint((30, 44, 80), a * 0.55, stroke=1.6)); c.drawLine(-150, yy + 2, 150, yy + 2, paint((110, 140, 200), a * 0.18, stroke=1))
    c.drawRect(skia.Rect(60, -192, 150, 0), paint((0, 0, 0), a * 0.12))
    c.restore()
    c.drawPath(wall, paint((24, 34, 64), a, stroke=OUTW))
    c.drawRect(skia.Rect(-152, -12, 152, 0), paint((70, 76, 92), a))
    # roof
    roof = poly_path([(-182, -186), (0, -322), (182, -186)])
    c.drawPath(roof, lin((0, -322), (0, -186), [(98, 66, 96), (64, 42, 70)], a))
    c.save(); c.clipPath(roof, skia.ClipOp.kIntersect, True)
    for k in range(1, 8):
        yy = -322 + k * 18
        c.drawLine(-200, yy, 200, yy, paint((40, 24, 46), a * 0.5, stroke=1.6))
    c.drawPath(poly_path([(0, -322), (182, -186), (0, -186)]), paint((0, 0, 0), a * 0.15))
    c.restore()
    c.drawPath(polyline_path([(-188, -182), (0, -328), (188, -182)]), paint((210, 200, 220), a, stroke=6))
    c.drawPath(polyline_path([(-188, -182), (0, -328), (188, -182)]), paint((70, 50, 80), a, stroke=1.4))
    # windows
    for wx in (-90, 70):
        if lit > 0: c.drawRect(skia.Rect(wx - 16, -166, wx + 66, -64), paint(LIT, a * lit * 0.4, blur=18))
        glass = skia.Rect(wx, -150, wx + 50, -80)
        c.drawRect(glass, skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear([(0, -150), (0, -80)], [col(lerpc((40, 60, 100), (255, 228, 150), lit), a), col(lerpc((30, 46, 84), (255, 190, 100), lit), a)])))
        c.drawRect(glass, paint((236, 236, 244), a, stroke=4))
        c.drawLine(wx + 25, -150, wx + 25, -80, paint((236, 236, 244), a, stroke=2.5)); c.drawLine(wx, -115, wx + 50, -115, paint((236, 236, 244), a, stroke=2.5))
        rr(c, wx - 6, -82, wx + 56, -74, 2, paint((236, 236, 244), a))
    # door
    box(c, -27, -104, 27, -6, (140, 70, 64), a, 3, k=0.1)
    for (dy0, dy1) in ((-94, -62), (-54, -16)):
        c.drawPath(rpath(-19, dy0, -3, dy1, 2), paint((110, 52, 48), a)); c.drawPath(rpath(3, dy0, 19, dy1, 2), paint((110, 52, 48), a))
    c.drawCircle(18, -54, 3.5, paint((240, 210, 120), a))
    c.drawCircle(-38, -96, 5, paint(LIT, a * (0.5 + 0.5 * lit))); c.drawCircle(-38, -96, 10, paint(LIT, a * 0.35 * (0.4 + lit), blur=6))
    rr(c, -36, -8, 36, 0, 2, paint((150, 156, 170), a))
    c.restore()

# ------------------------------------------------------------------ small icons
def drop_icon(c, x, y, r, a=1.0, color=WATER):
    if a <= 0.003: return
    p = skia.Path(); p.moveTo(x, y - r * 1.6); p.cubicTo(x + r * 0.4, y - r * 0.9, x + r, y - r * 0.4, x + r, y + r * 0.1)
    p.cubicTo(x + r, y + r * 0.7, x + r * 0.5, y + r, x, y + r); p.cubicTo(x - r * 0.5, y + r, x - r, y + r * 0.7, x - r, y + r * 0.1)
    p.cubicTo(x - r, y - r * 0.4, x - r * 0.4, y - r * 0.9, x, y - r * 1.6); p.close()
    c.drawPath(p, rad(x - r * 0.3, y - r * 0.2, r * 1.6, [sh(color, 0.35), color, sh(color, -0.3)], a, [0, 0.5, 1]))
    c.drawOval(skia.Rect(x - r * 0.55, y - r * 0.35, x - r * 0.2, y + r * 0.25), paint((255, 255, 255), a * 0.55))

_TET = [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]
def methane(c, x, y, s=1.0, a=1.0, t=0.0):
    """shaded ball-and-stick CH4 (rotating tetrahedron)"""
    if a <= 0.003: return
    ay, ax = t * 0.7 + 0.5, 0.62
    pts = []
    for (px, py, pz) in _TET:
        n = math.sqrt(3); px, py, pz = px / n, py / n, pz / n
        x1 = px * math.cos(ay) + pz * math.sin(ay); z1 = -px * math.sin(ay) + pz * math.cos(ay)
        y2 = py * math.cos(ax) - z1 * math.sin(ax); z2 = py * math.sin(ax) + z1 * math.cos(ax)
        pts.append((x + 78 * s * x1, y + 78 * s * y2, z2))
    c.drawCircle(x, y, 120 * s, paint(GAS, a * 0.12, blur=40 * s))
    def H(px, py, pz):
        r = 23 * s * (1 + 0.12 * pz)
        c.drawCircle(px + 3 * s, py + 5 * s, r, paint((0, 0, 0), a * 0.3, blur=4 * s))
        c.drawCircle(px, py, r, rad(px - r * 0.35, py - r * 0.4, r * 1.5, [(255, 255, 255), (220, 228, 242), (150, 162, 190)], a, [0, 0.45, 1]))
        text(c, 'H', px, py + 9 * s, 26 * s, (40, 54, 90), a, 'bold')
    def bond(px, py, pz):
        c.drawLine(x, y, px, py, paint((60, 70, 96), a, stroke=13 * s))
        c.drawLine(x, y, px, py, paint((196, 206, 226), a, stroke=8 * s))
        c.save(); c.translate(-1.5 * s, -2 * s); c.drawLine(x, y, px, py, paint((255, 255, 255), a * 0.6, stroke=2.5 * s)); c.restore()
    back = [p for p in pts if p[2] < 0]; front = [p for p in pts if p[2] >= 0]
    for p in sorted(back, key=lambda q: q[2]): bond(*p); H(*p)
    rC = 38 * s
    c.drawCircle(x + 3 * s, y + 6 * s, rC, paint((0, 0, 0), a * 0.35, blur=5 * s))
    c.drawCircle(x, y, rC, rad(x - rC * 0.35, y - rC * 0.4, rC * 1.5, [(170, 186, 222), (92, 108, 146), (44, 54, 80)], a, [0, 0.5, 1]))
    c.drawCircle(x, y, rC, paint(GAS, a * 0.8, stroke=3 * s))
    text(c, 'C', x, y + 12 * s, 34 * s, WHITE, a, 'bold')
    for p in sorted(front, key=lambda q: q[2]): bond(*p); H(*p)

def tire(c, x, y, r, a=1.0):
    if a <= 0.003: return
    contact(c, x, y + r, r * 0.9, r * 0.12, a, 0.4)
    n = 22
    for k in range(n):  # tread blocks
        an = k * 2 * math.pi / n
        c.save(); c.translate(x + r * 0.97 * math.cos(an), y + r * 0.97 * math.sin(an)); c.rotate(math.degrees(an))
        rr(c, -r * 0.07, -r * 0.09, r * 0.07, r * 0.09, r * 0.03, paint((26, 28, 34), a)); c.restore()
    c.drawCircle(x, y, r * 0.95, rad(x - r * 0.3, y - r * 0.35, r * 1.3, [(70, 74, 86), (40, 42, 50), (24, 26, 32)], a, [0, 0.6, 1]))
    c.drawCircle(x, y, r * 0.8, paint((80, 84, 96), a * 0.6, stroke=r * 0.02))
    c.drawCircle(x, y, r * 0.6, rad(x - r * 0.2, y - r * 0.25, r * 0.8, [(236, 240, 248), (176, 182, 196), (120, 126, 140)], a, [0, 0.5, 1]))
    c.drawCircle(x, y, r * 0.6, paint((90, 96, 110), a, stroke=r * 0.025))
    for k in range(5):  # spokes as cut-outs
        an = k * 2 * math.pi / 5 - math.pi / 2
        p = skia.Path()
        a0, a1 = an + 0.32, an + 2 * math.pi / 5 - 0.32
        p.moveTo(x + r * 0.22 * math.cos(a0 + 0.1), y + r * 0.22 * math.sin(a0 + 0.1))
        p.lineTo(x + r * 0.5 * math.cos(a0), y + r * 0.5 * math.sin(a0))
        p.arcTo(skia.Rect(x - r * 0.5, y - r * 0.5, x + r * 0.5, y + r * 0.5), math.degrees(a0), math.degrees(a1 - a0), False)
        p.lineTo(x + r * 0.22 * math.cos(a1 - 0.1), y + r * 0.22 * math.sin(a1 - 0.1)); p.close()
        c.drawPath(p, paint((40, 44, 54), a))
    c.drawCircle(x, y, r * 0.17, rad(x - r * 0.05, y - r * 0.05, r * 0.2, [(220, 224, 234), (130, 136, 150)], a))
    for k in range(5):
        an = k * 2 * math.pi / 5
        c.drawCircle(x + r * 0.1 * math.cos(an), y + r * 0.1 * math.sin(an), r * 0.025, paint((80, 86, 100), a))
    c.drawArc(skia.Rect(x - r * 0.88, y - r * 0.88, x + r * 0.88, y + r * 0.88), 200, 60, False, paint((255, 255, 255), a * 0.18, stroke=r * 0.05))

def sun(c, x, y, r, a=1.0, t=0.0):
    if a <= 0.003: return
    c.drawCircle(x, y, r * 1.7, paint((255, 200, 80), a * 0.25, blur=r * 0.6))
    for k in range(12):
        an = k * math.pi / 6 + t * 0.3
        L0, L1 = (1.28, 1.62) if k % 2 == 0 else (1.28, 1.48)
        c.drawLine(x + r * L0 * math.cos(an), y + r * L0 * math.sin(an), x + r * L1 * math.cos(an), y + r * L1 * math.sin(an), paint((255, 196, 70), a, stroke=r * 0.13))
    c.drawCircle(x, y, r, rad(x - r * 0.3, y - r * 0.35, r * 1.4, [(255, 246, 180), (255, 210, 90), (250, 160, 50)], a, [0, 0.5, 1]))

def snowflake(c, x, y, r, a=1.0, t=0.0):
    if a <= 0.003: return
    c.drawCircle(x, y, r * 1.3, paint((150, 200, 255), a * 0.18, blur=r * 0.5))
    for wpass, cc in ((r * 0.2, (90, 140, 210)), (r * 0.12, (226, 242, 255))):
        p = paint(cc, a, stroke=wpass)
        for k in range(6):
            an = k * math.pi / 3 + t * 0.2
            c.drawLine(x, y, x + r * math.cos(an), y + r * math.sin(an), p)
            for sgn in (-1, 1):
                for f in (0.45, 0.7):
                    mx, my = x + r * f * math.cos(an), y + r * f * math.sin(an)
                    L = r * (0.3 if f < 0.6 else 0.22)
                    c.drawLine(mx, my, mx + L * math.cos(an + sgn * 0.8), my + L * math.sin(an + sgn * 0.8), p)

def phone(c, x, y, s=1.0, a=1.0, t=0.0):
    """smartphone showing a call"""
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    c.drawPath(rpath(-30, -55, 30, 59, 11), paint((0, 0, 0), a * 0.35, blur=5))
    box(c, -32, -58, 32, 58, (54, 60, 78), a, 12)
    scr = rpath(-26, -48, 26, 48, 6)
    c.drawPath(scr, lin((0, -48), (0, 48), [(70, 150, 240), (40, 90, 190)], a))
    c.drawCircle(0, 18, 13, paint((70, 210, 120), a))
    hs = skia.Path(); hs.moveTo(-6, 13); hs.quadTo(-6, 24, 6, 24); hs.lineTo(6, 20); hs.lineTo(2, 19); hs.lineTo(-1, 16); hs.lineTo(-2, 12); hs.close()
    c.drawPath(hs, paint((255, 255, 255), a))
    for k in range(3): c.drawArc(skia.Rect(-10 - k * 7, -24 - k * 7, 10 + k * 7, -4 + k * 7), 225, 90, False, paint((255, 255, 255), a * (0.8 - k * 0.2) * (0.6 + 0.4 * math.sin(t * 5 - k)), stroke=2.4))
    c.restore()

def light_switch(c, x, y, s=1.0, a=1.0):
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.scale(s, s)
    c.drawPath(rpath(-40, -60, 44, 70, 9), paint((0, 0, 0), a * 0.35, blur=6))
    box(c, -40, -64, 40, 64, (240, 236, 226), a, 9, k=0.06)
    for sy in (-48, 48):
        c.drawCircle(0, sy, 5, paint((190, 186, 176), a)); c.drawLine(-3, sy - 3, 3, sy + 3, paint((130, 126, 116), a, stroke=1.6))
    rr(c, -15, -32, 15, 32, 5, paint((200, 196, 184), a))
    tg = rpath(-11, -30, 11, 6, 5)
    c.drawPath(tg, lin((0, -30), (0, 6), [(255, 255, 250), (214, 210, 198)], a)); c.drawPath(tg, paint((150, 146, 134), a, stroke=1.6))
    c.restore()

def match(c, x, y, s=1.0, a=1.0, t=0.0):
    if a <= 0.003: return
    c.save(); c.translate(x, y); c.rotate(20)
    stick = rpath(-5 * s, -10 * s, 5 * s, 92 * s, 3 * s)
    c.drawPath(stick, lin((-5 * s, 0), (5 * s, 0), [(240, 214, 160), (196, 160, 104)], a)); c.drawPath(stick, paint((130, 100, 60), a, stroke=1.4))
    c.drawOval(skia.Rect(-9 * s, -26 * s, 9 * s, -2 * s), rad(-3 * s, -18 * s, 12 * s, [(250, 120, 90), (190, 40, 36), (110, 20, 20)], a, [0, 0.5, 1]))
    c.restore()
    fire_flame(c, x - 4 * s, y - 20 * s, 0.6 * s, a, t)

def door(c, x, gy, s=1.0, a=1.0, open_=0.0, t=0.0):
    """interior doorway (frame) with door swung open showing the outside at night"""
    if a <= 0.003: return
    c.save(); c.translate(x, gy); c.scale(s, s)
    op = rpath(-60, -220, 60, 0, 3)
    c.drawPath(op, lin((0, -220), (0, 0), [(30, 50, 100), (60, 90, 150)], a))
    c.save(); c.clipPath(op, skia.ClipOp.kIntersect, True)
    for (sx, sy) in ((-40, -196), (-6, -176), (30, -204), (14, -150), (-30, -140)): c.drawCircle(sx, sy, 1.8, paint((255, 255, 255), a * 0.8))
    c.drawCircle(30, -180, 12, paint((250, 246, 220), a * 0.9))
    c.drawRect(skia.Rect(-60, -50, 60, 0), lin((0, -50), (0, 0), [(70, 140, 90), (44, 96, 64)], a))
    c.restore()
    # frame / trim
    fr = (226, 220, 206)
    c.drawPath(polyline_path([(-66, 0), (-66, -226), (66, -226), (66, 0)]), paint(sh(fr, -0.5), a, stroke=14, join='miter'))
    c.drawPath(polyline_path([(-66, 0), (-66, -226), (66, -226), (66, 0)]), paint(fr, a, stroke=10, join='miter'))
    # door leaf (perspective)
    w = 120 * (1 - 0.78 * open_)
    leaf = poly_path([(-60, -220), (-60 + w, -220 - 14 * open_), (-60 + w, 14 * open_), (-60, 0)])
    dc = (150, 96, 64)
    c.drawPath(leaf, lin((-60, 0), (-60 + w, 0), [sh(dc, 0.1), sh(dc, -0.2)], a)); c.drawPath(leaf, paint(sh(dc, -0.5), a, stroke=OUTW))
    if w > 20:
        for (y0_, y1_) in ((-200, -120), (-100, -20)):
            pnl = poly_path([(-60 + w * 0.2, y0_ - 4 * open_), (-60 + w * 0.8, y0_ - 10 * open_), (-60 + w * 0.8, y1_ + 2 * open_), (-60 + w * 0.2, y1_ + 6 * open_)])
            c.drawPath(pnl, paint(sh(dc, -0.2), a)); c.drawPath(pnl, paint(sh(dc, -0.45), a, stroke=1.4))
        c.drawCircle(-60 + w * 0.82, -110, 4.5, paint((245, 215, 120), a))
    c.restore()

def badge_811(c, x, y, r, a=1.0):
    """generic 'call before you dig' badge (own design)"""
    if a <= 0.003: return
    c.drawCircle(x + 4, y + 8, r, paint((0, 0, 0), a * 0.4, blur=10))
    c.drawCircle(x, y, r, rad(x - r * 0.3, y - r * 0.4, r * 1.5, [(80, 160, 255), (36, 104, 214), (20, 64, 150)], a, [0, 0.55, 1]))
    c.drawCircle(x, y, r * 0.8, rad(x - r * 0.2, y - r * 0.3, r, [(255, 255, 255), (232, 238, 248)], a))
    c.drawCircle(x, y, r * 0.8, paint((20, 64, 150), a, stroke=r * 0.03))
    for k in range(24):
        an = k * math.pi / 12
        c.drawCircle(x + r * 0.9 * math.cos(an), y + r * 0.9 * math.sin(an), r * 0.022, paint((255, 255, 255), a * 0.75))
    # small shovel glyph
    sx, sy = x, y - r * 0.5
    c.drawLine(sx, sy - r * 0.16, sx, sy + r * 0.08, paint((120, 80, 50), a, stroke=r * 0.04))
    c.drawLine(sx - r * 0.06, sy - r * 0.17, sx + r * 0.06, sy - r * 0.17, paint((120, 80, 50), a, stroke=r * 0.04))
    bl = skia.Path(); bl.moveTo(sx - r * 0.07, sy + r * 0.06); bl.lineTo(sx + r * 0.07, sy + r * 0.06); bl.lineTo(sx + r * 0.07, sy + r * 0.15); bl.quadTo(sx, sy + r * 0.24, sx - r * 0.07, sy + r * 0.15); bl.close()
    c.drawPath(bl, paint((150, 158, 176), a))
    text(c, '811', x, y + r * 0.25, r * 0.66, (22, 56, 140), a, 'bold')

def flag(c, x, gy, h, a=1.0, t=0.0, color=PE_Y):
    if a <= 0.003: return
    c.drawLine(x, gy, x, gy - h, paint((70, 70, 80), a, stroke=4)); c.drawLine(x, gy, x, gy - h, paint((230, 230, 236), a, stroke=2.2))
    w = 36; fh = 24; wv = 3 * math.sin(t * 4 + x * 0.05)
    p = skia.Path(); p.moveTo(x, gy - h); p.quadTo(x + w * 0.5, gy - h - 4 + wv, x + w, gy - h + 2)
    p.lineTo(x + w, gy - h + fh + 2); p.quadTo(x + w * 0.5, gy - h + fh - 4 + wv, x, gy - h + fh); p.close()
    c.drawPath(p, lin((x, 0), (x + w, 0), [sh(color, 0.15), sh(color, -0.15)], a)); c.drawPath(p, paint(sh(color, -0.5), a, stroke=1.4))

def mini_station(c, x0, x1, gy, h, a=1.0, reg_s=0.4, glow=0.0, t=0.0):
    """small fenced regulator station (map/landscape scale)"""
    if a <= 0.003: return
    cx = (x0 + x1) / 2
    if glow > 0: c.drawPath(rpath(x0 - 14, gy - h - 14, x1 + 14, gy + 6, 12), paint(GAS, a * glow * 0.4, blur=18))
    contact(c, cx, gy, (x1 - x0) * 0.55, 5, a, 0.4)
    rr(c, x0 - 4, gy - 6, x1 + 4, gy + 2, 2, paint((120, 126, 140), a))
    py = gy - h * 0.42
    c.drawLine(x0 + 6, py, x1 - 6, py, paint((70, 78, 96), a, stroke=7)); c.drawLine(x0 + 6, py, x1 - 6, py, paint((176, 184, 200), a, stroke=4.5))
    for xx in (x0 + 10, x1 - 10): c.drawLine(xx, py, xx, gy - 4, paint((176, 184, 200), a, stroke=4.5))
    regulator(c, cx, py, reg_s, a)
    # chain-link fence
    fp = paint((170, 186, 216), a * 0.35, stroke=1)
    step = 7
    for k in range(int((x1 - x0) / step) + int(h / step) + 2):
        xa = x0 + k * step
        c.save(); c.clipRect(skia.Rect(x0, gy - h, x1, gy - 6))
        c.drawLine(xa, gy - h, xa - h, gy, fp); c.drawLine(xa - h, gy - h, xa, gy, fp); c.restore()
    for xx in (x0, cx, x1): c.drawLine(xx, gy - 4, xx, gy - h - 2, paint((150, 160, 186), a, stroke=2.5))
    c.drawLine(x0, gy - h, x1, gy - h, paint((150, 160, 186), a, stroke=2))
