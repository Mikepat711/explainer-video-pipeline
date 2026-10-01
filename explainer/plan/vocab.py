"""The visual vocabulary a lesson plan is written in.

One catalog serves three purposes: it is rendered into the writer prompt (`describe()`),
it drives semantic validation of plans (`plan.checks`), and it is the contract the
animation engine implements. Coordinates live in a 1600x900 design space (origin top
left, y down); the renderer maps it to 16:9 or crops it for 9:16.
"""
from __future__ import annotations

from dataclasses import dataclass

DESIGN_W, DESIGN_H = 1600, 900
CAPTION_TOP = 760

COLOR_ROLES = ("bg", "surface", "ink", "muted", "accent", "accent2", "accent3", "warn", "good", "hot", "cold")
ICONS = ("satellite", "signal", "clock", "flame", "snowflake", "bolt", "house", "phone", "drop", "cloud", "fan", "sun",
         "thermometer", "gauge", "gear", "chip", "globe", "pin", "spark", "compressor", "coil", "valve", "layers",
         "antenna", "building", "check", "atom", "kettle", "plug")
BOX_ANCHORS = ("center", "top", "bottom", "left", "right")


def p(kind: str, doc: str = "", **kw) -> dict:
    return {"type": kind, "doc": doc, **kw}


@dataclass
class Kind:
    doc: str
    params: dict
    animatable: tuple = ()
    anchors: tuple = BOX_ANCHORS
    required: tuple = ()
    group: str = ""
    sub_targets: str = ""


COLOR = p("color", "palette role or #RRGGBB")
STATE = ("normal", "off", "highlight", "overload", "failed")

