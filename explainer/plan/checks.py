"""Semantic checks for writer output that a JSON schema cannot express."""
from __future__ import annotations

import re

from ..util import split_sentences
from .vocab import (CAPTION_TOP, COLOR_ROLES, COMMON_ANIMATABLE, ENTER_ANIMS, EXIT_ANIMS, KINDS, MECHANISM_ACTIONS,
                    is_animatable)

_TIME = re.compile(r"^\s*(?:(s|e)(\d+)|start|end)\s*([+-]\s*\d*\.?\d+)?\s*$", re.I)
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
MAX_SCENE_WORDS = 36
TEXTY = {"text", "label", "meter", "badge", "dimension", "compare"}


def script_words(script: dict) -> int:
    return sum(len(s.split()) for sc in script["scenes"] for s in sc["sentences"])


def check_research(research: dict, required: list[str] = ()) -> list[str]:
    if not required:
        return []
    got = [t.get("id") for t in research.get("required_topics") or []]
    errors = [f"required_topics: '{r}' is missing; research every required topic under its own id"
              for r in required if r not in got]
    errors += [f"required_topics: '{g}' is not one of the required ids {list(required)}" for g in got
               if g not in required]
    return errors


def _unknown_cover(cid: str, required, where: str) -> str:
    return (f"{where}.covers: '{cid}' is not a required topic id" + (f" (use {list(required)})" if required else
            " (this brief has no required topics; drop covers)"))


def script_coverage(script: dict, required: list[str] = ()) -> list[str]:
    errors, covered = [], set()
    for sc in script["scenes"]:
        for cid in sc.get("covers") or []:
            if cid in required:
                covered.add(cid)
            else:
                errors.append(_unknown_cover(cid, required, f"scenes[{sc['id']}]"))
    for r in required:
        if r not in covered:
            errors.append(f"required topic '{r}' is not taught: give it a scene (or a clearly separate part of one) "
                          f"and list '{r}' in that scene's covers")
    return errors


def check_script(script: dict, word_range: tuple[int, int], required: list[str] = ()) -> list[str]:
    errors = script_coverage(script, required)
    ids = [sc["id"] for sc in script["scenes"]]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"scene id '{dup}' is used more than once")
    for sc in script["scenes"]:
        for i, s in enumerate(sc["sentences"], 1):
            parts = split_sentences(s)
            if len(parts) != 1:
                errors.append(f"scenes[{sc['id']}].sentences[{i}] must be exactly one sentence (it splits into "
                              f"{len(parts)}); sentence boundaries are animation sync points")
            if len(s.split()) > 32:
                errors.append(f"scenes[{sc['id']}].sentences[{i}] has {len(s.split())} words; keep spoken sentences "
                              "under 30 words")
        if split_sentences(" ".join(sc["sentences"])) != [s.strip() for s in sc["sentences"]]:
            errors.append(f"scenes[{sc['id']}]: joined, the sentences re-split differently; start every sentence "
                          "with a capital letter or digit and end it with . ! or ?")
    n = script_words(script)
    lo, hi = word_range
    if not lo <= n <= hi:
        errors.append(f"the narration has {n} words; write between {lo} and {hi}")
    return errors


def _time_ok(val, n_sentences: int) -> str | None:
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return None if val >= 0 else "negative time"
    if not isinstance(val, str):
        return "time must be a number or a sentence reference"
    m = _TIME.match(val)
    if not m:
        return f"bad time {val!r}; use s1, e2, s3+0.5, start, end-1.0 or seconds"
    if m.group(2) and not 1 <= int(m.group(2)) <= n_sentences:
        return f"{val!r} refers to sentence {m.group(2)} but this scene has {n_sentences}"
    return None


