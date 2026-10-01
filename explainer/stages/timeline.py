from __future__ import annotations

import re

from ..pipeline import Stage
from ..util import log, read_json, write_json
from .common import plan_engine

_REF = re.compile(r"^\s*(s|e)(\d+)\s*([+-]\s*\d*\.?\d+)?\s*$", re.I)
_END = re.compile(r"^\s*end\s*([+-]\s*\d*\.?\d+)?\s*$", re.I)


def resolve_time(val, sentences: list[dict], dur: float):
    if isinstance(val, (int, float)):
        return float(val)
    if not isinstance(val, str):
        return val
    m = _REF.match(val)
    if m:
        idx = min(max(int(m.group(2)) - 1, 0), len(sentences) - 1) if sentences else 0
        base = 0.5 if not sentences else sentences[idx]["start" if m.group(1).lower() == "s" else "end"]
        return round(base + float((m.group(3) or "0").replace(" ", "")), 3)
    m = _END.match(val)
    if m:
        return round(dur + float((m.group(1) or "0").replace(" ", "")), 3)
    try:
        return float(val)
    except ValueError:
        return val


def resolve_spec(obj, sentences, dur, found: list):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "at" or k.endswith("_at"):
                r = resolve_time(v, sentences, dur)
                if isinstance(r, float):
                    r = min(max(r, 0.0), max(0.0, dur - 0.6))
                    found.append(r)
                out[k] = r
            else:
                out[k] = resolve_spec(v, sentences, dur, found)
        return out
    if isinstance(obj, list):
        return [resolve_spec(v, sentences, dur, found) for v in obj]
    return obj


_TEXT_KEYS = {"heading", "title", "subtitle", "kicker", "text", "label", "sub", "value", "prefix", "unit", "note",
              "ray_label", "receive_label", "delta_label", "formula", "result", "fix_label", "flow_label",
              "hero_label"}


def on_screen_words(obj) -> int:
    """Rough count of words a viewer has to read in a shot spec."""
    if isinstance(obj, list):
        return sum(len(v.split()) if isinstance(v, str) else on_screen_words(v) for v in obj)
    if not isinstance(obj, dict):
        return 0
    n = 0
    for k, v in obj.items():
        if isinstance(v, str) and k in _TEXT_KEYS:
            n += len(v.split())
        elif isinstance(v, (dict, list)) and k != "sentences":
            n += on_screen_words(v)
    return n


def scene_duration(shot: dict, voice_dur: float, sentences: list[dict], L: dict) -> float:
    """Narration length, stretched so the last reveal and all on-screen text get time to be read."""
    base = voice_dur + float(shot.get("hold", 0))
    reveals: list[float] = []
    resolve_spec(shot, sentences, base, reveals)
    reading = on_screen_words(shot) / float(L.get("reading_wpm", 160)) * 60
    return max(float(L.get("min_scene", 3.0)), base, max(reveals, default=0.0) + float(L.get("reveal_hold", 1.5)),
               reading + 1.5)


PLAN_TEXT = {"text", "label", "meter", "badge", "dimension", "gauge", "compare", "wave", "powerline", "plant",
             "generator", "substation", "breaker"}
POP_ANIMS = {"pop", "grow", "build"}


def _plan_words(scene: dict) -> int:
    n = 0
    for a in scene.get("actors", []):
        prm = a.get("params") or {}
        if a.get("kind") in PLAN_TEXT:
            n += sum(len(str(prm.get(k, "")).split()) for k in ("text", "left_title", "right_title", "unit"))
    return n


def resolve_beats(scene: dict, sentences: list[dict], dur: float) -> dict:
    out = dict(scene)
    beats = []
    for b in scene.get("beats", []):
        r = resolve_time(b.get("at", 0), sentences, dur)
        b = dict(b, at=round(min(max(float(r) if isinstance(r, (int, float)) else 0.0, 0.0), max(0.0, dur - 0.05)), 3))
        beats.append(b)
    out["beats"] = beats
    return out