KINDS: dict[str, Kind] = {
    # --- words and annotation -------------------------------------------------------------
    "text": Kind("A short on-screen statement or title. Use sparingly; the narration carries the words.", {
        "text": p("text", max_words=10), "size": p("enum", values=("xs", "s", "m", "l", "xl", "xxl")),
        "weight": p("enum", values=("regular", "medium", "bold")), "align": p("enum", values=("left", "center", "right")),
        "color": COLOR, "max_width": p("num", min=60, max=1600)}, ("text",), required=("text",), group="words"),
    "label": Kind("A name tag pointing at a part, with an optional leader line.", {
        "text": p("text", max_words=6), "target": p("ref"), "side": p("enum", values=("top", "bottom", "left", "right", "auto")),
        "leader": p("bool"), "color": COLOR}, ("text",), required=("text", "target"), group="words"),
    "badge": Kind("A round step number or short symbol (1, 2, A, !, kW).", {
        "text": p("str", max_len=6), "color": COLOR, "size": p("num", min=16, max=120)}, required=("text",), group="words"),
    "dimension": Kind("A measurement bracket between two points with a value (e.g. '400 kV', '1,000 km').", {
        "from": p("ref"), "to": p("ref"), "text": p("text", max_words=4), "offset": p("num", min=-300, max=300),
        "color": COLOR}, ("text",), required=("from", "to", "text"), group="words"),
    # --- geometry ------------------------------------------------------------------------------
    "shape": Kind("A basic shape: panel, region, body of a part, highlight area.", {
        "shape": p("enum", values=("rect", "rounded", "circle", "ellipse", "ring", "polygon")),
        "w": p("num", min=1, max=3200), "h": p("num", min=1, max=1800), "r": p("num", min=1, max=900),
        "points": p("points", doc="polygon vertices relative to `at`"), "fill": COLOR, "stroke": COLOR,
        "stroke_width": p("num", min=0, max=40), "dashed": p("bool")},
        ("w", "h", "r", "fill_level"), required=("shape",), group="geometry"),
    "path": Kind("A drawn line or curve: wire, pipe, route, outline. Other actors can flow along it.", {
        "points": p("points", doc="absolute design-space points, at least 2"), "smooth": p("bool"), "closed": p("bool"),
        "color": COLOR, "width": p("num", min=1, max=60), "dashed": p("bool"),
        "arrow": p("enum", values=("none", "end", "start", "both"))}, ("width",),
        anchors=("start", "end", "mid"), required=("points",), group="geometry"),
    "arrow": Kind("An arrow between two actors/points (causality, direction of energy or force).", {
        "from": p("ref"), "to": p("ref"), "curve": p("num", min=-1, max=1), "color": COLOR,
        "width": p("num", min=1, max=40), "dashed": p("bool"), "text": p("text", max_words=5)},
        ("width",), anchors=("start", "end", "mid"), required=("from", "to"), group="geometry"),
    "icon": Kind("A small line icon.", {"name": p("enum", values=ICONS), "size": p("num", min=20, max=400), "color": COLOR},
                 required=("name",), group="geometry"),
    # --- motion and mechanism --------------------------------------------------------------------
    "flow": Kind("Moving particles along a path/arrow/powerline: current, fluid, heat, data, traffic. "
                 "direction 'alternate' shows AC sloshing back and forth.", {
        "along": p("ref", doc="id of a path, arrow, powerline or network edge 'net.a-b'"),
        "particles": p("int", min=1, max=120), "speed": p("num", min=0, max=1200, doc="design px per second"),
        "size": p("num", min=1, max=40), "color": COLOR, "style": p("enum", values=("dots", "dashes", "pulses", "arrows", "packets")),
        "direction": p("enum", values=("forward", "reverse", "alternate"))},
        ("speed", "particles", "size"), anchors=("start", "end"), required=("along",), group="motion"),
    "wave": Kind("A live waveform plot (AC voltage, sound, oscillation). Frequency/amplitude animate smoothly.", {
        "w": p("num", min=60, max=1600), "h": p("num", min=30, max=900),
        "waveform": p("enum", values=("sine", "square", "sawtooth", "triangle")),
        "cycles": p("num", min=0.5, max=40, doc="cycles visible across the width"),
        "amplitude": p("num", min=0, max=1), "speed": p("num", min=0, max=10, doc="scroll speed, cycles per second"),
        "phase": p("num", min=0, max=360), "color": COLOR, "axis": p("bool"), "text": p("text", max_words=4)},
        ("cycles", "amplitude", "speed", "phase"), group="motion"),
    "rotor": Kind("A spinning part: generator magnet, turbine, fan, wheel, propeller.", {
        "radius": p("num", min=10, max=450), "style": p("enum", values=("magnet", "turbine", "fan", "wheel", "propeller")),
        "poles": p("int", min=2, max=24), "rpm": p("num", min=0, max=600, doc="visual speed, not real rpm"),
        "color": COLOR}, ("rpm", "radius"), required=("radius",), group="motion"),
    "coil": Kind("A wire coil (electromagnet, transformer winding, inductor). `current` makes the winding glow "
                 "and its sign shows direction.", {
        "turns": p("int", min=1, max=60), "length": p("num", min=20, max=900), "radius": p("num", min=5, max=300),
        "orientation": p("enum", values=("horizontal", "vertical")), "current": p("num", min=-1, max=1),
        "color": COLOR, "text": p("text", max_words=4)},
        ("current", "turns"), anchors=BOX_ANCHORS + ("lead_in", "lead_out"), required=("turns",), group="motion"),
    "field": Kind("Field lines around something (magnetic loops, radial heat/light, electric field).", {
        "around": p("ref"), "radius": p("num", min=20, max=900), "lines": p("int", min=2, max=24),
        "style": p("enum", values=("magnetic", "radial", "heat", "electric")), "strength": p("num", min=0, max=1),
        "color": COLOR}, ("strength", "radius"), required=("around",), group="motion"),
    "gear": Kind("A toothed gear or sprocket; meshing gears are timed by their rpm.", {
        "teeth": p("int", min=6, max=80), "radius": p("num", min=10, max=450), "rpm": p("num", min=-300, max=300),
        "color": COLOR, "spokes": p("int", min=0, max=12)}, ("rpm", "radius"),
        required=("teeth", "radius"), group="mechanical"),
    "chain": Kind("A chain or belt wrapped around gears/pulleys, links moving at `speed`.", {
        "around": p("list", item="ref", min_items=2, max_items=8), "speed": p("num", min=-600, max=600), "color": COLOR},
        ("speed",), required=("around",), group="mechanical"),
    "spring": Kind("A coil spring between two points; `compression` squeezes it.", {
        "from": p("ref"), "to": p("ref"), "coils": p("int", min=3, max=40), "compression": p("num", min=0, max=0.9),
        "color": COLOR}, ("compression",), required=("from", "to"), group="mechanical"),
    "lever": Kind("A rigid arm on a pivot; `angle` rotates it (linkages, cages, switches).", {
        "length": p("num", min=10, max=1200), "angle": p("num", min=-360, max=360), "width": p("num", min=2, max=80),
        "color": COLOR}, ("angle", "length"), anchors=("pivot", "tip", "center"), required=("length",), group="mechanical"),
    "cable": Kind("A cable/rope/bowden wire through points; `tension` tightens and highlights it.", {
        "points": p("points"), "tension": p("num", min=0, max=1), "color": COLOR, "width": p("num", min=1, max=30)},
        ("tension",), anchors=("start", "end", "mid"), required=("points",), group="mechanical"),
    # --- data and instruments ------------------------------------------------------------------
    "gauge": Kind("A needle dial or arc gauge. Animate `value` to make the needle move (e.g. grid frequency).", {
        "min": p("num"), "max": p("num"), "value": p("num"), "unit": p("str", max_len=8), "text": p("text", max_words=4),
        "decimals": p("int", min=0, max=3), "radius": p("num", min=40, max=400),
        "zones": p("list", item={"from": p("num"), "to": p("num"), "color": COLOR}, max_items=6),
        "style": p("enum", values=("dial", "arc", "vertical"))}, ("value",), required=("min", "max", "value"), group="data"),
    "meter": Kind("A digital readout (volts, amps, MW, %). Animate `value` to count up/down.", {
        "value": p("num"), "unit": p("str", max_len=8), "text": p("text", max_words=4), "decimals": p("int", min=0, max=3),
        "color": COLOR, "size": p("enum", values=("s", "m", "l", "xl"))}, ("value",), required=("value",), group="data"),
    "bars": Kind("A bar chart. Animate `values` (same length) to grow/shrink bars.", {
        "labels": p("list", item="text", max_items=10), "values": p("list", item="num", max_items=10),
        "max": p("num"), "unit": p("str", max_len=8), "w": p("num", min=100, max=1600), "h": p("num", min=60, max=800),
        "orientation": p("enum", values=("vertical", "horizontal")), "colors": p("list", item="color", max_items=10)},
        ("values",), required=("labels", "values"), group="data"),
    "line_chart": Kind("A chart of one or more series over time. `progress` 0-1 draws it left to right like a live "
                       "trace; a marker rides the leading edge.", {
        "w": p("num", min=120, max=1600), "h": p("num", min=80, max=800), "x_label": p("text", max_words=4),
        "y_label": p("text", max_words=4),
        "series": p("list", item={"name": p("text", max_words=3), "values": p("list", item="num", min_items=2,
                                                                                  max_items=200), "color": COLOR},
                    min_items=1, max_items=4),
        "y_min": p("num"), "y_max": p("num"), "x_ticks": p("list", item="text", max_items=12), "progress": p("num", min=0, max=1)},
        ("progress",), required=("series",), group="data"),
    "balance": Kind("A see-saw scale comparing two quantities; it tilts toward the heavier side.", {
        "left_text": p("text", max_words=3), "right_text": p("text", max_words=3), "left": p("num", min=0),
        "right": p("num", min=0), "width": p("num", min=120, max=1200), "color": COLOR},
        ("left", "right"), anchors=BOX_ANCHORS + ("left_pan", "right_pan"), required=("left", "right"), group="data"),
    "network": Kind("A schematic map: nodes at positions joined by edges (grids, pipelines, networks, routes). "
                    "Address parts as 'net.node' or 'net.a-b' for an edge; animate each part's `state` and edge `flow`.", {
        "nodes": p("list", min_items=2, max_items=40, item={
            "id": p("str", max_len=24), "at": p("point"), "text": p("text", max_words=3),
            "kind": p("enum", values=("generic", "plant", "substation", "city", "house", "factory", "battery", "hub",
                                       "switch", "load")),
            "state": p("enum", values=STATE)}),
        "edges": p("list", max_items=80, item={
            "from": p("str"), "to": p("str"), "class": p("enum", values=("hv", "mv", "lv", "link", "pipe")),
            "flow": p("num", min=-1, max=1), "state": p("enum", values=STATE)})},
        ("state", "flow"), required=("nodes", "edges"), group="data", sub_targets="nodes/edges"),
    "compare": Kind("Two side-by-side columns (before/after, AC vs DC, low vs high voltage).", {
        "left_title": p("text", max_words=4), "right_title": p("text", max_words=4),
        "left_items": p("list", item="text", max_items=4), "right_items": p("list", item="text", max_items=4),
        "w": p("num", min=300, max=1600)}, (), required=("left_title", "right_title"), group="data"),
    # --- electrical grid kit -------------------------------------------------------------------
    "plant": Kind("A power station drawn by type; `output` 0-1 drives its animation (smoke, spinning blades, "
                  "falling water, glowing panels).", {
        "type": p("enum", values=("gas", "coal", "nuclear", "hydro", "wind", "solar", "battery", "geothermal")),
        "output": p("num", min=0, max=1), "size": p("num", min=40, max=600), "text": p("text", max_words=3)},
        ("output",), anchors=BOX_ANCHORS + ("out",), required=("type",), group="grid"),
    "generator": Kind("Generator cutaway: a magnet rotor spinning inside stator coils; optional live sine output.", {
        "rpm": p("num", min=0, max=600), "poles": p("int", min=2, max=12), "size": p("num", min=80, max=700),
        "show_wave": p("bool"), "text": p("text", max_words=3)},
        ("rpm",), anchors=BOX_ANCHORS + ("out",), group="grid"),
    "transformer": Kind("Transformer. 'cutaway' shows an iron core with two windings and flux circulating; the turns "
                        "ratio sets the drawn coils, and the meters show voltage in and out.", {
        "style": p("enum", values=("cutaway", "substation", "pole_can", "symbol")),
        "primary_turns": p("int", min=1, max=60), "secondary_turns": p("int", min=1, max=60),
        "v_in": p("str", max_len=12), "v_out": p("str", max_len=12), "flux": p("num", min=0, max=1),
        "size": p("num", min=60, max=800), "show_meters": p("bool")},
        ("flux",), anchors=BOX_ANCHORS + ("in", "out"), required=("style",), group="grid"),
    "tower": Kind("A lattice transmission tower with insulator strings.", {
        "height": p("num", min=60, max=800), "circuits": p("int", min=1, max=2), "color": COLOR},
        (), anchors=BOX_ANCHORS + ("arm_left", "arm_right", "top_wire"), group="grid"),
    "powerline": Kind("Conductors between two points with sag, optional towers/poles in between. `flow` 0-1 sets the "
                      "speed of the moving current; `heat` 0-1 makes the wire glow (resistive loss).", {
        "from": p("ref"), "to": p("ref"), "voltage": p("enum", values=("hv", "mv", "lv")),
        "supports": p("int", min=0, max=12), "sag": p("num", min=0, max=120), "flow": p("num", min=0, max=1),
        "heat": p("num", min=0, max=1), "text": p("text", max_words=4)},
        ("flow", "heat"), anchors=("start", "end", "mid"), required=("from", "to"), group="grid"),
    "substation": Kind("A fenced substation yard: busbars, breakers and a transformer; `state` animates trips.", {
        "size": p("num", min=80, max=800), "breakers": p("int", min=1, max=6), "state": p("enum", values=STATE),
        "text": p("text", max_words=3)}, ("state",), anchors=BOX_ANCHORS + ("in", "out"), group="grid"),
    "pole": Kind("A wooden distribution pole, optionally with a can transformer.", {
        "height": p("num", min=60, max=600), "transformer": p("bool"), "color": COLOR},
        (), anchors=BOX_ANCHORS + ("top_wire", "drop"), group="grid"),
    "house": Kind("A house (or apartment block); `lights` 0-1 lights the windows, `load` adds visible appliances.", {
        "style": p("enum", values=("house", "apartment", "shop")), "lights": p("num", min=0, max=1),
        "load": p("num", min=0, max=1), "size": p("num", min=30, max=500)},
        ("lights", "load"), anchors=BOX_ANCHORS + ("in",), group="grid"),
    "city": Kind("A skyline block; `lights` 0-1 sets how many windows are lit (demand, blackouts).", {
        "buildings": p("int", min=3, max=40), "w": p("num", min=100, max=1600), "h": p("num", min=60, max=700),
        "lights": p("num", min=0, max=1)}, ("lights",), anchors=BOX_ANCHORS + ("in",), group="grid"),
    "factory": Kind("An industrial load; `load` 0-1 drives machinery motion and chimney activity.", {
        "load": p("num", min=0, max=1), "size": p("num", min=40, max=600)},
        ("load",), anchors=BOX_ANCHORS + ("in",), group="grid"),
    "breaker": Kind("A circuit breaker/switch; set `state` to 'open' to trip it with an arc flash.", {
        "state": p("enum", values=("closed", "open")), "size": p("num", min=20, max=300), "text": p("text", max_words=3)},
        ("state",), anchors=BOX_ANCHORS + ("in", "out"), group="grid"),
    "battery": Kind("A battery bank; `charge` 0-1 fills it, `flow` -1..1 shows charging or discharging.", {
        "charge": p("num", min=0, max=1), "flow": p("num", min=-1, max=1), "size": p("num", min=30, max=500)},
        ("charge", "flow"), anchors=BOX_ANCHORS + ("in", "out"), group="grid"),
}