class _Scene:
    def __init__(self, sid: str, actors: dict[str, dict]):
        self.sid, self.actors = sid, actors

    def network_parts(self, aid: str) -> tuple[set, set]:
        a = self.actors[aid]
        prm = a.get("params") or {}
        nodes = {n.get("id") for n in prm.get("nodes") or [] if isinstance(n, dict)}
        edges = {f"{e.get('from')}-{e.get('to')}" for e in prm.get("edges") or [] if isinstance(e, dict)}
        return nodes, edges

    def resolve(self, ref: str) -> tuple[str | None, str | None]:
        """Returns (actor_id, error)."""
        aid, _, sub = ref.partition(".")
        if aid not in self.actors:
            return None, f"'{ref}' is not an actor in this scene"
        if not sub:
            return aid, None
        kind = self.actors[aid]["kind"]
        if kind == "network":
            nodes, edges = self.network_parts(aid)
            if sub not in nodes and sub not in edges:
                return None, f"'{ref}': network '{aid}' has no node or edge '{sub}'"
            return aid, None
        if sub not in KINDS[kind].anchors:
            return None, f"'{ref}': {kind} has anchors {list(KINDS[kind].anchors)}"
        return aid, None


def _check_value(spec, v, path: str, scene: _Scene, errors: list[str]) -> int:
    """Validates one param value; returns on-screen word count it contributes."""
    t = spec if isinstance(spec, str) else spec["type"]
    spec = {} if isinstance(spec, str) else spec
    words = 0
    if t == "text":
        if not isinstance(v, str):
            errors.append(f"{path}: expected text")
        else:
            words = len(v.split())
            if words > spec.get("max_words", 6):
                errors.append(f"{path}: {words} words; keep it to {spec.get('max_words', 6)} or fewer")
    elif t == "str":
        if not isinstance(v, str):
            errors.append(f"{path}: expected a string")
        elif len(v) > spec.get("max_len", 80):
            errors.append(f"{path}: longer than {spec.get('max_len', 80)} characters")
    elif t in ("num", "int"):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or (t == "int" and not isinstance(v, int)):
            errors.append(f"{path}: expected {'an integer' if t == 'int' else 'a number'}")
        elif ("min" in spec and v < spec["min"]) or ("max" in spec and v > spec["max"]):
            errors.append(f"{path}: {v} outside {spec.get('min')}..{spec.get('max')}")
    elif t == "bool":
        if not isinstance(v, bool):
            errors.append(f"{path}: expected true/false")
    elif t == "color":
        if not (isinstance(v, str) and (v in COLOR_ROLES or _HEX.match(v))):
            errors.append(f"{path}: color must be one of {list(COLOR_ROLES)} or #RRGGBB")
    elif t == "enum":
        if v not in spec["values"]:
            errors.append(f"{path}: {v!r} not in {list(spec['values'])}")
    elif t == "point":
        if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)):
            errors.append(f"{path}: expected [x, y]")
    elif t == "points":
        if not (isinstance(v, list) and len(v) >= 2 and all(
                isinstance(q, list) and len(q) == 2 and all(isinstance(x, (int, float)) for x in q) for q in v)):
            errors.append(f"{path}: expected a list of at least two [x, y] points")
    elif t == "ref":
        if isinstance(v, list):
            _check_value("point", v, path, scene, errors)
        elif isinstance(v, str):
            _, err = scene.resolve(v)
            if err:
                errors.append(f"{path}: {err}")
        else:
            errors.append(f"{path}: expected an actor id, 'id.anchor' or [x, y]")
    elif t == "list":
        if not isinstance(v, list):
            errors.append(f"{path}: expected a list")
            return 0
        if len(v) < spec.get("min_items", 0) or len(v) > spec.get("max_items", 999):
            errors.append(f"{path}: needs {spec.get('min_items', 0)}..{spec.get('max_items', 999)} items, has {len(v)}")
        item = spec.get("item", "str")
        for i, x in enumerate(v):
            if isinstance(item, dict):
                if not isinstance(x, dict):
                    errors.append(f"{path}[{i}]: expected an object with {list(item)}")
                    continue
                for k, val in x.items():
                    if k not in item:
                        errors.append(f"{path}[{i}]: unknown field '{k}' (allowed: {list(item)})")
                    else:
                        words += _check_value(item[k], val, f"{path}[{i}].{k}", scene, errors)
            else:
                words += _check_value(item, x, f"{path}[{i}]", scene, errors)
    return words