def plan_scene_duration(scene: dict, voice_dur: float, sentences: list[dict], L: dict) -> float:
    """Narration plus hold, stretched (by at most 3 s) so the last change completes and new parts can be read."""
    base = voice_dur + float(scene.get("hold", 0.5))
    beats = resolve_beats(scene, sentences, base)["beats"]
    enters = [b["at"] for b in beats if b["do"] == "enter"]
    ends = [b["at"] + float(b.get("dur") or (1.6 if b["do"] == "camera" else 1.0)) for b in beats
            if b["do"] in ("set", "move", "camera", "trace")]
    want = max([e + float(L.get("reveal_hold", 1.5)) for e in enters] + [e + 0.4 for e in ends] + [0.0])
    reading = _plan_words(scene) / float(L.get("reading_wpm", 160)) * 60 + 1.5
    return max(float(L.get("min_scene", 3.0)), base, min(base + 3.0, max(want, reading)))


def plan_timeline(plan: dict, timing: dict, L: dict, fps: int) -> list[dict]:
    """Every plan scene with its duration, resolved beats and the state it inherits (all scenes, unfiltered)."""
    from ..gfx.model import SceneModel, spin_budget
    style = plan.get("style") or {}
    spin = spin_budget(plan["scenes"])
    finals: dict[str, tuple] = {}
    out, prev = [], None
    for sc in plan["scenes"]:
        tm = timing.get(sc["id"])
        if tm is None:
            continue
        dur = round(plan_scene_duration(sc, tm["duration"], tm["sentences"], L) * fps) / fps
        scene = resolve_beats(sc, tm["sentences"], dur)
        base = finals[sc["inherit"]][0] if sc.get("inherit") in finals else None
        cam0 = finals[prev][1] if sc.get("transition") == "continue" and prev in finals else None
        model = SceneModel(scene, style, base, cam0, spin)
        finals[sc["id"]] = (model.final_state(dur), list(model.camera(dur)))
        spec = {"engine": "plan", "style": style, "scene": scene, "base": base, "camera0": cam0, "spin": spin}
        out.append({"id": sc["id"], "duration": dur, "spec": spec, "sentences": tm["sentences"],
                    "transition": sc.get("transition") or "fade", "hold": float(sc.get("hold", 0.5)),
                    "voice": tm["duration"]})
        prev = sc["id"]
    return out


def plan_events(sc: dict, t0: float, first: bool) -> list[dict]:
    ev = []
    if not first and sc["transition"] not in ("continue", "cut"):
        ev.append({"t": round(t0, 3), "kind": "whoosh"})
    for b in sc["spec"]["scene"]["beats"]:
        t = round(t0 + b["at"], 3)
        if b["do"] == "enter" and (b.get("anim") in POP_ANIMS or b.get("anim") is None):
            ev.append({"t": t, "kind": "pop"})
        elif b["do"] == "set" and b.get("param") == "state" and b.get("to") in ("open", "failed", "off"):
            ev.append({"t": t, "kind": "impact"})
        elif b["do"] == "pulse":
            ev.append({"t": t, "kind": "pop"})
    return ev


