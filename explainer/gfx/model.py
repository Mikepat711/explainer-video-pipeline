"""A visual-plan scene as a function of time.

This is the animation model behind the renderer, with no drawing in it: beats become tracks, actors get a
presence (enter/exit), a position (moves along arcs), parameter values and phase integrals (so a rotor that
speeds up keeps its angle continuous), and the camera glides between regions. The timeline stage uses it to
carry a scene's final state into scenes that `inherit` from it; the renderer samples it every frame.
"""
from __future__ import annotations

import math
from copy import deepcopy

from ..plan.vocab import DESIGN_H, DESIGN_W, KINDS

FULL = (0.0, 0.0, float(DESIGN_W), float(DESIGN_H))
MOTION = {"calm": 1.3, "measured": 1.0, "lively": 0.8}
DEFAULT_DUR = {"set": 1.0, "move": 1.2, "enter": 0.7, "exit": 0.5, "pulse": 0.9, "trace": 1.4, "camera": 1.6}

DEFAULTS: dict[str, dict] = {
    "text": {"size": "m", "weight": "medium", "align": "center", "color": "ink", "max_width": 1100},
    "label": {"side": "auto", "leader": True, "color": "ink"},
    "badge": {"color": "accent", "size": 46},
    "dimension": {"offset": 40, "color": "muted"},
    "shape": {"w": 200, "h": 120, "r": 60, "stroke_width": 3, "fill_level": 1.0},
    "path": {"width": 6, "color": "muted", "arrow": "none"},
    "arrow": {"curve": 0, "color": "accent", "width": 6},
    "icon": {"size": 72, "color": "accent"},
    "flow": {"particles": 14, "speed": 140, "size": 7, "color": "accent", "style": "dots", "direction": "forward"},
    "wave": {"w": 420, "h": 150, "waveform": "sine", "cycles": 3, "amplitude": 0.8, "speed": 1.0, "phase": 0,
             "color": "accent", "axis": True},
    "rotor": {"radius": 80, "style": "turbine", "poles": 2, "rpm": 30, "color": "accent"},
    "coil": {"turns": 8, "length": 220, "radius": 50, "orientation": "horizontal", "current": 0, "color": "accent2"},
    "field": {"radius": 160, "lines": 6, "style": "magnetic", "strength": 0.8, "color": "accent"},
    "gear": {"rpm": 20, "color": "muted", "spokes": 5},
    "chain": {"speed": 120, "color": "muted"},
    "spring": {"coils": 10, "compression": 0, "color": "muted"},
    "lever": {"angle": 0, "width": 16, "color": "muted"},
    "cable": {"tension": 0.5, "color": "muted", "width": 5},
    "gauge": {"decimals": 0, "radius": 110, "style": "dial"},
    "meter": {"decimals": 0, "color": "accent", "size": "m"},
    "bars": {"w": 520, "h": 300, "orientation": "vertical"},
    "line_chart": {"w": 640, "h": 340, "progress": 1.0},
    "balance": {"width": 480, "color": "muted"},
    "network": {},
    "compare": {"w": 900},
    "plant": {"output": 0.8, "size": 220},
    "generator": {"rpm": 60, "poles": 2, "size": 300, "show_wave": False},
    "transformer": {"primary_turns": 10, "secondary_turns": 4, "flux": 0.8, "size": 300, "show_meters": True},
    "tower": {"height": 260, "circuits": 1, "color": "muted"},
    "powerline": {"voltage": "hv", "supports": 0, "sag": 30, "flow": 0.6, "heat": 0},
    "substation": {"size": 280, "breakers": 3, "state": "normal"},
    "pole": {"height": 200, "transformer": False, "color": "muted"},
    "house": {"style": "house", "lights": 0.8, "load": 0.3, "size": 120},
    "city": {"buildings": 12, "w": 420, "h": 240, "lights": 0.8},
    "factory": {"load": 0.6, "size": 220},
    "breaker": {"state": "closed", "size": 90},
    "battery": {"charge": 0.6, "flow": 0, "size": 140},
}

# parameters whose running integral drives continuous motion (angles, particle offsets, wave phase)
PHASED = {"rotor": ("rpm",), "gear": ("rpm",), "generator": ("rpm",), "flow": ("speed",), "wave": ("speed",),
          "powerline": ("flow",), "chain": ("speed",), "plant": ("output",), "factory": ("load",),
          "battery": ("flow",), "transformer": ("flux",), "house": ("load",), "coil": ("current",)}
REF_KINDS = {"arrow", "powerline", "dimension", "spring", "flow", "field", "chain"}
POINT_KINDS = {"path", "cable"}
TEXT_SIZES = {"xs": 22, "s": 28, "m": 36, "l": 48, "xl": 64, "xxl": 88}
METER_SIZES = {"s": (180, 84, 34), "m": (240, 104, 46), "l": (320, 132, 62), "xl": (420, 170, 84)}


