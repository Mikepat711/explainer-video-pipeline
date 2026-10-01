"""Parametric motion-graphics scene templates.

Every template receives a shot spec (from shots.json, with all `at` timing
keys already resolved to scene-local seconds by the timeline stage), the scene
duration, and a Layout. Templates only draw inside the header/stage regions so
burned-in captions never collide with graphics.
"""
from __future__ import annotations

import math
import re

import cairo

from .canvas import Layout, Painter, clamp, in_out_cubic, lerp, mix, out_back, out_cubic, prog
from .icons import draw_icon

TEMPLATE_DOC = """
Templates and their fields (all `at` values accept seconds or "sN" = start of narration sentence N,
optionally "+0.5"/"-0.3"; "end-1.5" = 1.5 s before scene end):
- title: title, subtitle, kicker, icon
- bullets: heading, items[{text, icon, at}], icon (hero), hero_label
- diagram: heading, nodes[{id, label, sub, icon, x, y (0-1 in stage), at, color, kind: icon|box}],
           edges[{from, to, at, label, flow: bool, color, dashed: bool, bend: float}], portrait: transpose|same
- cycle: heading, nodes[{label, sub, icon, at}] (4 nodes: left, top, right, bottom), segment_colors[4],
         loop_at, highlight[{node, at}], heat[{node, dir: in|out, label, color, at}], zones[{label, color}] (2)
- cutaway: heading, layers[{label, sub, color, at}] (outer->inner), ray_at, ray_label, center_icon
- stat: heading, value, prefix, unit, label, at, icon, bars[{label, value, color, at}], note, note_at
- compare: heading, cards[{title, from_icon, to_icon, flow_label, color, items[text], at}] (2)
- steps: heading, steps[{title, text, icon, at}]
- orbit: heading, planes, sats_per_plane, orbits_at, sats_at, links_at, labels[{title, text, at}]
- signal: heading, packet[{text, at}], emit_at, receive_at, receive_label, delta_at, delta_label,
          formula, formula_at, result, result_at
- trilateration: heading, anchors[{label, x, y, px, py, at}], target{x, y, px, py}, fix_at, fix_label,
                 bands: bool, tighten_at, extra_at
- recap: heading, items[{text, icon, at}] or [text], title, end_at
Any template also accepts notes[{text, at}] (a callout pill at the bottom of the stage).
""".strip()


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class Scene:
    show_header = True

    def __init__(self, spec: dict, dur: float, layout: Layout, meta: dict):
        self.s, self.dur, self.L, self.meta = spec, dur, layout, meta

    # ---- helpers ------------------------------------------------------
    def at(self, obj, key="at", default=0.4):
        v = obj.get(key) if isinstance(obj, dict) else None
        return _num(v, default) if v is not None else default

    def seq(self, items, key="at", start=0.6, gap=None):
        """Resolved times for a list, spreading unspecified ones across the scene."""
        n = max(1, len(items))
        gap = gap or max(0.5, (self.dur - start - 1.5) / n)
        return [self.at(it, key, start + i * gap) if isinstance(it, dict) else start + i * gap
                for i, it in enumerate(items)]

    @property
    def stage(self):
        sx, sy, sw, sh = self.L.stage
        if self.s.get("notes"):
            sh -= 90
        return sx, sy, sw, sh

    # ---- frame --------------------------------------------------------
    def draw(self, p: Painter, t: float):
        enter = out_cubic(prog(t, 0.0, 0.5))
        # Non-final scenes keep running past `dur`; the assemble stage crossfades into the next scene.
        leave = 1 - in_out_cubic(prog(t, self.dur - 1.0, 1.0, paced=False)) if self.meta.get("last", True) else 1.0
        p.alpha = 1.0
        self.ambient(p, t)
        p.alpha = min(enter, leave)
        if self.show_header:
            self.header(p, t)
        c = p.ctx
        c.save()
        sx, sy, sw, sh = self.L.stage
        k = 1.0 + 0.022 * (t / max(self.dur, 0.1))
        cx, cy = sx + sw / 2, sy + sh / 2
        c.translate(cx, cy + 14 * (1 - enter))
        c.scale(k, k)
        c.translate(-cx, -cy)
        self.content(p, t)
        c.restore()
        self.notes(p, t)
        p.alpha = 1.0
        self.progress(p, t)

    def ambient(self, p: Painter, t: float):
        L = self.L
        gt = self.meta.get("global_start", 0) + t
        for i, (fx, fy, col) in enumerate(((0.18, 0.28, "accent"), (0.86, 0.72, "violet"))):
            x = L.w * fx + math.sin(gt * 0.13 + i * 2) * L.w * 0.04
            y = L.h * fy + math.cos(gt * 0.11 + i) * L.h * 0.04
            p.glow(x, y, max(L.w, L.h) * 0.42, col, 0.10)

    def header(self, p: Painter, t: float):
        hx, hy, hw, hh = self.L.header
        e = out_cubic(prog(t, 0.05, 0.6))
        off = 36 * (1 - e)
        kicker = f"{self.meta.get('index', 1):02d}   {self.meta.get('title', '').upper()}"
        p.rrect(hx + off, hy + 6, 34, 6, 3, fill="accent", fill_a=e)
        p.text(kicker, hx + 50 + off, hy - 4, 22, "muted", e, "semibold", tracking=0.14, tag="kicker")
        size = 64 if not self.L.portrait else 76
        lines = 1 if not self.L.portrait else 3
        e2 = out_cubic(prog(t, 0.15, 0.6))
        p.text_block(self.s.get("heading", ""), hx + 36 * (1 - e2), hy + 38, hw, hh - 40, size, "text", e2,
                     "bold", max_lines=lines, lh=1.1, tag="heading")

    def progress(self, p: Painter, t: float):
        if not self.meta.get("progress_bar", True):
            return
        total = self.meta.get("total_duration", 1)
        f = clamp((self.meta.get("global_start", 0) + t) / total)
        p.ctx.rectangle(0, 0, self.L.w, 5)
        p.rgba("stroke", 0.5)
        p.ctx.fill()
        p.ctx.rectangle(0, 0, self.L.w * f, 5)
        p.rgba("accent", 0.9)
        p.ctx.fill()

    def notes(self, p: Painter, t: float):
        notes = self.s.get("notes") or []
        if not notes:
            return
        times = self.seq(notes, start=1.0)
        cur = None
        for n, tt in zip(notes, times):
            if t >= tt:
                cur = (n, tt)
        if not cur:
            return
        n, tt = cur
        e = out_back(prog(t, tt, 0.45))
        sx, sy, sw, sh = self.L.stage
        text = n["text"] if isinstance(n, dict) else str(n)
        size = 34 if not self.L.portrait else 32
        maxw = sw * 0.9
        s, lines = p.fit(text, maxw - 60, size * 1.3, size, 22, "semibold", max_lines=1)
        w = p.text_w(lines[0], s, "semibold") + 64
        cx, cy = sx + sw / 2, sy + sh - 40 + 20 * (1 - e)
        p.rrect(cx - w / 2, cy - 32, w, 64, 32, fill="panel_hi", fill_a=0.96 * e, stroke="accent",
                stroke_a=0.8 * e, lw=2)
        p.text(lines[0], cx, cy - s * 0.52, s, "text", e, "semibold", "center", tag="note")

    def content(self, p: Painter, t: float):
        pass

    # ---- shared widgets ----------------------------------------------
    def icon_badge(self, p, name, cx, cy, r, color="accent", a=1.0, t=0.0, active=0.0):
        if active > 0:
            p.glow(cx, cy, r * 2.2, color, 0.35 * active * a)
        p.circle(cx, cy, r, fill="panel", fill_a=a, stroke=color, stroke_a=a * (0.55 + 0.45 * active), lw=3)
        draw_icon(p, name, cx, cy, r * 1.05, color, a, t)