class Timeline(Stage):
    name = "timeline"
    deps = ("plan", "shots", "voice")
    description = "sync the visual plan (or legacy shots) to narration timing"
    extra_code = ("gfx/model.py", "plan/vocab.py", "stages/common.py")

    def inputs(self, ctx):
        L = ctx.cfg["length"]
        return {"scenes": ctx.scenes_filter, "fps": ctx.cfg["video"]["fps"],
                "pacing": {k: L.get(k) for k in ("min_scene", "reveal_hold", "reading_wpm")},
                "crossfade": ctx.cfg["style"].get("crossfade", 0.5),
                "engine": ctx.cfg["render"].get("engine", "auto")}

    def outputs(self, ctx):
        return [ctx.vdir / "timeline.json"]

    def run(self, ctx):
        timing = {s["id"]: s for s in read_json(ctx.common / "voice" / "timing.json")["scenes"]}
        plan = plan_engine(ctx)
        if plan is not None:
            return self._run_plan(ctx, plan, timing)
        log("    rendering with legacy shot templates")
        return self._run_shots(ctx, timing)

    def _chosen(self, ctx, ids: list[str]) -> set[str]:
        if not ctx.scenes_filter:
            return set(ids)
        chosen = {i for i in ids if i in ctx.scenes_filter}
        if not chosen:
            raise SystemExit(f"--scenes matched nothing; available: {ids}")
        return chosen

    def _run_plan(self, ctx, plan, timing):
        fps = ctx.cfg["video"]["fps"]
        L = ctx.cfg["length"]
        script = read_json(ctx.common / "script.json")
        full = plan_timeline(plan, timing, L, fps)
        chosen = self._chosen(ctx, [s["id"] for s in full])
        out, events, t0, stretched = [], [], 0.0, []
        for sc in full:
            if sc["id"] not in chosen:
                continue
            if sc["duration"] > sc["voice"] + sc["hold"] + 0.05:
                stretched.append(f"{sc['id']} +{sc['duration'] - sc['voice'] - sc['hold']:.1f}s")
            events += plan_events(sc, t0, not out)
            out.append({"id": sc["id"], "index": len(out) + 1, "start": round(t0, 4), "duration": sc["duration"],
                        "spec": sc["spec"], "sentences": sc["sentences"], "transition": sc["transition"]})
            t0 += sc["duration"]
        poster = None
        if plan.get("poster"):
            hit = next((s for s in out if s["id"] == plan["poster"]["scene"]), None)
            if hit:
                pt = resolve_time(plan["poster"]["at"], hit["sentences"], hit["duration"])
                pt = float(pt) if isinstance(pt, (int, float)) else hit["duration"] * 0.6
                poster = {"scene": hit["id"], "t": round(min(max(pt, 0.0), hit["duration"] - 0.1), 3)}
        self._write(ctx, script["title"], script.get("subtitle", ""), fps, t0, out, events, stretched, poster)

    def _run_shots(self, ctx, timing):
        shots = read_json(ctx.common / "shots.json")
        if shots.get("unused"):
            raise SystemExit("shots.json was not built for this topic (it has a visual plan); re-run the shots stage")
        fps = ctx.cfg["video"]["fps"]
        L = ctx.cfg["length"]
        chosen_ids = self._chosen(ctx, [s["id"] for s in shots["scenes"]])
        out, events, t0, stretched = [], [], 0.0, []
        for shot in shots["scenes"]:
            if shot["id"] not in chosen_ids:
                continue
            tm = timing[shot["id"]]
            dur = round(scene_duration(shot, tm["duration"], tm["sentences"], L) * fps) / fps
            if dur > tm["duration"] + float(shot.get("hold", 0)) + 0.05:
                stretched.append(f"{shot['id']} +{dur - tm['duration'] - float(shot.get('hold', 0)):.1f}s")
            found: list[float] = []
            spec = resolve_spec(shot, tm["sentences"], dur, found)
            if out:
                events.append({"t": round(t0, 3), "kind": "whoosh"})
            if shot["template"] in ("title", "stat"):
                events.append({"t": round(t0 + (found[0] if found else 0.6), 3), "kind": "impact"})
            for f in sorted(set(found)):
                events.append({"t": round(t0 + f, 3), "kind": "pop"})
            out.append({"id": shot["id"], "index": len(out) + 1, "start": round(t0, 4), "duration": dur, "spec": spec,
                        "sentences": tm["sentences"], "transition": "fade"})
            t0 += dur
        self._write(ctx, shots["title"], shots["subtitle"], fps, t0, out, events, stretched, None)

    def _write(self, ctx, title, subtitle, fps, total, out, events, stretched, poster):
        events.sort(key=lambda e: e["t"])
        dedup = []
        for e in events:
            if e["kind"] == "pop" and dedup and e["t"] - dedup[-1]["t"] < 0.3:
                continue
            dedup.append(e)
        log(f"    {len(out)} scenes, {total:.1f}s total, {len(dedup)} sound-design cues")
        if stretched:
            log(f"    held longer so changes finish and labels can be read: {', '.join(stretched)}")
        write_json(ctx.vdir / "timeline.json", {"title": title, "subtitle": subtitle, "fps": fps,
                                                "total": round(total, 4),
                                                "crossfade": float(ctx.cfg["style"].get("crossfade", 0.5)),
                                                "poster": poster, "scenes": out, "events": dedup})