# ---- easing -------------------------------------------------------------------------------------
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def ease(name: str, x: float) -> float:
    x = clamp(x)
    if name == "linear":
        return x
    if name == "in":
        return x ** 3
    if name == "out":
        return 1 - (1 - x) ** 3
    if name == "step":
        return 1.0 if x >= 1 else 0.0
    if name == "spring":
        return 1.0 if x >= 1 else 1 - math.exp(-6 * x) * math.cos(3 * math.pi * x) * (1 - x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _numlist(v) -> bool:
    return isinstance(v, list) and bool(v) and all(_num(x) for x in v)


class Track:
    """One parameter over time: numbers (and lists of numbers) tween; anything else switches at the end."""

    __slots__ = ("v0", "segs", "_cum", "_dt", "_end")

    def __init__(self, v0):
        self.v0, self.segs, self._cum, self._dt, self._end = v0, [], None, 1 / 120, 0.0

    def add(self, t0: float, dur: float, to, ease_name: str = "smooth") -> None:
        self.segs.append((t0, t0 + max(dur, 1e-4), self.value(t0), to, ease_name))
        self.segs.sort(key=lambda s: s[0])
        self._cum = None

    def value(self, t: float):
        v = self.v0
        for t0, t1, a, b, e in self.segs:
            if t < t0:
                break
            if t >= t1:
                v = b
                continue
            f = ease(e, (t - t0) / (t1 - t0))
            if _num(a) and _num(b):
                return lerp(a, b, f)
            if _numlist(a) and _numlist(b):
                n = max(len(a), len(b))
                aa, bb = a + [0] * (n - len(a)), b + [0] * (n - len(b))
                return [lerp(x, y, f) for x, y in zip(aa, bb)]
            return a
        return v

    def changed_at(self, t: float) -> tuple[float | None, object]:
        """(time of the last completed switch at or before t, value before it) for enum transitions."""
        last, prev = None, self.v0
        for t0, t1, a, b, _ in self.segs:
            if t1 <= t:
                last, prev = t1, a
        return last, prev

    def integral(self, t: float) -> float:
        v0 = float(self.v0) if _num(self.v0) else 0.0
        if not self.segs:
            return v0 * t
        if self._cum is None:
            self._end = max(s[1] for s in self.segs)
            n = int(math.ceil(self._end / self._dt)) + 1
            vals = [float(self.value(k * self._dt) or 0) for k in range(n + 1)]
            cum = [0.0]
            for k in range(n):
                cum.append(cum[-1] + (vals[k] + vals[k + 1]) * 0.5 * self._dt)
            self._cum = cum
        n = len(self._cum) - 1
        t_top = n * self._dt
        if t >= t_top:
            return self._cum[-1] + float(self.value(t_top) or 0) * (t - t_top)
        if t <= 0:
            return v0 * t
        k = int(t / self._dt)
        tk = k * self._dt
        return self._cum[k] + (float(self.value(tk) or 0) + float(self.value(t) or 0)) * 0.5 * (t - tk)


class Presence:
    __slots__ = ("alpha", "reveal", "dx", "dy", "scale", "wipe", "anim", "p", "entering")

    def __init__(self, alpha=1.0, reveal=1.0, dx=0.0, dy=0.0, scale=1.0, wipe=1.0, anim="", p=1.0, entering=False):
        self.alpha, self.reveal, self.dx, self.dy, self.scale, self.wipe = alpha, reveal, dx, dy, scale, wipe
        self.anim, self.p, self.entering = anim, p, entering


def _enter(anim: str, p: float) -> Presence:
    e = ease("out", p)
    if anim == "draw":
        return Presence(min(1.0, p * 4), ease("smooth", p), anim=anim, p=p, entering=True)
    if anim == "pop":
        s = 1 + 1.7 * (p - 1) ** 3 + 0.7 * (p - 1) ** 2 if p < 1 else 1.0
        return Presence(min(1.0, p * 3), 1.0, scale=max(0.01, s), anim=anim, p=p, entering=True)
    if anim == "grow":
        return Presence(min(1.0, p * 3), 1.0, scale=max(0.01, e), anim=anim, p=p, entering=True)
    if anim in ("slide_up", "slide_down", "slide_left", "slide_right"):
        d = 70 * (1 - e)
        dx, dy = {"slide_up": (0, d), "slide_down": (0, -d), "slide_left": (d, 0), "slide_right": (-d, 0)}[anim]
        return Presence(e, 1.0, dx, dy, anim=anim, p=p, entering=True)
    if anim == "wipe":
        return Presence(1.0, 1.0, wipe=ease("smooth", p), anim=anim, p=p, entering=True)
    if anim == "build":
        return Presence(min(1.0, p * 2.5), ease("smooth", p), anim=anim, p=p, entering=True)
    return Presence(ease("smooth", p), 1.0, anim=anim or "fade", p=p, entering=True)


def _exit(anim: str, p: float) -> Presence:
    e = ease("in", p)
    if anim == "shrink":
        return Presence(1 - p * p, 1.0, scale=max(0.01, 1 - e), anim=anim, p=p)
    if anim in ("slide_up", "slide_down", "slide_left", "slide_right"):
        d = 70 * e
        dx, dy = {"slide_up": (0, -d), "slide_down": (0, d), "slide_left": (-d, 0), "slide_right": (d, 0)}[anim]
        return Presence(1 - e, 1.0, dx, dy, anim=anim, p=p)
    return Presence(1 - ease("smooth", p), 1.0, anim=anim or "fade", p=p)


class Actor:
    def __init__(self, spec: dict, order: int):
        self.id, self.kind, self.order = spec["id"], spec["kind"], order
        self.spec = spec
        self.z = int(spec.get("z", 0))
        self.params0 = {**DEFAULTS.get(self.kind, {}), **deepcopy(spec.get("params") or {})}
        self.carry: dict[str, float] = dict(spec.get("_carry") or {})
        self.at0 = tuple(spec["at"]) if spec.get("at") else _default_at(self.kind, self.params0)
        self.tracks: dict[str, Track] = {}
        for k in ("scale", "rotate", "opacity"):
            self.tracks[k] = Track(float(spec.get(k, {"scale": 1.0, "rotate": 0.0, "opacity": 1.0}[k])))
        self.visible0 = spec.get("visible", True) is not False
        self.events: list[tuple[float, float, str, str]] = []
        self.moves: list[tuple[float, float, tuple, tuple, float, str]] = []
        self.pulses: list[tuple[float, float, int, str | None]] = []
        self.traces: list[tuple[float, float, str | None, str]] = []
        self.sub: dict[str, dict[str, Track]] = {}

    # ---- values ----------------------------------------------------------------------------------
    def track(self, param: str) -> Track:
        if param not in self.tracks:
            self.tracks[param] = Track(self.params0.get(param, 0.0 if param in ("fill_level",) else None))
        return self.tracks[param]

    def value(self, param: str, t: float):
        tr = self.tracks.get(param)
        return tr.value(t) if tr else self.params0.get(param)

    def params(self, t: float) -> dict:
        out = dict(self.params0)
        for k, tr in self.tracks.items():
            if k not in ("scale", "rotate", "opacity"):
                out[k] = tr.value(t)
        return out

    def phase(self, param: str, t: float) -> float:
        tr = self.tracks.get(param)
        base = self.carry.get(param, 0.0)
        if tr is None:
            v = self.params0.get(param, 0.0)
            return base + (float(v) if _num(v) else 0.0) * t
        return base + tr.integral(t)

    def sub_track(self, part: str, param: str) -> Track:
        d = self.sub.setdefault(part, {})
        if param not in d:
            d[param] = Track(self._sub_default(part, param))
        return d[param]

    def _sub_default(self, part: str, param: str):
        for n in self.params0.get("nodes") or []:
            if n.get("id") == part:
                return n.get(param, "normal" if param == "state" else 0.0)
        for e in self.params0.get("edges") or []:
            if f"{e.get('from')}-{e.get('to')}" == part:
                return e.get(param, "normal" if param == "state" else 0.0)
        return "normal" if param == "state" else 0.0

    def sub_value(self, part: str, param: str, t: float):
        tr = (self.sub.get(part) or {}).get(param)
        return tr.value(t) if tr else self._sub_default(part, param)

    def sub_phase(self, part: str, t: float) -> float:
        tr = (self.sub.get(part) or {}).get("flow")
        base = self.carry.get(f"{part}.flow", 0.0)
        return base + (tr.integral(t) if tr else float(self._sub_default(part, "flow") or 0) * t)

    # ---- placement -------------------------------------------------------------------------------
    def position(self, t: float) -> tuple[float, float]:
        pos = self.at0
        for t0, t1, a, b, curve, e in self.moves:
            if t < t0:
                break
            start = pos
            if t >= t1:
                pos = b
                continue
            f = ease(e, (t - t0) / (t1 - t0))
            if curve:
                mx, my = (start[0] + b[0]) / 2, (start[1] + b[1]) / 2
                dx, dy = b[0] - start[0], b[1] - start[1]
                cx, cy = mx - dy * curve * 0.5, my + dx * curve * 0.5
                u = 1 - f
                return (u * u * start[0] + 2 * u * f * cx + f * f * b[0], u * u * start[1] + 2 * u * f * cy + f * f * b[1])
            return (lerp(start[0], b[0], f), lerp(start[1], b[1], f))
        return pos

    def presence(self, t: float) -> Presence:
        visible = self.visible0 and not (self.events and self.events[0][2] == "enter")
        last = None
        for ev in self.events:
            if ev[0] <= t:
                last = ev
        if last is None:
            return Presence(1.0 if visible else 0.0)
        p = clamp((t - last[0]) / max(last[1], 1e-4))
        return _enter(last[3], p) if last[2] == "enter" else _exit(last[3], p)

    def emphasis(self, t: float) -> tuple[float, str | None]:
        best, color = 0.0, None
        for t0, dur, rep, col in self.pulses:
            if t0 <= t <= t0 + dur * rep:
                local = ((t - t0) / dur) % 1.0
                v = math.sin(math.pi * local) ** 2
                if v > best:
                    best, color = v, col
        return best, color


def _default_at(kind: str, prm: dict) -> tuple[float, float]:
    pts = prm.get("points") if kind in POINT_KINDS else None
    if kind == "network":
        pts = [n.get("at") for n in prm.get("nodes") or [] if isinstance(n, dict) and n.get("at")]
    if pts:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    return (DESIGN_W / 2, DESIGN_H / 2)


def network_relative(prm: dict, at_given: bool) -> bool:
    """Node coordinates are absolute design-space points unless they clearly sit around (0, 0)."""
    pts = [n.get("at") for n in prm.get("nodes") or [] if isinstance(n, dict) and n.get("at")]
    return at_given and bool(pts) and any(p[0] < 0 or p[1] < 0 for p in pts) and all(
        abs(p[0]) <= 820 and abs(p[1]) <= 470 for p in pts)


# ---- local geometry ------------------------------------------------------------------------------
def local_box(a: Actor, prm: dict) -> tuple[float, float, float, float]:
    """Unscaled extent around the actor's position: (x0, y0, x1, y1)."""
    k = a.kind
    g = lambda name: float(prm.get(name) or DEFAULTS.get(k, {}).get(name) or 0)  # noqa: E731
    if k == "text":
        size = TEXT_SIZES.get(prm.get("size", "m"), 36)
        w = min(g("max_width") or 1100, 0.56 * size * len(str(prm.get("text", ""))))
        lines = max(1, math.ceil(0.56 * size * len(str(prm.get("text", ""))) / max(1, g("max_width") or 1100)))
        x0 = {"left": 0, "right": -w}.get(prm.get("align", "center"), -w / 2)
        return (x0, -size * 0.6 * lines, x0 + w, size * 0.6 * lines)
    if k == "label":
        w = 0.55 * 28 * len(str(prm.get("text", ""))) + 30
        return (-w / 2, -22, w / 2, 22)
    if k == "badge":
        s = g("size") / 2
        return (-s, -s, s, s)
    if k == "shape":
        sh = prm.get("shape", "rect")
        if sh in ("circle", "ring"):
            r = g("r")
            return (-r, -r, r, r)
        if sh == "polygon" and prm.get("points"):
            xs, ys = [p[0] for p in prm["points"]], [p[1] for p in prm["points"]]
            return (min(xs), min(ys), max(xs), max(ys))
        return (-g("w") / 2, -g("h") / 2, g("w") / 2, g("h") / 2)
    if k in POINT_KINDS and prm.get("points"):
        xs, ys = [p[0] - a.at0[0] for p in prm["points"]], [p[1] - a.at0[1] for p in prm["points"]]
        return (min(xs), min(ys), max(xs), max(ys))
    if k == "network":
        pts = [n["at"] for n in prm.get("nodes") or [] if n.get("at")]
        if not pts:
            return (-100, -100, 100, 100)
        rel = network_relative(prm, bool(a.spec.get("at")))
        xs = [p[0] - (0 if rel else a.at0[0]) for p in pts]
        ys = [p[1] - (0 if rel else a.at0[1]) for p in pts]
        return (min(xs) - 40, min(ys) - 40, max(xs) + 40, max(ys) + 60)
    if k == "icon":
        s = g("size") / 2
        return (-s, -s, s, s)
    if k == "wave":
        return (-g("w") / 2, -g("h") / 2, g("w") / 2, g("h") / 2)
    if k in ("rotor", "gear"):
        r = g("radius") * 1.08
        return (-r, -r, r, r)
    if k == "coil":
        L, r = g("length") / 2, g("radius")
        return (-L, -r, L, r) if prm.get("orientation", "horizontal") == "horizontal" else (-r, -L, r, L)
    if k == "lever":
        L, ang, pad = g("length"), math.radians(g("angle")), g("width") * 0.75
        tx, ty = L * math.cos(ang), L * math.sin(ang)
        return (min(0.0, tx) - pad, min(0.0, ty) - pad, max(0.0, tx) + pad, max(0.0, ty) + pad)
    if k == "gauge":
        r = g("radius")
        st = prm.get("style", "dial")
        if st == "vertical":
            return (-0.35 * r, -r, 0.35 * r, r + 40)
        if st == "arc":
            return (-r * 1.12, -r * 1.12, r * 1.12, 0.35 * r + 30)
        return (-r, -r, r, r * 0.95 + (max(18, r * 0.16) + 14 if prm.get("text") else 0))
    if k == "meter":
        w, h, _ = METER_SIZES.get(prm.get("size", "m"), METER_SIZES["m"])
        return (-w / 2, -h / 2, w / 2, h / 2 + (30 if prm.get("text") else 0))
    if k in ("bars", "line_chart"):
        return (-g("w") / 2, -g("h") / 2, g("w") / 2, g("h") / 2)
    if k == "balance":
        w = g("width")
        fh, drop, pr = balance_dims(w)
        lift = w / 2 * math.sin(math.radians(14))
        return (-w / 2 - 40, -lift - 12, w / 2 + 40, max(fh, lift + drop + pr + 40))
    if k == "compare":
        w = g("w")
        return (-w / 2, -170, w / 2, 170)
    if k in ("plant", "factory", "house"):
        s = g("size")
        return (-s / 2, -s / 2, s / 2, s / 2)
    if k == "generator":
        s = g("size")
        return (-s / 2, -s / 2, s / 2 + (s * 1.05 if prm.get("show_wave") else 0), s / 2)
    if k == "transformer":
        s = g("size")
        st = prm.get("style", "cutaway")
        h = {"cutaway": 0.78, "substation": 0.8, "pole_can": 1.2, "symbol": 0.6}.get(st, 0.8) * s
        w = {"pole_can": 0.55, "symbol": 0.9}.get(st, 1.0) * s
        top = 0.22 * s if st == "cutaway" and prm.get("show_meters", True) else 0
        return (-w / 2, -h / 2 - top, w / 2, h / 2)
    if k == "tower":
        h = g("height")
        return (-0.36 * h, -h / 2, 0.36 * h, h / 2)
    if k == "pole":
        h = g("height")
        return (-0.24 * h, -h / 2, 0.24 * h, h / 2)
    if k == "substation":
        s = g("size")
        return (-s / 2, -0.36 * s, s / 2, 0.36 * s)
    if k == "city":
        return (-g("w") / 2, -g("h") / 2, g("w") / 2, g("h") / 2)
    if k == "breaker":
        s = g("size")
        return (-s / 2, -0.42 * s, s / 2, 0.42 * s)
    if k == "battery":
        s = g("size")
        return (-0.65 * s, -0.42 * s, 0.65 * s, 0.42 * s)
    return (-60, -60, 60, 60)


def local_anchor(a: Actor, prm: dict, name: str) -> tuple[float, float] | None:
    x0, y0, x1, y1 = local_box(a, prm)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    box = {"center": (cx, cy), "top": (cx, y0), "bottom": (cx, y1), "left": (x0, cy), "right": (x1, cy)}
    if name in box:
        return box[name]
    k = a.kind
    s = float(prm.get("size") or 0)
    if k in POINT_KINDS and prm.get("points"):
        pts = [(p[0] - a.at0[0], p[1] - a.at0[1]) for p in prm["points"]]
        return {"start": pts[0], "end": pts[-1], "mid": _poly_at(pts, 0.5)}.get(name)
    if k == "coil":
        L = float(prm.get("length", 220)) / 2
        r = float(prm.get("radius", 50))
        hor = prm.get("orientation", "horizontal") == "horizontal"
        if name == "lead_in":
            return (-L - 30, r) if hor else (-r, L + 30)
        if name == "lead_out":
            return (L + 30, r) if hor else (r, L + 30)
    if k == "lever":
        L = float(prm.get("length", 100))
        ang = math.radians(float(prm.get("angle", 0)))
        return {"pivot": (0, 0), "tip": (L * math.cos(ang), L * math.sin(ang)),
                "center": (L / 2 * math.cos(ang), L / 2 * math.sin(ang))}.get(name)
    if k == "balance":
        w = float(prm.get("width", 480))
        tilt = balance_tilt(prm)
        dx, dy = w / 2 * math.cos(tilt), w / 2 * math.sin(tilt)
        drop = balance_dims(w)[1]
        return {"left_pan": (-dx, -dy + drop), "right_pan": (dx, dy + drop)}.get(name)
    if k == "plant":
        if name == "out":
            return (s * 0.5, -s * 0.08)
    if k == "generator":
        if name == "out":
            return (s * 0.5, 0)
    if k == "transformer":
        st = prm.get("style", "cutaway")
        w = {"pole_can": 0.55, "symbol": 0.9}.get(st, 1.0) * s
        y = -0.28 * s if st in ("substation", "pole_can") else 0
        return {"in": (-w / 2, y), "out": (w / 2, y)}.get(name)
    if k == "tower":
        h = float(prm.get("height", 260))
        arm_y = -h / 2 + 0.22 * h + 0.09 * h
        return {"arm_left": (-0.34 * h, arm_y), "arm_right": (0.34 * h, arm_y),
                "top_wire": (0, -h / 2)}.get(name)
    if k == "pole":
        h = float(prm.get("height", 200))
        return {"top_wire": (0.2 * h, -h / 2 + 0.07 * h - 0.04 * h), "drop": (0.14 * h, -h / 2 + 0.36 * h)}.get(name)
    if k == "substation":
        return {"in": (-s / 2, -0.12 * s), "out": (s / 2, -0.12 * s)}.get(name)
    if k in ("house", "factory"):
        if name == "in":
            return (-s * 0.42, -s * 0.12)
    if k == "city":
        if name == "in":
            return (x0, cy)
    if k in ("breaker", "battery"):
        return {"in": (x0, 0), "out": (x1, 0)}.get(name)
    return None


def balance_tilt(prm: dict) -> float:
    left, right = float(prm.get("left") or 0), float(prm.get("right") or 0)
    tot = max(left, right, 1e-6)
    return math.radians(14) * clamp((right - left) / tot, -1, 1)


def balance_dims(w: float) -> tuple[float, float, float]:
    """(fulcrum height, pan drop, pan radius); capped so a wide beam stays a short, readable band."""
    return min(0.36 * w, 110.0), min(0.2 * w, 110.0), min(0.11 * w, 64.0)


def _poly_at(pts, u: float) -> tuple[float, float]:
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(seg) or 1
    d = clamp(u) * total
    for i, s in enumerate(seg):
        if d <= s or i == len(seg) - 1:
            f = d / s if s else 0
            return (lerp(pts[i][0], pts[i + 1][0], f), lerp(pts[i][1], pts[i + 1][1], f))
        d -= s
    return pts[-1]


def poly_at(pts, u: float) -> tuple[float, float]:
    return _poly_at(pts, u)


def poly_len(pts) -> float:
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def poly_angle(pts, u: float) -> float:
    a, b = _poly_at(pts, max(0.0, u - 0.01)), _poly_at(pts, min(1.0, u + 0.01))
    return math.atan2(b[1] - a[1], b[0] - a[0])


def bezier(p0, p1, curve: float, n: int = 24) -> list[tuple[float, float]]:
    if not curve:
        return [tuple(p0), tuple(p1)]
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    cx, cy = mx - dy * curve * 0.5, my + dx * curve * 0.5
    out = []
    for i in range(n + 1):
        f = i / n
        u = 1 - f
        out.append((u * u * p0[0] + 2 * u * f * cx + f * f * p1[0], u * u * p0[1] + 2 * u * f * cy + f * f * p1[1]))
    return out


def sagged(p0, p1, sag: float, n: int = 20) -> list[tuple[float, float]]:
    out = []
    for i in range(n + 1):
        f = i / n
        out.append((lerp(p0[0], p1[0], f), lerp(p0[1], p1[1], f) + 4 * sag * f * (1 - f)))
    return out


# ---- the scene -----------------------------------------------------------------------------------
class SceneModel:
    def __init__(self, scene: dict, style: dict | None = None, base: list[dict] | None = None,
                 camera0: list | None = None, spin: float | None = None):
        self.scene = scene
        self.style = style or {}
        self.pace = MOTION.get(self.style.get("motion", "measured"), 1.0)
        specs: dict[str, dict] = {}
        for a in base or []:
            specs[a["id"]] = deepcopy(a)
        for a in scene.get("actors", []):
            if a["id"] in specs:
                merged = {**specs[a["id"]], **{k: v for k, v in a.items() if k != "params"}}
                merged["params"] = {**(specs[a["id"]].get("params") or {}), **(a.get("params") or {})}
                if a.get("kind") != specs[a["id"]].get("kind"):
                    merged.pop("_carry", None)
                specs[a["id"]] = merged
            else:
                specs[a["id"]] = deepcopy(a)
        self.actors = {aid: Actor(s, i) for i, (aid, s) in enumerate(specs.items())}
        start = tuple(scene.get("camera") or camera0 or FULL)
        self.cam = [Track(float(v)) for v in start]
        self.cam_moves: list[tuple[float, float]] = []
        self._build(scene.get("beats", []))
        self.spin = spin if spin is not None else spin_budget([scene])
        self.view: tuple[float, float, float, float] | None = None  # visible world rect above the captions
        self.screen: tuple[float, float, float, float] | None = None  # whole visible world rect

    # ---- beats -----------------------------------------------------------------------------------
    def _dur(self, b: dict) -> float:
        if b.get("dur") is not None:
            return float(b["dur"])
        return DEFAULT_DUR.get(b["do"], 1.0) * self.pace

    def _build(self, beats: list[dict]) -> None:
        ordered = sorted(enumerate(beats), key=lambda ib: (float(ib[1].get("at", 0) or 0), ib[0]))
        for _, b in ordered:
            t = float(b.get("at", 0) or 0)
            do = b["do"]
            dur = self._dur(b)
            e = b.get("ease") or ("out" if do in ("move", "camera") else "smooth")
            targets = b.get("target")
            targets = [targets] if isinstance(targets, str) else list(targets or [])
            if do == "camera":
                region = b.get("region") or self.frame_targets(targets, t)
                if region:
                    for tr, v in zip(self.cam, region):
                        tr.add(t, dur, float(v), b.get("ease") or "smooth")
                    self.cam_moves.append((t, t + dur))
                continue
            for ref in targets:
                aid, _, sub = ref.partition(".")
                a = self.actors.get(aid)
                if a is None:
                    continue
                if do == "enter":
                    a.events.append((t, dur, "enter", b.get("anim") or "fade"))
                elif do == "exit":
                    a.events.append((t, dur, "exit", b.get("anim") or "fade"))
                elif do == "set" and "param" in b:
                    if sub and a.kind == "network":
                        a.sub_track(sub, b["param"]).add(t, dur, b.get("to"), e)
                    else:
                        a.track(b["param"]).add(t, dur, b.get("to"), e)
                elif do == "move" and isinstance(b.get("to"), list):
                    start = a.position(t)
                    a.moves.append((t, t + dur, start, tuple(b["to"]), float(b.get("curve") or 0), e))
                    a.moves.sort(key=lambda m: m[0])
                elif do == "pulse":
                    a.pulses.append((t, dur, int(b.get("repeat") or 1), b.get("color")))
                elif do == "trace":
                    a.traces.append((t, dur, b.get("color"), sub))
        for a in self.actors.values():
            a.events.sort(key=lambda ev: ev[0])

    # ---- geometry --------------------------------------------------------------------------------
    def to_world(self, a: Actor, local: tuple[float, float], t: float) -> tuple[float, float]:
        x, y = a.position(t)
        s = float(a.value("scale", t) or 1.0)
        r = math.radians(float(a.value("rotate", t) or 0.0))
        lx, ly = local[0] * s, local[1] * s
        if r:
            lx, ly = lx * math.cos(r) - ly * math.sin(r), lx * math.sin(r) + ly * math.cos(r)
        return (x + lx, y + ly)

    def network_point(self, a: Actor, node: dict, t: float) -> tuple[float, float]:
        p = node.get("at") or [0, 0]
        rel = network_relative(a.params0, bool(a.spec.get("at")))
        return self.to_world(a, (p[0], p[1]) if rel else (p[0] - a.at0[0], p[1] - a.at0[1]), t)

    def nodes(self, a: Actor) -> dict[str, dict]:
        return {n["id"]: n for n in a.params0.get("nodes") or [] if isinstance(n, dict) and n.get("id")}

    def point(self, ref, t: float, role: str = "center", toward=None) -> tuple[float, float]:
        """World point for a reference: [x, y], 'id', 'id.anchor', 'net.node' or 'net.a-b'."""
        if isinstance(ref, (list, tuple)):
            return (float(ref[0]), float(ref[1]))
        aid, _, sub = str(ref).partition(".")
        a = self.actors.get(aid)
        if a is None:
            return (DESIGN_W / 2, DESIGN_H / 2)
        prm = a.params(t)
        if a.kind == "network" and sub:
            nodes = self.nodes(a)
            if sub in nodes:
                return self.network_point(a, nodes[sub], t)
            fr, _, to = sub.partition("-")
            if fr in nodes and to in nodes:
                p, q = self.network_point(a, nodes[fr], t), self.network_point(a, nodes[to], t)
                return ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        if sub:
            loc = local_anchor(a, prm, sub)
            if loc is not None:
                return self.to_world(a, loc, t)
        if a.kind in REF_KINDS or (a.kind in POINT_KINDS and role in ("from", "to")):
            pts = self.polyline(a, t)
            if pts:
                return pts[0] if role == "from" else pts[-1] if role == "to" else _poly_at(pts, 0.5)
        if role in ("from", "to"):
            named = {"from": ("out", "top_wire", "right"), "to": ("in", "top_wire", "left")}[role]
            if a.kind in ("plant", "generator", "transformer", "substation", "breaker", "battery", "house",
                          "factory", "city", "tower", "pole"):
                for nm in named:
                    if nm in KINDS[a.kind].anchors and nm not in ("right", "left"):
                        if a.kind == "tower" and nm == "top_wire":
                            nm = "arm_right" if role == "from" else "arm_left"
                        loc = local_anchor(a, prm, nm)
                        if loc is not None:
                            return self.to_world(a, loc, t)
            if toward is not None:
                return self.edge_point(a, prm, t, toward)
        return self.to_world(a, local_anchor(a, prm, "center") or (0, 0), t)

    def edge_point(self, a: Actor, prm: dict, t: float, toward) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bounds(a, t, prm)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = toward[0] - cx, toward[1] - cy
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return (cx, cy)
        hw, hh = max(1.0, (x1 - x0) / 2 + 10), max(1.0, (y1 - y0) / 2 + 10)
        f = min(hw / abs(dx) if dx else 1e9, hh / abs(dy) if dy else 1e9)
        return (cx + dx * min(f, 1.0), cy + dy * min(f, 1.0))

    def bounds(self, a: Actor, t: float, prm: dict | None = None) -> tuple[float, float, float, float]:
        prm = prm if prm is not None else a.params(t)
        if a.kind in REF_KINDS:
            pts = self.polyline(a, t) or [a.position(t)]
            if a.kind == "field":
                c = self.point(prm.get("around"), t)
                r = float(prm.get("radius", 160)) * float(a.value("scale", t) or 1)
                return (c[0] - r, c[1] - r, c[0] + r, c[1] + r)
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            return (min(xs), min(ys), max(xs), max(ys))
        if a.kind == "label":
            x, y = self.label_center(a, t, prm)
            x0, y0, x1, y1 = local_box(a, prm)
            return (x + x0, y + y0, x + x1, y + y1)
        x0, y0, x1, y1 = local_box(a, prm)
        corners = [self.to_world(a, c, t) for c in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
        xs, ys = [c[0] for c in corners], [c[1] for c in corners]
        return (min(xs), min(ys), max(xs), max(ys))

    def label_center(self, a: Actor, t: float, prm: dict) -> tuple[float, float]:
        if a.spec.get("at") or a.moves:
            return a.position(t)
        target = prm.get("target")
        tid = str(target).partition(".")[0] if isinstance(target, str) else None
        ta = self.actors.get(tid) if tid else None
        if ta is None or "." in str(target):
            p = self.point(target, t)
            side = prm.get("side", "auto")
            off = {"top": (0, -56), "bottom": (0, 56), "left": (-120, 0), "right": (120, 0)}
            return (p[0] + off.get(side, off["top"])[0], p[1] + off.get(side, off["top"])[1])
        x0, y0, x1, y1 = self.bounds(ta, t)
        w = local_box(a, prm)[2]
        side = prm.get("side", "auto")
        if side == "auto":
            side = "top" if y0 > 110 else ("bottom" if y1 < 700 else "right")
        gap = 46
        return {"top": ((x0 + x1) / 2, y0 - gap), "bottom": ((x0 + x1) / 2, y1 + gap),
                "left": (x0 - gap - w, (y0 + y1) / 2), "right": (x1 + gap + w, (y0 + y1) / 2)}[side]

    def edge_fade(self, x0: float, y0: float, x1: float, y1: float) -> float:
        """Opacity for a label by how much of it is on screen: a sliver at the frame edge is hidden, and a
        camera pan fades it in as it arrives."""
        if self.screen is None or x1 <= x0 or y1 <= y0:
            return 1.0
        sx0, sy0, sx1, sy1 = self.screen
        ix = max(0.0, min(x1, sx1) - max(x0, sx0))
        iy = max(0.0, min(y1, sy1) - max(y0, sy0))
        return clamp((ix * iy / ((x1 - x0) * (y1 - y0)) - 0.3) / 0.5)

    def fit_view(self, cx: float, cy: float, w: float, h: float, pad: float = 14.0,
                 anchor: tuple[float, float] | None = None) -> tuple[float, float]:
        """Slide a w×h box centred on (cx, cy) inside the visible area when it, or the point it labels, is on
        screen; anything else stays put, so a camera pan doesn't drag far-away labels along the frame edge."""
        if self.view is None:
            return cx, cy
        vx0, vy0, vx1, vy1 = self.view
        sx0, sy0, sx1, sy1 = self.screen or self.view

        def inside(p):
            return p is not None and sx0 <= p[0] <= sx1 and sy0 <= p[1] <= sy1
        if not (inside((cx, cy)) or inside(anchor)):
            return cx, cy
        if w + 2 * pad <= vx1 - vx0:
            cx = clamp(cx, vx0 + pad + w / 2, vx1 - pad - w / 2)
        if h + 2 * pad <= vy1 - vy0:
            cy = clamp(cy, vy0 + pad + h / 2, vy1 - pad - h / 2)
        return cx, cy

    def polyline(self, a: Actor, t: float, prm: dict | None = None) -> list[tuple[float, float]]:
        """World-space centre line of a line-like actor (what flows, traces and arrows follow)."""
        prm = prm if prm is not None else a.params(t)
        k = a.kind
        if k in POINT_KINDS and prm.get("points"):
            pts = [self.to_world(a, (p[0] - a.at0[0], p[1] - a.at0[1]), t) for p in prm["points"]]
            if k == "cable":
                return _cable_curve(pts, float(prm.get("tension", 0.5)))
            return _smooth(pts, bool(prm.get("smooth")), bool(prm.get("closed")))
        if k == "arrow":
            p1 = self.point(prm.get("to"), t, "to", toward=self.point(prm.get("from"), t))
            p0 = self.point(prm.get("from"), t, "from", toward=p1)
            return bezier(p0, p1, float(prm.get("curve") or 0))
        if k == "powerline":
            p0, p1 = self.point(prm.get("from"), t, "from"), self.point(prm.get("to"), t, "to")
            return self.powerline_curve(prm, p0, p1)
        if k in ("dimension", "spring"):
            p0, p1 = self.point(prm.get("from"), t, "from"), self.point(prm.get("to"), t, "to")
            return [p0, p1]
        if k == "flow":
            return self.along(prm.get("along"), t)
        if k == "chain":
            return self.chain_loop(prm, t)
        return []

    def powerline_curve(self, prm: dict, p0, p1) -> list[tuple[float, float]]:
        n = int(prm.get("supports") or 0)
        sag = float(prm.get("sag", 30))
        knots = [(lerp(p0[0], p1[0], i / (n + 1)), lerp(p0[1], p1[1], i / (n + 1))) for i in range(n + 2)]
        pts: list[tuple[float, float]] = []
        for i in range(len(knots) - 1):
            seg = sagged(knots[i], knots[i + 1], sag, 14)
            pts += seg if not pts else seg[1:]
        return pts

    def along(self, ref, t: float) -> list[tuple[float, float]]:
        if isinstance(ref, list):
            return [tuple(p) for p in ref] if ref and isinstance(ref[0], list) else []
        aid, _, sub = str(ref or "").partition(".")
        a = self.actors.get(aid)
        if a is None:
            return []
        if a.kind == "network" and sub:
            nodes = self.nodes(a)
            fr, _, to = sub.partition("-")
            if fr in nodes and to in nodes:
                return [self.network_point(a, nodes[fr], t), self.network_point(a, nodes[to], t)]
            return []
        return self.polyline(a, t)

    def chain_loop(self, prm: dict, t: float) -> list[tuple[float, float]]:
        circles = []
        for ref in prm.get("around") or []:
            aid = str(ref).partition(".")[0] if isinstance(ref, str) else None
            g = self.actors.get(aid) if aid else None
            c = self.point(ref, t)
            r = 10.0
            if g is not None and g.kind in ("gear", "rotor"):
                r = float(g.value("radius", t) or 40) * float(g.value("scale", t) or 1) * 1.04
            circles.append((c[0], c[1], r))
        return belt(circles)

    def frame_targets(self, targets: list[str], t: float):
        boxes = []
        for ref in targets:
            a = self.actors.get(str(ref).partition(".")[0])
            if a is not None:
                boxes.append(self.bounds(a, t))
        if not boxes:
            return None
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        w, h = max(x1 - x0, 1) * 1.35, max(y1 - y0, 1) * 1.35
        w, h = max(w, h * 16 / 9, 420), max(h, w * 9 / 16, 236)
        w, h = max(w, h * 16 / 9), max(h, w * 9 / 16)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return [cx - w / 2, cy - h / 2, w, h]

    def camera(self, t: float) -> tuple[float, float, float, float]:
        return tuple(tr.value(t) for tr in self.cam)

    # ---- carry-over ------------------------------------------------------------------------------
    def final_state(self, t: float) -> list[dict]:
        """Actor specs describing the state at time t, for a later scene that inherits this one."""
        out = []
        for a in sorted(self.actors.values(), key=lambda x: x.order):
            spec = {k: v for k, v in a.spec.items() if k not in ("params", "_carry", "visible")}
            spec["at"] = [round(v, 2) for v in a.position(t)]
            for k in ("scale", "rotate", "opacity"):
                spec[k] = round(float(a.value(k, t)), 4)
            pres = a.presence(t)
            spec["visible"] = pres.alpha > 0.5
            prm = a.params(t)
            if a.kind == "network":
                nodes = [dict(n) for n in prm.get("nodes") or []]
                edges = [dict(e) for e in prm.get("edges") or []]
                for n in nodes:
                    n["state"] = a.sub_value(n.get("id"), "state", t)
                for e in edges:
                    part = f"{e.get('from')}-{e.get('to')}"
                    e["state"] = a.sub_value(part, "state", t)
                    e["flow"] = a.sub_value(part, "flow", t)
                prm["nodes"], prm["edges"] = nodes, edges
            spec["params"] = {k: v for k, v in prm.items() if k in KINDS[a.kind].params or k == "fill_level"}
            carry = {p: round(a.phase(p, t), 4) for p in PHASED.get(a.kind, ())}
            if a.kind == "network":
                for e in prm.get("edges") or []:
                    part = f"{e.get('from')}-{e.get('to')}"
                    carry[f"{part}.flow"] = round(a.sub_phase(part, t), 4)
            spec["_carry"] = carry
            out.append(spec)
        return out

    def last_change(self) -> float:
        ends = [0.0]
        for a in self.actors.values():
            ends += [ev[0] + ev[1] for ev in a.events]
            ends += [m[1] for m in a.moves]
            ends += [t0 + d * r for t0, d, r, _ in a.pulses]
            ends += [t0 + d for t0, d, _, _ in a.traces]
            for k, tr in a.tracks.items():
                ends += [s[1] for s in tr.segs]
        ends += [m[1] for m in self.cam_moves]
        return max(ends)


SPIN_KINDS = ("rotor", "gear", "generator")
MAX_VISUAL_RPM = 75.0


def spin_budget(scenes: list[dict]) -> float:
    """One factor for every rotor in the lesson so the fastest turns ~1.25 rev/s: fast enough to read as
    spinning, slow enough not to strobe at 30 fps, and speed changes keep their true proportions."""
    top = 0.0
    for sc in scenes:
        for a in sc.get("actors", []):
            if a.get("kind") in SPIN_KINDS:
                top = max(top, abs(float((a.get("params") or {}).get("rpm") or 0)))
        for b in sc.get("beats", []):
            if b.get("do") == "set" and b.get("param") == "rpm" and _num(b.get("to")):
                top = max(top, abs(float(b["to"])))
    return min(1.0, MAX_VISUAL_RPM / top) if top > 0 else 1.0


def _smooth(pts, smooth: bool, closed: bool) -> list[tuple[float, float]]:
    pts = [tuple(p) for p in pts]
    if closed:
        pts = pts + [pts[0]]
    if not smooth or len(pts) < 3:
        return pts
    out = []
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[i - 1] if i > 0 else (pts[-2] if closed else pts[i])
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < n else (pts[1] if closed else p2)
        for k in range(10):
            f = k / 10
            f2, f3 = f * f, f * f * f
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * f + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * f2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * f3) for j in (0, 1)))
    out.append(pts[-1])
    return out