COMMON_ANIMATABLE = ("opacity", "scale", "rotate")
ACTIONS = {
    "enter": "reveal targets; anim: fade|draw|pop|grow|slide_up|slide_down|slide_left|slide_right|wipe|build",
    "exit": "remove targets; anim: fade|shrink|slide_up|slide_down|slide_left|slide_right",
    "set": "animate one parameter of a target to `to` over `dur` (numbers tween; enums/text switch at the end)",
    "move": "move a target to point `to` (optionally along a gentle arc with `curve`)",
    "pulse": "briefly emphasise targets with a glow/scale pulse (`repeat` times)",
    "trace": "send a single bright pulse along a path, arrow, powerline or network edge",
    "camera": "glide the view to a region [x, y, w, h] or to frame a target actor",
}
ENTER_ANIMS = ("fade", "draw", "pop", "grow", "slide_up", "slide_down", "slide_left", "slide_right", "wipe", "build")
EXIT_ANIMS = ("fade", "shrink", "slide_up", "slide_down", "slide_left", "slide_right")
EASES = ("linear", "smooth", "out", "in", "spring", "step")
MECHANISM_ACTIONS = ("set", "move", "trace", "camera")

STYLE_BACKGROUNDS = ("solid", "gradient", "blueprint", "dots", "paper", "night")
TYPEFACES = ("geometric", "humanist", "rounded", "mono", "serif")
TRANSITIONS = ("cut", "fade", "slide_left", "slide_up", "zoom_in", "zoom_out", "continue")