# ---------------------------------------------------------------------------
class Title(Scene):
    show_header = False

    def content(self, p, t):
        L = self.L
        cx = L.w / 2
        maxw = L.w * (0.8 if not L.portrait else 0.86)
        tsize = 112 if not L.portrait else 104
        s, lines = p.fit(self.s.get("title", ""), maxw, tsize * 1.1 * 3, tsize, 56, "bold", 1.08, 3)
        title_h = len(lines) * s * 1.08
        icon_r = 86
        stack = icon_r * 2 + 60 + 32 + 26 + title_h + 40 + 50
        top = (L.caption_top - stack) / 2 + (20 if not L.portrait else 60)
        icy = top + icon_r
        e_icon = out_back(prog(t, 0.1, 0.8))
        for i, rr in enumerate((icon_r + 26, icon_r + 52, icon_r + 80)):
            pr = in_out_cubic(prog(t, 0.2 + i * 0.12, 1.1))
            c = p.ctx
            c.new_path()
            a0 = -math.pi / 2 + t * (0.3 - i * 0.15)
            c.arc(cx, icy, rr, a0, a0 + 2 * math.pi * pr)
            p.rgba("accent", 0.5 - i * 0.14)
            c.set_line_width(2.5)
            if i == 1:
                c.set_dash([6, 10])
            c.stroke()
            c.set_dash([])
            ang = t * (0.9 - i * 0.25) + i * 2.1
            p.circle(cx + rr * math.cos(ang), icy + rr * math.sin(ang), 6 - i, fill="accent", fill_a=pr)
        p.glow(cx, icy, icon_r * 2.4, "accent", 0.35 * e_icon)
        c = p.ctx
        c.save()
        c.translate(cx, icy)
        c.scale(max(0.01, e_icon), max(0.01, e_icon))
        c.translate(-cx, -icy)
        self.icon_badge(p, self.s.get("icon", "spark"), cx, icy, icon_r, "accent", 1.0, t, 1.0)
        c.restore()
        y = icy + icon_r + 60
        ek = out_cubic(prog(t, 0.45, 0.6))
        p.text(self.s.get("kicker", "THEORY EXPLAINER").upper(), cx, y + 10 * (1 - ek), 26, "accent", ek,
               "semibold", "center", tracking=0.28, tag="kicker")
        y += 32 + 26
        for i, ln in enumerate(lines):
            e = out_cubic(prog(t, 0.6 + i * 0.12, 0.7))
            p.text(ln, cx, y + i * s * 1.08 + 40 * (1 - e), s, "text", e, "bold", "center", tag="title")
        y += title_h + 26
        eb = in_out_cubic(prog(t, 1.0, 0.7))
        p.rrect(cx - 70 * eb, y, 140 * eb, 6, 3, fill="accent", fill_a=eb)
        y += 30
        es = out_cubic(prog(t, 1.2, 0.7))
        p.text_block(self.s.get("subtitle", ""), cx - maxw / 2, y + 16 * (1 - es), maxw, 110, 42, "muted", es,
                     "medium", "center", max_lines=2, tag="subtitle")


# ---------------------------------------------------------------------------
class Bullets(Scene):
    def content(self, p, t):
        sx, sy, sw, sh = self.stage
        items = [it if isinstance(it, dict) else {"text": str(it)} for it in self.s.get("items", [])]
        times = self.seq(items)
        if self.L.portrait:
            hero = (sx, sy, sw, sh * 0.36)
            lx, ly, lw, lh = sx, sy + sh * 0.42, sw, sh * 0.58
        else:
            hero = (sx + sw * 0.62, sy, sw * 0.38, sh)
            lx, ly, lw, lh = sx, sy, sw * 0.57, sh
        self.hero(p, t, *hero)
        n = max(1, len(items))
        row = min(150 if not self.L.portrait else 130, lh / n)
        oy = ly + (lh - row * n) / 2
        active = max([i for i, tt in enumerate(times) if t >= tt], default=-1)
        for i, (it, tt) in enumerate(zip(items, times)):
            e = out_cubic(prog(t, tt, 0.55))
            if e <= 0:
                continue
            y = oy + i * row
            r = min(38, row * 0.3)
            dim = 1.0 if i == active else 0.62
            x = lx + 30 * (1 - e)
            col = it.get("color", "accent")
            self.icon_badge(p, it.get("icon", "check"), x + r, y + row / 2, r, col, e, t, 1.0 if i == active else 0)
            tx = x + r * 2 + 28
            p.text_block(it.get("text", ""), tx, y + 8, lx + lw - tx, row - 16, 44, "text", e * dim, "semibold",
                         max_lines=2, valign="middle", min_size=26, tag=f"item{i}")

    def hero(self, p, t, x, y, w, h):
        e = out_back(prog(t, 0.3, 0.8))
        if e <= 0:
            return
        cx, cy = x + w / 2, y + h / 2
        r = min(w, h) * 0.34
        p.glow(cx, cy, r * 2.2, "accent", 0.25 * e)
        p.circle(cx, cy, r * e, fill="panel", fill_a=0.9, stroke="stroke", lw=2)
        c = p.ctx
        c.new_path()
        c.arc(cx, cy, r * 1.18, t * 0.4, t * 0.4 + math.pi * 1.4)
        p.rgba("accent", 0.7 * e)
        c.set_line_width(3)
        c.set_dash([2, 14])
        c.stroke()
        c.set_dash([])
        draw_icon(p, self.s.get("icon", "spark"), cx, cy, r * 1.15 * e, "accent", e, t)
        if self.s.get("hero_label"):
            p.text(self.s["hero_label"], cx, cy + r * 1.35, 30, "muted", e, "semibold", "center", tag="hero")