def _cable_curve(pts, tension: float) -> list[tuple[float, float]]:
    sag = (1 - clamp(tension)) * 40
    out: list[tuple[float, float]] = []
    for i in range(len(pts) - 1):
        seg = sagged(pts[i], pts[i + 1], sag * min(1.0, math.dist(pts[i], pts[i + 1]) / 300), 12)
        out += seg if not out else seg[1:]
    return out


def belt(circles: list[tuple[float, float, float]]) -> list[tuple[float, float]]:
    """Closed loop wrapped around circles (in the given order), as a polyline."""
    if len(circles) < 2:
        return []
    cx = sum(c[0] for c in circles) / len(circles)
    cy = sum(c[1] for c in circles) / len(circles)
    ordered = sorted(circles, key=lambda c: math.atan2(c[1] - cy, c[0] - cx))
    n = len(ordered)
    tangents = []
    for i in range(n):
        (x1, y1, r1), (x2, y2, r2) = ordered[i], ordered[(i + 1) % n]
        d = math.dist((x1, y1), (x2, y2)) or 1e-6
        base = math.atan2(y2 - y1, x2 - x1)
        off = math.acos(clamp((r1 - r2) / d, -1, 1))
        ang = base - off
        tangents.append(((x1 + r1 * math.cos(ang), y1 + r1 * math.sin(ang)),
                         (x2 + r2 * math.cos(ang), y2 + r2 * math.sin(ang)), ang))
    pts: list[tuple[float, float]] = []
    for i in range(n):
        a_in = tangents[i - 1][2]
        a_out = tangents[i][2]
        x, y, r = ordered[i]
        while a_out < a_in:
            a_out += 2 * math.pi
        steps = max(2, int((a_out - a_in) / 0.2))
        for k in range(steps + 1):
            a = a_in + (a_out - a_in) * k / steps
            pts.append((x + r * math.cos(a), y + r * math.sin(a)))
        pts.append(tangents[i][1])
    pts.append(pts[0])
    return pts