def _fmt_param(name: str, spec) -> str:
    """name:type with every limit the validator enforces (enums are exhaustive, ≤N is a hard cap)."""
    spec = {"type": spec} if isinstance(spec, str) else spec
    t = spec["type"]
    if t == "enum":
        s = "|".join(spec["values"])
    elif t == "list":
        item = spec.get("item")
        n = [str(spec[k]) for k in ("min_items", "max_items") if k in spec]
        count = f" ({'..'.join(n)} items)" if len(n) == 2 else (f" (≤{spec['max_items']} items)" if "max_items" in spec else "")
        if isinstance(item, dict):
            s = "list of {" + ", ".join(_fmt_param(k, v) for k, v in item.items()) + "}" + count
        else:
            s = f"list of {_fmt_param('', item)[1:]}{count}"
    elif t in ("num", "int"):
        rng = [str(spec[k]) for k in ("min", "max") if k in spec]
        s = t + (f" {'..'.join(rng)}" if len(rng) == 2 else (f" ≥{spec['min']}" if "min" in spec else ""))
    elif t == "text":
        s = f"text≤{spec.get('max_words', 6)}w"
    elif t == "str":
        s = f"str≤{spec['max_len']}ch" if "max_len" in spec else "str"
    else:
        s = t
    return f"{name}:{s}"


def describe() -> str:
    """Compact vocabulary reference for the writer prompt."""
    lines = []
    group = None
    for name, k in KINDS.items():
        if k.group != group:
            group = k.group
            lines.append(f"\n[{group}]")
        req = f" required: {', '.join(k.required)}." if k.required else ""
        anim = f" animatable: {', '.join(k.animatable)}." if k.animatable else ""
        anchors = f" anchors: {', '.join(k.anchors)}." if k.anchors != BOX_ANCHORS else ""
        params = "; ".join(_fmt_param(n, s) for n, s in k.params.items())
        lines.append(f"- {name}: {k.doc} params: {params}.{req}{anim}{anchors}")
    return "\n".join(lines).strip()


def is_animatable(kind: str, param: str) -> bool:
    k = KINDS.get(kind)
    return bool(k) and (param in k.animatable or param in COMMON_ANIMATABLE)