def _check_actor(a: dict, path: str, scene: _Scene, errors: list[str]) -> int:
    kind = KINDS[a["kind"]]
    prm = a.get("params") or {}
    for req in kind.required:
        if req not in prm:
            errors.append(f"{path}: {a['kind']} needs params.{req}")
    words = 0
    for k, v in prm.items():
        if k not in kind.params:
            errors.append(f"{path}: {a['kind']} has no param '{k}' (allowed: {sorted(kind.params)})")
            continue
        words += _check_value(kind.params[k], v, f"{path}.params.{k}", scene, errors)
    at = a.get("at")
    if at and not (-400 <= at[0] <= 2000 and -400 <= at[1] <= 1300):
        errors.append(f"{path}: position {at} is far outside the 1600x900 design space")
    if at and a["kind"] in TEXTY and at[1] > CAPTION_TOP:
        errors.append(f"{path}: {a['kind']} at y={at[1]} sits in the caption band (keep y < {CAPTION_TOP})")
    if a["kind"] == "network":
        nodes = {n.get("id") for n in prm.get("nodes") or [] if isinstance(n, dict)}
        for i, e in enumerate(prm.get("edges") or []):
            if isinstance(e, dict) and (e.get("from") not in nodes or e.get("to") not in nodes):
                errors.append(f"{path}.params.edges[{i}]: joins unknown nodes {e.get('from')!r}-{e.get('to')!r}")
    return words


def _check_beat(b: dict, path: str, scene: _Scene, n_sent: int, errors: list[str]) -> None:
    err = _time_ok(b["at"], n_sent)
    if err:
        errors.append(f"{path}.at: {err}")
    do = b["do"]
    targets = b.get("target")
    targets = [targets] if isinstance(targets, str) else (targets or [])
    if do != "camera" and not targets:
        errors.append(f"{path}: '{do}' needs a target")
    resolved = []
    for t in targets:
        aid, terr = scene.resolve(t)
        if terr:
            errors.append(f"{path}.target: {terr}")
        resolved.append((t, aid))
    if do == "enter" and b.get("anim") and b["anim"] not in ENTER_ANIMS:
        errors.append(f"{path}.anim: enter animations are {list(ENTER_ANIMS)}")
    if do == "exit" and b.get("anim") and b["anim"] not in EXIT_ANIMS:
        errors.append(f"{path}.anim: exit animations are {list(EXIT_ANIMS)}")
    if do == "set":
        if "param" not in b or "to" not in b:
            errors.append(f"{path}: 'set' needs param and to")
            return
        for t, aid in resolved:
            if not aid:
                continue
            kind = scene.actors[aid]["kind"]
            param = b["param"]
            if "." in t and kind == "network":
                if param not in ("state", "flow"):
                    errors.append(f"{path}: network parts animate 'state' or 'flow', not '{param}'")
                continue
            if not is_animatable(kind, param):
                errors.append(f"{path}: '{param}' is not animatable on {kind} (animatable: "
                              f"{list(KINDS[kind].animatable) + list(COMMON_ANIMATABLE)})")
                continue
            spec = KINDS[kind].params.get(param)
            if spec:
                _check_value(spec, b["to"], f"{path}.to", scene, errors)
            elif not isinstance(b["to"], (int, float)):
                errors.append(f"{path}.to: '{param}' takes a number")
    if do == "move" and not (isinstance(b.get("to"), list) and len(b["to"]) == 2):
        errors.append(f"{path}: 'move' needs to: [x, y]")
    if do == "camera" and not (b.get("region") or targets):
        errors.append(f"{path}: 'camera' needs region [x, y, w, h] or a target")


NODE_KIND_ALIASES = {"home": "house", "homes": "house", "consumer": "load", "demand": "load", "customer": "load",
                     "generator": "plant", "station": "plant", "storage": "battery", "town": "city",
                     "industry": "factory", "relay": "switch", "breaker": "switch", "bus": "hub"}


HONESTY_NOTE = re.compile(r"exaggerat|not to scale|for illustration|simplified|sped up|slowed down", re.I)