# ---------------------------------------------------------------------------
class Diagram(Scene):
    def pos(self, n):
        sx, sy, sw, sh = self.stage
        x, y = _num(n.get("x"), 0.5), _num(n.get("y"), 0.5)
        if self.L.portrait:
            if "px" in n:
                x, y = _num(n["px"]), _num(n.get("py"), y)
            elif self.s.get("portrait", "transpose") == "transpose":
                x, y = y, x
        pad = 90
        return sx + pad + x * (sw - 2 * pad), sy + pad * 0.6 + y * (sh - pad * 1.9)

    def content(self, p, t):
        nodes = self.s.get("nodes", [])
        ntimes = self.seq(nodes, start=0.5)
        by_id = {n.get("id", str(i)): (n, tt) for i, (n, tt) in enumerate(zip(nodes, ntimes))}
        for i, ed in enumerate(self.s.get("edges", [])):
            a, b = by_id.get(ed.get("from")), by_id.get(ed.get("to"))
            if not a or not b:
                continue
            start = self.at(ed, "at", max(a[1], b[1]) + 0.3)
            self.edge(p, t, a[0], b[0], ed, start)
        for i, n in enumerate(nodes):
            self.node(p, t, n, ntimes[i], i)

    def radius(self, n):
        return _num(n.get("r"), 62 if not self.L.portrait else 56)

    def edge(self, p, t, na, nb, ed, start):
        pr = in_out_cubic(prog(t, start, 0.8))
        if pr <= 0:
            return
        (x1, y1), (x2, y2) = self.pos(na), self.pos(nb)
        ra, rb = self.radius(na) + 14, self.radius(nb) + 14
        d = math.dist((x1, y1), (x2, y2)) or 1
        bend = _num(ed.get("bend"), 0)
        mx_, my_ = (x1 + x2) / 2 - (y2 - y1) / d * bend * d, (y1 + y2) / 2 + (x2 - x1) / d * bend * d
        pts = [((1 - u) ** 2 * x1 + 2 * (1 - u) * u * mx_ + u * u * x2,
                (1 - u) ** 2 * y1 + 2 * (1 - u) * u * my_ + u * u * y2) for u in [i / 40 for i in range(41)]]
        pts = [q for q in pts if math.dist(q, (x1, y1)) >= ra and math.dist(q, (x2, y2)) >= rb]
        if len(pts) < 2:
            return
        col = ed.get("color", "muted")
        dash = [10, 10] if ed.get("dashed") else None
        end = p.polyline(pts, col, 0.9, 4, pr, dash)
        if end and pr > 0.05:
            k = max(1, int(len(pts) * pr) - 1)
            ang = math.atan2(end[1] - pts[k - 1][1], end[0] - pts[k - 1][0])
            p.arrow_head(end[0], end[1], ang, col, 0.95, 20)
        if ed.get("flow") and pr >= 1:
            n = max(2, int(d / 90))
            for j in range(n):
                u = ((t - start) * 0.45 + j / n) % 1.0
                idx = u * (len(pts) - 1)
                i0 = int(idx)
                f = idx - i0
                q0, q1 = pts[i0], pts[min(i0 + 1, len(pts) - 1)]
                px_, py_ = lerp(q0[0], q1[0], f), lerp(q0[1], q1[1], f)
                p.glow(px_, py_, 18, col, 0.6)
                p.circle(px_, py_, 5, fill=col)
        if ed.get("label"):
            el = out_cubic(prog(t, start + 0.5, 0.5))
            q = pts[len(pts) // 2]
            p.pill(ed["label"], q[0], q[1], 24, "panel_hi", el, "text", "semibold", tag="edge")

    def node(self, p, t, n, tt, i):
        e = out_back(prog(t, tt, 0.6))
        if e <= 0:
            return
        x, y = self.pos(n)
        r = self.radius(n) * e
        col = n.get("color", "accent")
        pulse = 0.5 + 0.5 * math.sin((t - tt) * 3) if t - tt < 2.0 else 0
        if n.get("kind") == "box":
            w, h = r * 3.4, r * 1.6
            p.rrect(x - w / 2, y - h / 2, w, h, 18, fill="panel", stroke=col, lw=3)
            p.text_block(n.get("label", ""), x - w / 2 + 12, y - h / 2 + 6, w - 24, h - 12, 32, "text", e,
                         "semibold", "center", max_lines=2, valign="middle", tag=f"node{i}")
            return
        self.icon_badge(p, n.get("icon", "spark"), x, y, r, col, 1.0, t, pulse * (1 - prog(t, tt + 1.5, 0.5)))
        el = out_cubic(prog(t, tt + 0.2, 0.5))
        lw = 300 if not self.L.portrait else 260
        if n.get("label"):
            s1, l1 = p.fit(n["label"], lw, 80, 32, 22, "semibold", max_lines=2)
            h1 = len(l1) * s1 * 1.18
            wid = max(p.text_w(ln, s1, "semibold") for ln in l1)
            h2, l2, s2 = 0, [], 24
            if n.get("sub"):
                s2, l2 = p.fit(n["sub"], lw, 60, 24, 18, "medium", max_lines=2)
                h2 = len(l2) * s2 * 1.18 + 4
                wid = max([wid] + [p.text_w(ln, s2, "medium") for ln in l2])
            top = y + r + 12
            p.rrect(x - wid / 2 - 14, top - 4, wid + 28, h1 + h2 + 10, 12, fill="bg0", fill_a=0.72 * el)
            p.text_block(n["label"], x - lw / 2, top, lw, 80, 32, "text", el, "semibold", "center",
                         max_lines=2, min_size=22, tag=f"node{i}")
            if l2:
                p.text_block(n["sub"], x - lw / 2, top + h1 + 4, lw, 60, 24, "muted", el, "medium", "center",
                             max_lines=2, min_size=18, tag=f"sub{i}")


# ---------------------------------------------------------------------------
class Cycle(Scene):
    def geometry(self):
        sx, sy, sw, sh = self.stage
        if self.L.portrait:
            w, h = sw * 0.58, sh * 0.74
        else:
            w, h = sw * 0.46, sh * 0.72
        cx, cy = sx + sw / 2, sy + sh / 2 + (0 if not self.L.portrait else 10)
        return cx, cy, w, h

    def loop_points(self):
        cx, cy, w, h = self.geometry()
        r = min(w, h) * 0.18
        x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        pts = []

        def arc(ax, ay, a0, a1):
            for k in range(13):
                a = a0 + (a1 - a0) * k / 12
                pts.append((ax + r * math.cos(a), ay + r * math.sin(a)))

        pts.append((x0, cy))
        arc(x0 + r, y0 + r, math.pi, 1.5 * math.pi)
        pts.append((cx, y0))
        arc(x1 - r, y0 + r, 1.5 * math.pi, 2 * math.pi)
        pts.append((x1, cy))
        arc(x1 - r, y1 - r, 0, 0.5 * math.pi)
        pts.append((cx, y1))
        arc(x0 + r, y1 - r, 0.5 * math.pi, math.pi)
        pts.append((x0, cy))
        anchors = [0, 14, 28, 42]
        return pts, anchors

    def content(self, p, t):
        pts, anchors = self.loop_points()
        nodes = self.s.get("nodes", [])[:4]
        ntimes = self.seq(nodes, start=0.6)
        cols = self.s.get("segment_colors", ["cool", "hot", "warm", "cold"])
        self.zones(p, t)
        loop_at = self.at(self.s, "loop_at", 0.3)
        pr = in_out_cubic(prog(t, loop_at, 1.4))
        segs = [pts[anchors[i]:(anchors[i + 1] if i < 3 else len(pts) - 1) + 1] for i in range(4)]
        for i, seg in enumerate(segs):
            sp = clamp(pr * 4 - i)
            p.polyline(seg, cols[i % len(cols)], 0.22, 22, sp)
            p.polyline(seg, cols[i % len(cols)], 0.95, 5, sp)
        if pr >= 1:
            self.particles(p, t, segs, cols, loop_at + 1.4)
        hl = self.s.get("highlight", [])
        hl_times = self.seq(hl, start=1.0)
        active = None
        for h, tt in zip(hl, hl_times):
            if t >= tt:
                active = (int(h.get("node", 0)), tt)
        for i, (n, tt) in enumerate(zip(nodes, ntimes)):
            a = pts[anchors[i]]
            act = 0.0
            if active and active[0] == i:
                act = 0.75 + 0.25 * math.sin((t - active[1]) * 4)
            self.card(p, t, n, a, tt, i, act)
        for i, h in enumerate(self.s.get("heat", [])):
            self.heat_arrow(p, t, h, pts, anchors)

    def particles(self, p, t, segs, cols, t0):
        allpts = [q for seg in segs for q in seg]
        seglen = [len(s) for s in segs]
        n = 28
        total = len(allpts)
        for j in range(n):
            u = ((t - t0) * 0.07 + j / n) % 1.0
            idx = int(u * (total - 1))
            acc, si = 0, 0
            for k, L_ in enumerate(seglen):
                if idx < acc + L_:
                    si = k
                    break
                acc += L_
            q = allpts[idx]
            fade = clamp((t - t0) / 0.8)
            p.circle(q[0], q[1], 6, fill="white", fill_a=0.9 * fade)
            p.glow(q[0], q[1], 20, cols[si % len(cols)], 0.7 * fade)

    def card(self, p, t, n, a, tt, i, act):
        e = out_back(prog(t, tt, 0.6))
        if e <= 0:
            return
        w = (340 if not self.L.portrait else 300) * e
        h = (118 if not self.L.portrait else 112) * e
        x, y = a[0] - w / 2, a[1] - h / 2
        col = n.get("color", "accent")
        if act:
            p.glow(a[0], a[1], w * 0.9, col, 0.4 * act)
        p.rrect(x, y, w, h, 20, fill="panel", fill_a=0.97, stroke=col, stroke_a=0.5 + 0.5 * act, lw=3)
        ir = h * 0.3
        self.icon_badge(p, n.get("icon", "spark"), x + ir + 16, a[1], ir, col, e, t, act)
        tx = x + ir * 2 + 30
        tw = x + w - 14 - tx
        if n.get("sub"):
            p.text_block(n.get("label", ""), tx, y + 12, tw, h * 0.44, 30, "text", e, "bold", max_lines=1,
                         min_size=18, valign="bottom", tag=f"node{i}")
            p.text_block(n["sub"], tx, y + h * 0.58, tw, h * 0.36, 22, "muted", e, "medium", max_lines=1,
                         min_size=16, tag=f"sub{i}")
        else:
            p.text_block(n.get("label", ""), tx, y + 10, tw, h - 20, 30, "text", e, "bold", max_lines=2,
                         valign="middle", min_size=20, tag=f"node{i}")

    def zones(self, p, t):
        zones = self.s.get("zones") or []
        if len(zones) != 2:
            return
        sx, sy, sw, sh = self.stage
        e = out_cubic(prog(t, 0.2, 0.8))
        cx = sx + sw / 2
        for k, z in enumerate(zones):
            x = sx if k == 0 else cx
            p.rrect(x + 6, sy, sw / 2 - 12, sh, 24, fill=z.get("color", "cold"), fill_a=0.06 * e)
            lx = x + 30 if k == 0 else sx + sw - 30
            p.text(z.get("label", "").upper(), lx, sy + 18, 22, z.get("color", "muted"), 0.9 * e, "semibold",
                   "left" if k == 0 else "right", tracking=0.18, tag=f"zone{k}")
        p.line(cx, sy + 10, cx, sy + sh - 10, "muted", 0.35 * e, 2, [4, 10])

    def heat_arrow(self, p, t, h, pts, anchors):
        tt = self.at(h, "at", 2.0)
        e = out_cubic(prog(t, tt, 0.7))
        if e <= 0:
            return
        i = int(h.get("node", 0))
        ax, ay = pts[anchors[i]]
        col = h.get("color", "hot")
        cx, cy, w, hh = self.geometry()
        sx, sy, sw, sh = self.stage
        if self.L.portrait or i in (1, 3):
            dx, dy = 0, (-1 if ay < cy else 1)
            if self.L.portrait and i in (0, 2):
                dx, dy = 0, -1
                ay -= 60
            dist0, dist1 = 70, 170
        else:
            dx, dy = (-1 if ax < cx else 1), 0
            dist0 = 200
            dist1 = min(330, abs((sx if ax < cx else sx + sw) - ax) - 30)
        inward = h.get("dir", "in") == "in"
        for k in (-1, 0, 1):
            ox, oy = -dy * k * 34, dx * k * 34
            p0 = (ax + dx * dist1 + ox, ay + dy * dist1 + oy)
            p1 = (ax + dx * dist0 + ox, ay + dy * dist0 + oy)
            if not inward:
                p0, p1 = p1, p0
            wig = []
            for j in range(21):
                u = j / 20
                bx, by = lerp(p0[0], p1[0], u), lerp(p0[1], p1[1], u)
                amp = 7 * math.sin(u * math.pi * 4 - t * 6)
                wig.append((bx - dy * amp, by + dx * amp))
            end = p.polyline(wig, col, 0.9 * e, 4, e)
            if end and e > 0.9:
                p.arrow_head(end[0], end[1], math.atan2(p1[1] - p0[1], p1[0] - p0[0]), col, e, 18)
        if h.get("label"):
            lx, ly = ax + dx * (dist0 + dist1) / 2, ay + dy * (dist0 + dist1) / 2
            ly += (-80 if dy == 0 else 0)
            if dy != 0:
                lx += 150 if not self.L.portrait else 0
                ly += 0 if not self.L.portrait else dy * 30
            p.pill(h["label"], lx, ly, 24, col, e, "bg0", tag="heat")


# ---------------------------------------------------------------------------
class Cutaway(Scene):
    def content(self, p, t):
        sx, sy, sw, sh = self.stage
        layers = self.s.get("layers", [])
        times = self.seq(layers, start=0.6)
        n = max(1, len(layers))
        if self.L.portrait:
            R = min(sw * 0.34, sh * 0.24)
            cx, cy = sx + sw / 2, sy + R + 10
        else:
            R = min(sw * 0.24, sh * 0.47)
            cx, cy = sx + sw * 0.28, sy + sh / 2
        radii = [R * (1 - i / (n + 0.4)) for i in range(n)]
        wedge0, wedge1 = -math.pi / 2, 0.0
        c = p.ctx
        for i, (ly, tt) in enumerate(zip(layers, times)):
            e = out_cubic(prog(t, tt * 0.35, 0.8))
            col = ly.get("color", "accent")
            r = radii[i] * (0.85 + 0.15 * e)
            p.circle(cx, cy, r, fill="panel" if i % 2 == 0 else "panel_hi", fill_a=e, stroke=col,
                     stroke_a=0.35 * e, lw=2)
        cut = in_out_cubic(prog(t, 0.5, 1.0))
        for i, ly in enumerate(layers):
            col = ly.get("color", "accent")
            r0 = radii[i]
            r1 = radii[i + 1] if i + 1 < n else 0
            c.new_path()
            c.arc(cx, cy, r0, wedge0, wedge0 + (wedge1 - wedge0) * cut)
            c.arc_negative(cx, cy, r1, wedge0 + (wedge1 - wedge0) * cut, wedge0)
            c.close_path()
            p.rgba(col, 0.55 + 0.35 * (i == n - 1))
            c.fill()
        if cut > 0:
            for ang in (wedge0, wedge0 + (wedge1 - wedge0) * cut):
                p.line(cx, cy, cx + R * math.cos(ang), cy + R * math.sin(ang), "text", 0.6 * cut, 2)
        if self.s.get("center_icon"):
            draw_icon(p, self.s["center_icon"], cx, cy, radii[-1] * 0.9, "text", 0.95 * cut, t)
        for i, (ly, tt) in enumerate(zip(layers, times)):
            self.callout(p, t, i, ly, tt, cx, cy, radii, R, n)
        self.ray(p, t, cx, cy, radii, R)

    def callout(self, p, t, i, ly, tt, cx, cy, radii, R, n):
        e = out_cubic(prog(t, tt, 0.6))
        if e <= 0:
            return
        sx, sy, sw, sh = self.stage
        col = ly.get("color", "accent")
        r_mid = (radii[i] + (radii[i + 1] if i + 1 < n else 0)) / 2
        ang = -math.pi / 2 + (i + 0.5) / n * (math.pi / 2)
        ax, ay = cx + r_mid * math.cos(ang), cy + r_mid * math.sin(ang)
        if self.L.portrait:
            top = cy + R + 50
            rowh = (sy + sh - top) / n
            lx, ly_ = sx + 70, top + i * rowh
            p.circle(sx + 26, ly_ + 22, 12 * e, fill=col)
            s, h, _ = p.text_block(ly.get("label", ""), lx, ly_, sw - 80, 46, 34, "text", e, "bold",
                                   max_lines=1, min_size=24, tag=f"layer{i}")
            if ly.get("sub"):
                p.text_block(ly["sub"], lx, ly_ + h + 4, sw - 80, rowh - h - 10, 26, "muted", e, "medium",
                             max_lines=1, min_size=18, tag=f"lsub{i}")
            return
        colx = cx + R + 110
        rowh = sh / n
        ly_ = sy + i * rowh + rowh * 0.5
        p.circle(ax, ay, 7 * e, fill="text", fill_a=e)
        elbow = (cx + R + 50, ly_)
        p.polyline([(ax, ay), (elbow[0] - 30, ly_ if abs(ly_ - ay) < 4 else ay + (ly_ - ay) * 0.9), elbow,
                    (colx - 14, ly_)], "text", 0.6 * e, 2, e)
        wcol = sx + sw - colx
        p.rrect(colx, ly_ - 32, 8, 64, 4, fill=col, fill_a=e)
        s, h, _ = p.text_block(ly.get("label", ""), colx + 26, ly_ - 38, wcol - 30, 46, 36, "text", e, "bold",
                               max_lines=1, min_size=24, tag=f"layer{i}")
        if ly.get("sub"):
            p.text_block(ly["sub"], colx + 26, ly_ + 8, wcol - 30, rowh / 2 - 6, 26, "muted", e, "medium",
                         max_lines=2, min_size=18, tag=f"lsub{i}")

    def ray(self, p, t, cx, cy, radii, R):
        tt = self.s.get("ray_at")
        if tt is None:
            return
        tt = _num(tt)
        pr = in_out_cubic(prog(t, tt, 1.6))
        if pr <= 0:
            return
        sx, sy, sw, sh = self.stage
        ang = -math.pi / 2 + 0.2
        rs = min(R * 1.35, (cy - sy - 10) / abs(math.sin(ang)))
        pts = [(cx + rs * math.cos(ang), cy + rs * math.sin(ang))]
        a = ang
        for i, r in enumerate(radii[:-1]):
            a += 0.07 * (1 if i % 2 == 0 else -0.6)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        pts.append((cx + radii[-1] * math.cos(a + 0.05), cy + radii[-1] * math.sin(a + 0.05)))
        end = p.polyline(pts, "warn", 0.95, 4, pr, [14, 8])
        if end:
            p.glow(end[0], end[1], 28, "warn", 0.8)
            p.circle(end[0], end[1], 7, fill="warn")
        if self.s.get("ray_label") and pr > 0.3:
            el = out_cubic(prog(t, tt + 0.5, 0.5))
            lw_ = p.text_w(self.s["ray_label"], 24, "semibold") + 29
            p.pill(self.s["ray_label"], pts[0][0] - lw_ / 2 - 18, pts[0][1] + 14, 24, "warn", el, "bg0", tag="ray")


# ---------------------------------------------------------------------------
class Stat(Scene):
    def content(self, p, t):
        sx, sy, sw, sh = self.stage
        bars = self.s.get("bars") or []
        tt = self.at(self.s, "at", 0.6)
        e = out_cubic(prog(t, tt, 0.7))
        count = in_out_cubic(prog(t, tt, 1.3))
        raw = str(self.s.get("value", "0"))
        m = re.match(r"^([\d,]*\.?\d+)", raw)
        if m:
            target = float(m.group(1).replace(",", ""))
            dec = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
            val = target * count
            shown = f"{val:,.{dec}f}" if "," in m.group(1) else f"{val:.{dec}f}"
            shown += raw[m.end():]
        else:
            shown = raw
        shown = f"{self.s.get('prefix', '')}{shown}"
        unit = self.s.get("unit", "")
        if self.L.portrait:
            box = (sx, sy, sw, sh * (0.5 if bars else 0.8))
            bbox = (sx, sy + sh * 0.56, sw, sh * 0.44)
        else:
            box = (sx, sy, sw * (0.5 if bars else 0.62), sh)
            bbox = (sx + sw * 0.56, sy + sh * 0.1, sw * 0.44, sh * 0.8)
        bx, by, bw, bh = box
        size = 210 if not self.L.portrait else 190
        us = size * 0.34
        while size > 80 and p.text_w(shown, size, "bold") + p.text_w(unit, us, "semibold") + 24 > bw:
            size -= 8
            us = size * 0.34
        vw = p.text_w(shown, size, "bold")
        total_w = vw + (p.text_w(unit, us, "semibold") + 24 if unit else 0)
        x0 = bx + (bw - total_w) / 2 if (self.L.portrait or not bars) else bx
        cy = by + bh * 0.42
        p.glow(x0 + vw / 2, cy, size * 1.4, "accent", 0.22 * e)
        p.text(shown, x0, cy - size * 0.55 + 30 * (1 - e), size, "text", e, "bold", tag="value")
        if unit:
            p.text(unit, x0 + vw + 24, cy - size * 0.55 + size * 0.8 - us * 0.8 + 30 * (1 - e), us, "accent",
                   e, "semibold", tag="unit")
        el = out_cubic(prog(t, tt + 0.5, 0.6))
        align = "center" if (self.L.portrait or not bars) else "left"
        p.text_block(self.s.get("label", ""), bx, cy + size * 0.5, bw, bh * 0.4, 40, "muted", el, "medium",
                     align, max_lines=3, min_size=24, tag="label")
        if bars:
            self.bars(p, t, bars, *bbox)
        elif self.s.get("icon") and not self.L.portrait:
            ix, iy = sx + sw * 0.82, sy + sh / 2
            ei = out_back(prog(t, tt + 0.2, 0.7))
            p.glow(ix, iy, 220, "accent", 0.25 * ei)
            self.icon_badge(p, self.s["icon"], ix, iy, 130 * max(ei, 0.01), "accent", ei, t, 1)
        if self.s.get("note"):
            en = out_back(prog(t, self.at(self.s, "note_at", tt + 2), 0.5))
            if en > 0:
                p.pill(self.s["note"], bx + bw / 2 if align == "center" else bx + p.text_w(self.s["note"], 28,
                       "semibold") / 2 + 20, by + bh - 30, 28, "warn", en, "bg0", tag="snote")

    def bars(self, p, t, bars, x, y, w, h):
        vmax = max(_num(b.get("value"), 1) for b in bars) or 1
        n = len(bars)
        row = h / n
        times = self.seq(bars, start=1.0)
        for i, (b, tt) in enumerate(zip(bars, times)):
            e = out_cubic(prog(t, tt, 0.9))
            if e <= 0:
                continue
            ry = y + i * row
            col = b.get("color", "accent")
            p.text(b.get("label", ""), x, ry + row * 0.08, 30, "text", e, "semibold", tag=f"bar{i}")
            bh = min(56, row * 0.36)
            by = ry + row * 0.08 + 46
            p.rrect(x, by, w, bh, bh / 2, fill="panel_hi", fill_a=e)
            frac = _num(b.get("value"), 0) / vmax
            p.rrect(x, by, max(bh, w * frac * e), bh, bh / 2, fill=col, fill_a=e)
            p.text(str(b.get("display", b.get("value"))), x + max(bh, w * frac * e) - 16, by + bh * 0.5 - 14, 28,
                   "bg0", e, "bold", "right", tag=f"barv{i}")


# ---------------------------------------------------------------------------
class Compare(Scene):
    def content(self, p, t):
        sx, sy, sw, sh = self.stage
        cards = self.s.get("cards", [])[:2]
        times = self.seq(cards, start=0.5)
        gap = 60
        for i, (cd, tt) in enumerate(zip(cards, times)):
            if self.L.portrait:
                ch = min(400, (sh - gap) / 2)
                top = sy + (sh - (2 * ch + gap)) / 2
                box = (sx, top + i * (ch + gap), sw, ch)
            else:
                cw = (sw - gap) / 2
                ch = min(sh, 440)
                box = (sx + i * (cw + gap), sy + (sh - ch) / 2, cw, ch)
            self.card(p, t, cd, tt, box, i)
        if len(cards) == 2:
            e = out_back(prog(t, times[1], 0.5))
            if self.L.portrait:
                cx, cy = sx + sw / 2, sy + sh / 2
            else:
                cx, cy = sx + sw / 2, sy + sh / 2
            p.circle(cx, cy, 34 * e, fill="bg1", stroke="stroke", lw=2)
            p.text(self.s.get("divider", "vs"), cx, cy - 13, 26, "muted", e, "bold", "center")

    def card(self, p, t, cd, tt, box, i):
        e = out_cubic(prog(t, tt, 0.6))
        if e <= 0:
            return
        x, y, w, h = box
        col = cd.get("color", "accent")
        y += 30 * (1 - e)
        p.rrect(x, y, w, h, 28, fill="panel", fill_a=0.95 * e, stroke=col, stroke_a=0.45 * e, lw=2)
        p.ctx.save()
        p.rrect_path(x, y, w, h, 28)
        p.ctx.clip()
        p.ctx.rectangle(x, y, w, 8)
        p.rgba(col, e)
        p.ctx.fill()
        p.ctx.restore()
        pad = 36
        p.text_block(cd.get("title", ""), x + pad, y + 26, w - 2 * pad, 56, 40, "text", e, "bold", max_lines=1,
                     min_size=26, tag=f"ctitle{i}")
        r = min(52, h * 0.13)
        fy = y + 26 + 56 + 50 + r
        ax, bx = x + pad + r + 10, x + w - pad - r - 10
        if cd.get("from_icon"):
            self.icon_badge(p, cd["from_icon"], ax, fy, r, cd.get("from_color", col), e, t)
            self.icon_badge(p, cd.get("to_icon", "spark"), bx, fy, r, cd.get("to_color", col), e, t)
            pr = in_out_cubic(prog(t, tt + 0.4, 0.8))
            p.arrow(ax, fy, bx, fy, col, e, 4, pr, 20, shrink=r + 16)
            if pr >= 1:
                for j in range(4):
                    u = ((t - tt) * 0.5 + j / 4) % 1.0
                    px_ = lerp(ax + r + 16, bx - r - 30, u)
                    p.glow(px_, fy, 16, col, 0.7 * e)
                    p.circle(px_, fy, 5, fill=col, fill_a=e)
            if cd.get("flow_label"):
                p.text_block(cd["flow_label"], ax + r + 20, fy - r - 44, bx - ax - 2 * r - 40, 40, 26, "muted",
                             e, "semibold", "center", max_lines=1, min_size=18, tag=f"flow{i}")
        items = cd.get("items", [])
        iy = fy + r + 34
        avail = y + h - 20 - iy
        rowh = min(64, avail / max(1, len(items)))
        for k, it in enumerate(items):
            ek = out_cubic(prog(t, tt + 0.8 + k * 0.35, 0.5))
            p.circle(x + pad + 8, iy + k * rowh + rowh / 2, 6, fill=col, fill_a=ek)
            p.text_block(it, x + pad + 30, iy + k * rowh, w - 2 * pad - 30, rowh, 30, "text", ek, "medium",
                         max_lines=2, valign="middle", min_size=18, tag=f"citem{i}{k}")


# ---------------------------------------------------------------------------
class Steps(Scene):
    def content(self, p, t):
        sx, sy, sw, sh = self.stage
        steps = self.s.get("steps", [])
        n = max(1, len(steps))
        times = self.seq(steps, start=0.5)
        active = max([i for i, tt in enumerate(times) if t >= tt], default=-1)
        if self.L.portrait:
            rowh = sh / n
            for i in range(n - 1):
                pr = in_out_cubic(prog(t, times[i + 1] - 0.3, 0.5))
                p.line(sx + 50, sy + i * rowh + rowh / 2 + 44, sx + 50, sy + (i + 1) * rowh + rowh / 2 - 44,
                       "stroke", 1, 4, progress=pr)
            for i, (st, tt) in enumerate(zip(steps, times)):
                e = out_cubic(prog(t, tt, 0.5))
                if e <= 0:
                    continue
                cy = sy + i * rowh + rowh / 2
                act = 1.0 if i == active else 0.0
                self.icon_badge(p, st.get("icon", "spark"), sx + 50, cy, 42, st.get("color", "accent"), e, t, act)
                p.pill(str(i + 1), sx + 86, cy - 34, 18, "accent", e, "bg0", "bold")
                x = sx + 130 + 20 * (1 - e)
                s, h, _ = p.text_block(st.get("title", ""), x, cy - rowh / 2 + 10, sw - 140, 50, 38, "text", e,
                                       "bold", max_lines=1, min_size=24, tag=f"step{i}")
                if st.get("text"):
                    p.text_block(st["text"], x, cy - rowh / 2 + 14 + h, sw - 140, rowh - h - 24, 28, "muted",
                                 e * (1 if act else 0.8), "medium", max_lines=2, min_size=18, tag=f"stext{i}")
            return
        gap = 34
        cw = (sw - gap * (n - 1)) / n
        cy = sy + sh * 0.5
        chh = min(sh * 0.86, 330 if any(st.get("text") for st in steps) else 270)
        for i in range(n - 1):
            pr = in_out_cubic(prog(t, times[i + 1] - 0.3, 0.5))
            x1 = sx + (i + 1) * cw + i * gap
            p.arrow(x1 - 4, cy - chh / 2 + 90, x1 + gap + 4, cy - chh / 2 + 90, "muted", 0.8, 3, pr, 12)
        for i, (st, tt) in enumerate(zip(steps, times)):
            e = out_cubic(prog(t, tt, 0.55))
            if e <= 0:
                continue
            x = sx + i * (cw + gap)
            y = cy - chh / 2 + 30 * (1 - e)
            act = 1.0 if i == active else 0.0
            col = st.get("color", "accent")
            if act:
                p.glow(x + cw / 2, y + chh / 2, cw * 0.9, col, 0.18)
            p.rrect(x, y, cw, chh, 26, fill="panel", fill_a=0.95 * e, stroke=col, stroke_a=(0.3 + 0.6 * act) * e,
                    lw=2.5)
            self.icon_badge(p, st.get("icon", "spark"), x + cw / 2, y + 90, 52, col, e, t, act)
            p.pill(f"{i + 1}", x + cw / 2 + 48, y + 44, 20, col, e, "bg0", "bold")
            s, h, _ = p.text_block(st.get("title", ""), x + 20, y + 168, cw - 40, 92, 36, "text", e, "bold",
                                   "center", max_lines=2, min_size=22, tag=f"step{i}")
            if st.get("text"):
                p.text_block(st["text"], x + 22, y + 176 + h, cw - 44, chh - 196 - h, 27, "muted", e, "medium",
                             "center", max_lines=4, min_size=18, tag=f"stext{i}")


# ---------------------------------------------------------------------------
class Orbit(Scene):
    def content(self, p, t):
        sx, sy, sw, sh = self.stage
        labels = self.s.get("labels", [])
        if self.L.portrait:
            ocx, ocy = sx + sw / 2, sy + sh * 0.3
            Re = sw * 0.14
        else:
            ocx, ocy = sx + sw / 2, sy + sh / 2
            Re = sh * 0.2
        planes = int(self.s.get("planes", 6))
        spp = int(self.s.get("sats_per_plane", 4))
        orbits_at = self.at(self.s, "orbits_at", 0.6)
        sats_at = self.at(self.s, "sats_at", orbits_at + 1.2)
        rx, ry = Re * 2.35, Re * 2.35 * 0.3
        sats = []
        c = p.ctx
        for k in range(planes):
            th = k * math.pi / planes + 0.25
            pr = in_out_cubic(prog(t, orbits_at + k * 0.12, 1.0))
            for half, lst in ((0, "back"), (1, "front")):
                pts = []
                for j in range(49):
                    ph = (math.pi if half == 0 else 0) + j / 48 * math.pi
                    x, y = rx * math.cos(ph), ry * math.sin(ph)
                    pts.append((ocx + x * math.cos(th) - y * math.sin(th), ocy + x * math.sin(th) + y * math.cos(th)))
                sats.append(("orbit", half, pts, pr))
            for j in range(spp):
                ph = t * 0.22 + j * 2 * math.pi / spp + k * 0.7
                x, y = rx * math.cos(ph), ry * math.sin(ph)
                X = ocx + x * math.cos(th) - y * math.sin(th)
                Y = ocy + x * math.sin(th) + y * math.cos(th)
                sats.append(("sat", 1 if math.sin(ph) > 0 else 0, (X, Y), k))
        for kind, half, data, extra in sats:
            if half == 0:
                self._draw_item(p, t, kind, data, extra, sats_at, back=True)
        self.earth(p, t, ocx, ocy, Re)
        for kind, half, data, extra in sats:
            if half == 1:
                self._draw_item(p, t, kind, data, extra, sats_at, back=False)
        links_at = self.s.get("links_at")
        if links_at is not None:
            pl = in_out_cubic(prog(t, _num(links_at), 0.8))
            rxp, ryp = ocx, ocy - Re
            front = [d for k_, h, d, _ in sats if k_ == "sat" and h == 1 and d[1] < ocy]
            front.sort(key=lambda d: math.dist(d, (rxp, ryp)))
            for d in front[:4]:
                p.line(rxp, ryp, d[0], d[1], "warn", 0.8, 2.5, [8, 8], pl)
            p.glow(rxp, ryp, 40, "warn", 0.8 * pl)
            p.circle(rxp, ryp, 9 * pl, fill="warn")
        self.labels(p, t, labels, ocx, ocy, rx)

    def _draw_item(self, p, t, kind, data, extra, sats_at, back):
        if kind == "orbit":
            p.polyline(data, "accent", 0.18 if back else 0.45, 2, extra)
        else:
            e = out_back(prog(t, sats_at + extra * 0.1, 0.5))
            if e <= 0:
                return
            X, Y = data
            a = 0.45 if back else 1.0
            p.glow(X, Y, 22, "accent", 0.5 * a * e)
            c = p.ctx
            c.save()
            c.translate(X, Y)
            c.scale(e, e)
            c.translate(-X, -Y)
            p.rrect(X - 7, Y - 7, 14, 14, 3, fill="text", fill_a=a)
            p.rrect(X - 22, Y - 4, 12, 8, 1, fill="accent", fill_a=a)
            p.rrect(X + 10, Y - 4, 12, 8, 1, fill="accent", fill_a=a)
            c.restore()

    def earth(self, p, t, cx, cy, R):
        e = out_back(prog(t, 0.2, 0.8))
        R = R * max(e, 0.01)
        p.glow(cx, cy, R * 1.6, "cold", 0.35)
        g = cairo.RadialGradient(cx - R * 0.35, cy - R * 0.4, R * 0.1, cx, cy, R)
        g.add_color_stop_rgba(0, 0.22, 0.55, 0.95, p.alpha)
        g.add_color_stop_rgba(1, 0.05, 0.16, 0.42, p.alpha)
        c = p.ctx
        c.new_path()
        c.arc(cx, cy, R, 0, 2 * math.pi)
        c.set_source(g)
        c.fill()
        c.save()
        c.arc(cx, cy, R, 0, 2 * math.pi)
        c.clip()
        for k in range(6):
            ph = (t * 0.15 + k / 6) % 1.0
            w = R * math.cos(ph * math.pi)
            c.save()
            c.translate(cx, cy)
            c.scale(max(abs(w), 0.5) / R, 1)
            c.arc(0, 0, R, 0, 2 * math.pi)
            c.restore()
            p.rgba("white", 0.12)
            c.set_line_width(1.5)
            c.stroke()
        for yy in (-0.5, 0, 0.5):
            hw = R * math.sqrt(1 - yy ** 2)
            p.line(cx - hw, cy + yy * R, cx + hw, cy + yy * R, "white", 0.12, 1.5)
        c.restore()
        p.circle(cx, cy, R, stroke="cool", stroke_a=0.6, lw=2)

    def labels(self, p, t, labels, ocx, ocy, rx):
        sx, sy, sw, sh = self.stage
        times = self.seq(labels, start=1.0)
        for i, (lb, tt) in enumerate(zip(labels, times)):
            e = out_cubic(prog(t, tt, 0.6))
            if e <= 0:
                continue
            if self.L.portrait:
                n = len(labels)
                top = ocy + rx * 1.0 + 40
                colw = (sw - 30) / 2
                x = sx + (i % 2) * (colw + 30)
                rows = math.ceil(n / 2)
                rh = (sy + sh - top) / max(1, rows)
                y = top + (i // 2) * rh
                w, h = colw, rh - 20
            else:
                side = i % 2
                w = (sw - 2 * rx) / 2 - 60
                x = sx if side == 0 else sx + sw - w
                n_side = math.ceil(len(labels) / 2)
                rh = min(200, sh / n_side)
                y = sy + (sh - rh * n_side) / 2 + (i // 2) * rh
                h = rh - 24
            x += (-24 if (i % 2 == 0) else 24) * (1 - e)
            p.rrect(x, y, w, h, 20, fill="panel", fill_a=0.92 * e, stroke="stroke", stroke_a=e, lw=2)
            p.rrect(x, y + 18, 6, h - 36, 3, fill="accent", fill_a=e)
            if lb.get("title"):
                s, hh, _ = p.text_block(lb["title"], x + 28, y + 16, w - 44, h * 0.5, 50, "text", e, "bold",
                                        max_lines=1, min_size=26, tag=f"ltitle{i}")
                p.text_block(lb.get("text", ""), x + 28, y + 20 + hh, w - 44, h - hh - 30, 26, "muted", e,
                             "medium", max_lines=2, min_size=16, tag=f"ltext{i}")
            else:
                p.text_block(lb.get("text", ""), x + 28, y + 12, w - 44, h - 24, 30, "text", e, "semibold",
                             max_lines=3, valign="middle", min_size=18, tag=f"ltext{i}")


# ---------------------------------------------------------------------------
class Signal(Scene):
    def content(self, p, t):
        sx, sy, sw, sh = self.stage
        if self.L.portrait:
            S = (sx + sw * 0.12, sy + sh * 0.08)
            Rc = (sx + sw * 0.8, sy + sh * 0.36)
            tl = (sx, sy + sh * 0.54, sw, sh * 0.2)
        else:
            S = (sx + sw * 0.1, sy + sh * 0.14)
            Rc = (sx + sw * 0.62, sy + sh * 0.5)
            tl = (sx, sy + sh * 0.76, sw * 0.62, sh * 0.24)
        es = out_back(prog(t, 0.3, 0.6))
        er = out_back(prog(t, 0.6, 0.6))
        self.icon_badge(p, "satellite", S[0], S[1], 58 * max(es, .01), "accent", es, t, 0.6)
        self.icon_badge(p, "phone", Rc[0], Rc[1], 58 * max(er, .01), "mint", er, t, 0.0)
        emit = self.at(self.s, "emit_at", 1.0)
        recv = self.at(self.s, "receive_at", emit + 2.5)
        pe = in_out_cubic(prog(t, emit, 0.8))
        p.line(S[0], S[1], Rc[0], Rc[1], "muted", 0.35, 2, [4, 10], pe)
        if t >= emit:
            period = 1.1
            d = math.dist(S, Rc)
            ang = math.atan2(Rc[1] - S[1], Rc[0] - S[0])
            for k in range(8):
                t0 = emit + k * period
                u = (t - t0) / 1.6
                if 0 <= u <= 1:
                    X, Y = lerp(S[0], Rc[0], u), lerp(S[1], Rc[1], u)
                    c = p.ctx
                    for j in range(3):
                        rr = 22 + j * 12
                        c.new_path()
                        c.arc(X - math.cos(ang) * j * 14, Y - math.sin(ang) * j * 14, rr, ang - 0.6, ang + 0.6)
                        p.rgba("accent", (0.9 - j * 0.25) * (1 - abs(u - 0.5) * 0.6))
                        c.set_line_width(3)
                        c.stroke()
        packet = self.s.get("packet", [])
        ptimes = self.seq(packet, start=emit + 0.3, gap=0.6)
        for i, (pk, tt) in enumerate(zip(packet, ptimes)):
            e = out_back(prog(t, tt, 0.45))
            if e <= 0:
                continue
            txt = pk["text"] if isinstance(pk, dict) else str(pk)
            bx = S[0] + 90 if not self.L.portrait else S[0] + 90
            by = S[1] - 40 + i * 58
            w = p.text_w(txt, 26, "semibold") + 36
            p.rrect(bx, by, w * e, 44, 12, fill="panel_hi", fill_a=0.95 * e, stroke="accent", stroke_a=0.5 * e)
            p.text(txt, bx + 18, by + 9, 26, "text", e, "semibold", tag=f"pk{i}")
        er2 = out_back(prog(t, recv, 0.45))
        if er2 > 0 and self.s.get("receive_label"):
            txt = self.s["receive_label"]
            w = p.text_w(txt, 26, "semibold") + 36
            bx = Rc[0] - w / 2
            by = Rc[1] + 80
            p.rrect(bx, by, w, 44, 12, fill="panel_hi", fill_a=0.95 * er2, stroke="mint", stroke_a=0.6 * er2)
            p.text(txt, bx + 18, by + 9, 26, "text", er2, "semibold", tag="recv")
        self.timeline(p, t, *tl)
        self.formula(p, t)

    def timeline(self, p, t, x, y, w, h):
        dt_at = self.s.get("delta_at")
        if dt_at is None:
            return
        tt = _num(dt_at)
        e = out_cubic(prog(t, tt, 0.6))
        if e <= 0:
            return
        ly = y + h * 0.45
        p.line(x, ly, x + w * e, ly, "stroke", 1, 3)
        t1, t2 = x + w * 0.18, x + w * 0.78
        for tx, lab, col in ((t1, "sent", "accent"), (t2, "received", "mint")):
            p.line(tx, ly - 18, tx, ly + 18, col, e, 4)
            p.text(lab, tx, ly + 26, 24, "muted", e, "semibold", "center", tag=f"tl{lab}")
        pb = in_out_cubic(prog(t, tt + 0.3, 0.8))
        p.line(t1, ly - 40, lerp(t1, t2, pb), ly - 40, "warn", e, 4)
        p.arrow_head(lerp(t1, t2, pb), ly - 40, 0, "warn", e * pb, 16)
        if self.s.get("delta_label") and pb > 0.95:
            p.pill(self.s["delta_label"], (t1 + t2) / 2, ly - 76, 26, "warn", e, "bg0", tag="delta")

    def formula(self, p, t):
        sx, sy, sw, sh = self.stage
        items = [("formula", "formula_at", "text", 44), ("result", "result_at", "accent", 64)]
        if self.L.portrait:
            x0, w = sx, sw
            ys = [sy + sh * 0.78, sy + sh * 0.78 + 80]
        else:
            x0, w = sx + sw * 0.7, sw * 0.3
            ys = [sy + sh * 0.26, sy + sh * 0.26 + 100]
        for (key, at_key, col, size), y in zip(items, ys):
            if not self.s.get(key):
                continue
            e = out_cubic(prog(t, self.at(self.s, at_key, 4.0), 0.6))
            if e <= 0:
                continue
            p.text_block(self.s[key], x0, y + 20 * (1 - e), w, size * 2.4, size, col, e, "bold",
                         max_lines=2, min_size=22, tag=key)


# ---------------------------------------------------------------------------
class Trilateration(Scene):
    def pt(self, o):
        sx, sy, sw, sh = self.stage
        x, y = _num(o.get("x"), 0.5), _num(o.get("y"), 0.5)
        if self.L.portrait and "px" in o:
            x, y = _num(o["px"]), _num(o.get("py"), y)
        return sx + x * sw, sy + y * sh

    def fitted(self, anchors, bands):
        """Scale/centre the construction so every circle (and label) stays inside the stage."""
        sx, sy, sw, sh = self.stage
        T = self.pt(self.s.get("target", {"x": 0.5, "y": 0.6}))
        pts = [self.pt(a) for a in anchors]
        grow = 1.1 if bands else 1.0
        pad = 34 if bands else 12
        x0 = y0 = float("inf")
        x1 = y1 = float("-inf")
        for A in pts:
            r = math.dist(A, T) * grow + pad
            x0, x1 = min(x0, A[0] - r), max(x1, A[0] + r)
            y0, y1 = min(y0, A[1] - r, A[1] - 90), max(y1, A[1] + r)
        y1 = max(y1, T[1] + 80)
        bw, bh = x1 - x0, y1 - y0
        k = min(1.0, sw / bw, sh / bh)
        ox = sx + (sw - bw * k) / 2 - x0 * k
        oy = sy + (sh - bh * k) / 2 - y0 * k
        tf = lambda q: (ox + q[0] * k, oy + q[1] * k)  # noqa: E731
        return tf(T), [tf(A) for A in pts]

    def content(self, p, t):
        anchors = self.s.get("anchors", [])
        times = self.seq(anchors, start=0.6)
        bands = bool(self.s.get("bands"))
        T, apts = self.fitted(anchors, bands)
        tighten = self.at(self.s, "tighten_at", 1e9) if bands else -1
        tight = in_out_cubic(prog(t, tighten, 1.2)) if bands else 1.0
        cols = ["accent", "violet", "mint", "warn"]
        for i, (an, tt) in enumerate(zip(anchors, times)):
            A = apts[i]
            col = an.get("color", cols[i % 4])
            d = math.dist(A, T)
            gr = out_cubic(prog(t, tt + 0.3, 1.2))
            if gr <= 0:
                continue
            err = (1 - tight) * d * 0.09 * (1 if i % 2 == 0 else -0.7)
            r = (d + err) * gr
            if bands and tight < 1:
                bw = lerp(46, 4, tight)
                p.circle(A[0], A[1], r, stroke=col, stroke_a=0.28, lw=bw)
            p.circle(A[0], A[1], r, fill=col, fill_a=0.05, stroke=col, stroke_a=0.9, lw=3)
        for i, (an, tt) in enumerate(zip(anchors, times)):
            A = apts[i]
            e = out_back(prog(t, tt, 0.5))
            if e <= 0:
                continue
            col = an.get("color", cols[i % 4])
            p.glow(A[0], A[1], 60, col, 0.4 * e)
            p.circle(A[0], A[1], 34 * e, fill="panel", stroke=col, lw=3)
            draw_icon(p, "satellite", A[0], A[1], 44 * e, col, e, t)
            if an.get("label"):
                p.pill(an["label"], A[0], A[1] - 62, 22, col, e, "bg0", tag=f"anc{i}")
        fx = self.s.get("fix_at")
        if fx is not None:
            e = out_back(prog(t, _num(fx), 0.6))
            if e > 0:
                pulse = (t - _num(fx)) % 1.4 / 1.4
                p.circle(T[0], T[1], 20 + 50 * pulse, stroke="warn", stroke_a=(1 - pulse) * e, lw=3)
                p.glow(T[0], T[1], 50, "warn", 0.8 * e)
                p.circle(T[0], T[1], 11 * e, fill="warn")
                if self.s.get("fix_label"):
                    w = p.text_w(self.s["fix_label"], 24, "semibold") + 29
                    cands = [(T[0], T[1] + 56), (T[0], T[1] - 56), (T[0] + w / 2 + 34, T[1]),
                             (T[0] - w / 2 - 34, T[1]), (T[0], T[1] + 96), (T[0], T[1] - 96)]

                    obstacles = [(A[0], A[1], 40) for A in apts] + \
                                [(A[0], A[1] - 62, 60) for A in apts]

                    def clearance(q):
                        return min((max(abs(q[0] - ox) - w / 2 - hw, abs(q[1] - oy) - 64)
                                    for ox, oy, hw in obstacles), default=1e9)
                    q = max(cands, key=clearance)
                    p.pill(self.s["fix_label"], q[0], q[1], 24, "warn", e, "bg0", tag="fix")


# ---------------------------------------------------------------------------
class Recap(Scene):
    def content(self, p, t):
        sx, sy, sw, sh = self.stage
        items = [it if isinstance(it, dict) else {"text": str(it)} for it in self.s.get("items", [])]
        times = self.seq(items, start=0.5, gap=max(0.35, min(1.2, (self.dur - 3) / max(1, len(items)))))
        n = max(1, len(items))
        cols = 1 if self.L.portrait else (2 if n <= 4 else 3)
        rows = math.ceil(n / cols)
        area_h = sh * (0.72 if self.s.get("title") else 1.0)
        gap = 26
        cw = (sw - gap * (cols - 1)) / cols
        chh = min(130, (area_h - gap * (rows - 1)) / rows)
        oy = sy + (area_h - (chh * rows + gap * (rows - 1))) / 2
        for i, (it, tt) in enumerate(zip(items, times)):
            e = out_back(prog(t, tt, 0.5))
            if e <= 0:
                continue
            r_, c_ = divmod(i, cols)
            x, y = sx + c_ * (cw + gap), oy + r_ * (chh + gap) + 20 * (1 - e)
            col = it.get("color", "accent")
            p.rrect(x, y, cw, chh, 22, fill="panel", fill_a=0.95 * min(1, e), stroke=col, stroke_a=0.5, lw=2)
            ir = chh * 0.3
            self.icon_badge(p, it.get("icon", "check"), x + 24 + ir, y + chh / 2, ir, col, min(1, e), t)
            tx = x + 24 + ir * 2 + 24
            p.text_block(it.get("text", ""), tx, y + 10, x + cw - 20 - tx, chh - 20, 36, "text", min(1, e),
                         "semibold", max_lines=2, valign="middle", min_size=22, tag=f"recap{i}")
        if self.s.get("title"):
            te = out_cubic(prog(t, self.at(self.s, "end_at", self.dur - 3.0), 0.8))
            if te > 0:
                y = sy + sh * 0.8
                p.rrect(sx + sw / 2 - 60 * te, y, 120 * te, 5, 2.5, fill="accent", fill_a=te)
                p.text_block(self.s["title"], sx, y + 24, sw, 70, 48, "text", te, "bold", "center",
                             max_lines=1, min_size=28, tag="endtitle")


TEMPLATES = {
    "title": Title, "bullets": Bullets, "diagram": Diagram, "cycle": Cycle, "cutaway": Cutaway, "stat": Stat,
    "compare": Compare, "steps": Steps, "orbit": Orbit, "signal": Signal, "trilateration": Trilateration,
    "recap": Recap,
}