def normalize_plan(plan: dict) -> dict:
    """Repairs cosmetic slips in place instead of spending a writer retry on them (unknown network node kinds
    become their nearest allowed kind; an "exaggerated for illustration" note set in the smallest type grows to
    the size other notes use). Returns the same plan."""
    kinds = KINDS["network"].params["nodes"]["item"]["kind"]["values"]
    for sc in plan.get("scenes") or []:
        for a in sc.get("actors") or []:
            if not isinstance(a, dict):
                continue
            prm = a.get("params") or {}
            if a.get("kind") == "text" and prm.get("size") == "xs" and HONESTY_NOTE.search(str(prm.get("text", ""))):
                prm["size"] = "s"
            if a.get("kind") != "network":
                continue
            for n in prm.get("nodes") or []:
                if isinstance(n, dict) and "kind" in n and n["kind"] not in kinds:
                    n["kind"] = NODE_KIND_ALIASES.get(str(n["kind"]).lower(), "generic")
    return plan


COVER_ACTIONS = ("set", "move", "trace")


def _check_coverage(plan: dict, required: list[str], scene_actors: dict[str, dict[str, dict]]) -> list[str]:
    """Every required topic needs its own visual: a non-text actor that `covers` it and is animated by a set,
    move or trace beat. `covers` holds one id, so two topics can never share an actor."""
    errors, shown = [], set()
    for sc in plan["scenes"]:
        actors = scene_actors.get(sc["id"], {})
        for a in sc["actors"]:
            cid = a.get("covers")
            if not cid:
                continue
            where = f"scenes[{sc['id']}].actors[{a['id']}]"
            if cid not in required:
                errors.append(_unknown_cover(cid, required, where))
            elif a["kind"] in TEXTY:
                errors.append(f"{where}.covers: a {a['kind']} cannot be the dedicated visual for '{cid}'; put covers "
                              "on the part that shows the mechanism")
        scene = _Scene(sc["id"], actors)
        for b in sc["beats"]:
            if b["do"] not in COVER_ACTIONS:
                continue
            targets = b.get("target")
            for t in [targets] if isinstance(targets, str) else (targets or []):
                aid, err = scene.resolve(t)
                a = actors.get(aid) if not err else None
                if a and a.get("covers") in required and a["kind"] not in TEXTY:
                    shown.add(a["covers"])
    for r in required:
        if r not in shown:
            errors.append(f"required topic '{r}' has no dedicated visual: give the actor that shows it (not text) "
                          f"\"covers\": \"{r}\" and animate it with a set, move or trace beat")
    return errors


def check_plan(plan: dict, script: dict, required: list[str] = ()) -> list[str]:
    errors: list[str] = []
    want = [sc["id"] for sc in script["scenes"]]
    got = [sc["id"] for sc in plan["scenes"]]
    if got != want:
        errors.append(f"plan scenes must match the script scene ids in order: expected {want}, got {got}")
    sentences = {sc["id"]: len(sc["sentences"]) for sc in script["scenes"]}
    final_actors: dict[str, dict[str, dict]] = {}
    for si, sc in enumerate(plan["scenes"]):
        base = f"scenes[{sc['id']}]"
        actors: dict[str, dict] = {}
        if sc.get("inherit"):
            if sc["inherit"] not in final_actors:
                errors.append(f"{base}.inherit: '{sc['inherit']}' is not an earlier scene")
            else:
                actors.update(final_actors[sc["inherit"]])
        for a in sc["actors"]:
            if a["id"] in actors and not sc.get("inherit"):
                errors.append(f"{base}: actor id '{a['id']}' is used twice")
            actors[a["id"]] = a
        scene = _Scene(sc["id"], actors)
        words = 0
        for ai, a in enumerate(sc["actors"]):
            words += _check_actor(a, f"{base}.actors[{a['id']}]", scene, errors)
        n_sent = sentences.get(sc["id"], 0)
        for bi, b in enumerate(sc["beats"]):
            _check_beat(b, f"{base}.beats[{bi}]", scene, n_sent, errors)
        if not any(b["do"] in MECHANISM_ACTIONS for b in sc["beats"]):
            errors.append(f"{base}: needs at least one mechanism beat ({', '.join(MECHANISM_ACTIONS)}) that shows "
                          "how something moves or changes, not just reveals")
        if words > MAX_SCENE_WORDS:
            errors.append(f"{base}: {words} on-screen words; keep it under {MAX_SCENE_WORDS} (the narration explains)")
        final_actors[sc["id"]] = actors
    poster = plan.get("poster")
    if poster and poster["scene"] not in got:
        errors.append(f"poster.scene '{poster['scene']}' is not a scene id")
    return errors + _check_coverage(plan, list(required), final_actors)
