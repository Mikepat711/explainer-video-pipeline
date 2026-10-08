"""Layout fix: a grind writer (llm.grind, e.g. Grok) clears text overlaps in the visual plan.

The writer's plan (Claude by default) is checked with the renderer's own layout probe at the real
narration timing. Each scene with issues goes to the grind writer, which may only move, resize, re-anchor
or re-time things: actor ids and kinds, every on-screen word, the beat sequence and the scene's teaching
fields are locked and verified. Every reply is re-probed; remaining issues are fed back for another
round (llm.retries), and the best version of each scene is kept only if it has fewer issues.
Output: plan.fixed.json (a plain copy when the grind writer is off or nothing needs fixing).
"""
from __future__ import annotations

import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor

from ..claude import ClaudeError
from ..config import frame_size
from ..gfx.render import make_renderer
from ..pipeline import Stage
from ..plan.checks import check_plan, normalize_plan
from ..plan.schemas import PLAN
from ..plan.vocab import CAPTION_TOP, DESIGN_H, DESIGN_W
from ..util import log, read_json, write_json
from ..writer import get_writer, write_meta, writer_identity
from .render import _meta, _overlap, layout_check, probe_times
from .timeline import _TEXT_KEYS, plan_timeline

LAYOUT_FIX = {"type": "object", "required": ["scene"], "properties": {
    "scene": PLAN["properties"]["scenes"]["items"],
    "changes": {"type": "array", "items": {"type": "string"}, "maxItems": 40}}}
LOCKED_SCENE_KEYS = ("id", "concept", "mechanism", "visual_cue", "inherit", "transition")
EXTRA_BEATS = ("exit", "move")  # the only beats a fix may add


def texts(obj, path="") -> list[tuple[str, str]]:
    """Every on-screen string (label, title, value, ...) with its path; a fix must keep all of them."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and k in _TEXT_KEYS:
                out.append((f"{path}.{k}", v))
            else:
                out += texts(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += texts(v, f"{path}[{i}]")
    return out


def intent_errors(orig: dict, new: dict) -> list[str]:
    """What a layout fix changed beyond layout (empty = design intent kept)."""
    errs = [f"scene field '{k}' must stay exactly as it was" for k in LOCKED_SCENE_KEYS if orig.get(k) != new.get(k)]
    a0 = {a["id"]: a for a in orig.get("actors", [])}
    a1 = {a.get("id"): a for a in new.get("actors", [])}
    if set(a0) != set(a1):
        errs.append(f"keep exactly the same actors (missing: {sorted(set(a0) - set(a1))}, added: "
                    f"{sorted(set(a1) - set(a0))})")
    for aid in set(a0) & set(a1):
        if a0[aid]["kind"] != a1[aid].get("kind"):
            errs.append(f"actor '{aid}' must stay kind '{a0[aid]['kind']}'")
        if sorted(texts(a0[aid].get("params") or {})) != sorted(texts(a1[aid].get("params") or {})):
            errs.append(f"actor '{aid}': on-screen text must not change (move, resize or re-anchor it instead)")
    seq0 = [(b["do"], json.dumps(b.get("target"))) for b in orig.get("beats", [])]
    seq1 = [(b.get("do"), json.dumps(b.get("target"))) for b in new.get("beats", [])]
    i, extras = 0, []
    for y in seq1:
        if i < len(seq0) and y == seq0[i]:
            i += 1
        else:
            extras.append(y)
    if i < len(seq0):
        errs.append("keep every original beat (same action and target) in the same order; you may change "
                    "at/dur/to/region/anim and add only 'exit' or 'move' beats")
    elif any(d not in EXTRA_BEATS for d, _ in extras):
        errs.append("only 'exit' or 'move' beats may be added")
    return errs


class Probe:
    """Layout issues of a plan at the real narration timing (16:9, the primary aspect)."""

    def __init__(self, ctx):
        self.ctx, self.cfg = ctx, ctx.cfg
        self.timing = {s["id"]: s for s in read_json(ctx.common / "voice" / "timing.json")["scenes"]}
        self.size = frame_size(dict(self.cfg, video=dict(self.cfg["video"], aspect="16:9")))

    def scenes(self, plan: dict) -> tuple[list[dict], dict]:
        full = plan_timeline(plan, self.timing, self.cfg["length"], self.cfg["video"]["fps"])
        out, t0 = [], 0.0
        for i, sc in enumerate(full, 1):
            out.append({"id": sc["id"], "index": i, "start": t0, "duration": sc["duration"], "spec": sc["spec"],
                        "sentences": sc["sentences"]})
            t0 += sc["duration"]
        tl = {"title": "", "total": t0, "crossfade": float(self.cfg["style"].get("crossfade", 0.5)), "scenes": out}
        return out, tl

    def issues(self, plan: dict, only: str | None = None) -> dict[str, list[str]]:
        scenes, tl = self.scenes(plan)
        return {sc["id"]: layout_check(sc, tl, self.cfg, self.size)["issues"]
                for sc in scenes if only in (None, sc["id"])}

    def boxes(self, plan: dict, sid: str) -> list[str]:
        """Text boxes in design units at each probe time, so the fixer can see where things are."""
        scenes, tl = self.scenes(plan)
        sc = next(s for s in scenes if s["id"] == sid)
        r = make_renderer(sc["spec"], sc["duration"], _meta(sc, tl), self.cfg, self.size)
        k = DESIGN_W / self.size[0]
        lines = []
        for t in probe_times(sc):
            boxes = [b for b in r.probe(t)["boxes"] if _overlap(b[1], (0, 0, *self.size)) > 0.5]
            lines.append(f"t={t}s: " + "; ".join(f"{tag} [x={x * k:.0f}, y={y * k:.0f}, w={w * k:.0f}, h={h * k:.0f}]"
                                                for tag, (x, y, w, h) in boxes))
        return lines


def fix_prompt(scene: dict, issues: list[str], boxes: list[str], captions: bool) -> str:
    cap = f"Burned-in captions cover y > {CAPTION_TOP}; text must stay above that line." if captions else ""
    return f"""TASK: layout
You are the production artist finishing a motion designer's animated scene. The design is approved; your job
is purely mechanical: make every piece of on-screen text readable, with no overlaps, nothing outside the
frame and nothing in the caption area. Do not redesign, restyle or re-teach anything.

Design space: {DESIGN_W}x{DESIGN_H}, origin top-left, y down; an actor's "at" is its center. {cap}

You may change ONLY: actor "at", "scale", "rotate", "z", layout params (sizes, text size, anchors/sides,
offsets, spacing, widths), beat timing ("at", "dur"), "move" destinations ("to"), camera regions, and enter/exit
animations. You may add "exit" beats (to clear a label before another takes its place) or "move" beats.
You must NOT change: any on-screen words, actor ids or kinds, the order of the existing beats, or the scene's
id/concept/mechanism/visual_cue/inherit/transition. Keep the composition recognisably the same: nudge,
shrink or re-time rather than rearranging the whole scene.

Layout problems found by the renderer (t = seconds into the scene; tags are actor ids, "id.part" for parts):
{chr(10).join(f"- {i}" for i in issues)}

Text boxes on screen at each checked moment (design units):
{chr(10).join(boxes)}

Scene JSON:
{json.dumps(scene, ensure_ascii=False)}

Reply with ONE JSON document and nothing else: {{"scene": <the complete corrected scene>, "changes": ["short
note per change"]}}. The scene must keep the same JSON structure and stay valid.
"""


class Layout(Stage):
    name = "layout"
    scope = "common"
    deps = ("plan", "voice")
    description = "fix text overlaps in the visual plan without changing its design (grind writer)"
    extra_code = ("claude.py", "writer.py", "plan", "gfx", "stages/render.py", "stages/timeline.py")

    def inputs(self, ctx):
        L = ctx.cfg["length"]
        return {"grind": writer_identity(ctx.cfg, self.name), "captions": ctx.cfg["captions"]["burn_in"],
                "style": ctx.cfg["style"], "fps": ctx.cfg["video"]["fps"],
                "pacing": {k: L.get(k) for k in ("min_scene", "reveal_hold", "reading_wpm")}}

    def outputs(self, ctx):
        c = ctx.common
        return [c / "plan.fixed.json", c / "layout.meta.json", c / "layout.md"]

    def run(self, ctx):
        c = ctx.common
        plan = read_json(c / "plan.json")
        meta_p = c / "plan.meta.json"
        fallback = meta_p.exists() and read_json(meta_p).get("fallback")
        writer, reason = get_writer(ctx.cfg, self.name)
        if plan.get("legacy_shots") or not plan.get("scenes") or fallback:
            return self._done(c, plan, "none", "no visual plan to fix", {}, {})
        probe = Probe(ctx)
        before = probe.issues(plan)
        n0 = sum(map(len, before.values()))
        log(f"    layout check: {n0} issue(s) in {sum(1 for v in before.values() if v)} scene(s)")
        if not writer or not n0:
            why = "nothing to fix" if not n0 else f"grind writer off ({reason})"
            return self._done(c, plan, writer.identity() if writer else "off", why, before, before)
        script = read_json(c / "script.json")
        required = ctx.brief.ids
        bad = [sid for sid, v in before.items() if v]
        log(f"    {writer.identity()} fixing {len(bad)} scene(s), up to {writer.retries + 1} rounds each")

        def fix(sid: str) -> dict:
            idx = next(i for i, s in enumerate(plan["scenes"]) if s["id"] == sid)
            orig = plan["scenes"][idx]
            best = {"sid": sid, "n": len(before[sid]), "scene": None, "changes": [], "rounds": 0}

            def check(payload: dict) -> list[str]:
                best["rounds"] += 1
                scene = payload["scene"]
                errs = intent_errors(orig, scene)
                cand = copy.deepcopy(plan)
                cand["scenes"][idx] = scene
                errs += [e for e in check_plan(normalize_plan(copy.deepcopy(cand)), script, required)
                         if sid in e or "scenes" not in e]
                if errs:
                    return errs
                try:
                    left = probe.issues(cand, only=sid)[sid]
                except Exception as exc:  # a reply the renderer cannot draw
                    return [f"the renderer could not draw this scene: {exc}"]
                log(f"    layout {sid}: round {best['rounds']}: {len(before[sid])} -> {len(left)} issue(s)")
                if len(left) < best["n"]:
                    best.update(n=len(left), scene=scene, changes=payload.get("changes") or [])
                return [f"still a layout problem: {m}" for m in left]

            t0 = time.time()
            try:
                _, meta = writer.generate("layout", fix_prompt(orig, before[sid], probe.boxes(plan, sid),
                                                               ctx.cfg["captions"]["burn_in"]), LAYOUT_FIX, check=check)
                best["cost_usd"] = meta.get("cost_usd")
            except ClaudeError as exc:  # usually "issues remain after the last round"; the best round is still kept
                best["error"] = str(exc)[:300]
                best["cost_usd"] = getattr(exc, "cost_usd", None)
            best["seconds"] = round(time.time() - t0, 1)
            return best

        workers = max(1, int(ctx.cfg["llm"].get("grind_parallel", 4)))
        with ThreadPoolExecutor(min(workers, len(bad))) as ex:
            results = list(ex.map(fix, bad))
        fixed = copy.deepcopy(plan)
        for r in results:
            if r["scene"] is not None:
                fixed["scenes"][next(i for i, s in enumerate(plan["scenes"]) if s["id"] == r["sid"])] = r["scene"]
        after = probe.issues(fixed)
        # a fix can shift a later scene that inherits this one; keep the merged plan only where it is better
        for r in results:
            if r["scene"] is not None and len(after.get(r["sid"], [])) > len(before[r["sid"]]):
                i = next(i for i, s in enumerate(plan["scenes"]) if s["id"] == r["sid"])
                fixed["scenes"][i] = plan["scenes"][i]
                r["reverted"] = True
        after = probe.issues(fixed)
        if sum(map(len, after.values())) >= n0:
            fixed, after = plan, before
        self._done(c, fixed, writer.identity(), "", before, after, results)

    @staticmethod
    def _done(c, plan, writer, note, before, after, results=()):
        write_json(c / "plan.fixed.json", plan)
        n0, n1 = sum(map(len, before.values())), sum(map(len, after.values()))
        md = [f"# Layout fix ({writer})", "", f"Issues: {n0} before, {n1} after." + (f" {note}." if note else ""), ""]
        for r in results:
            md.append(f"## {r['sid']}: {len(before[r['sid']])} -> {len(after.get(r['sid'], []))} issue(s)"
                      f" in {r.get('rounds', 0)} round(s), {r.get('seconds', 0)}s"
                      + (" (reverted: made a later scene worse)" if r.get("reverted") else "")
                      + (f" (gave up: {r['error']})" if r.get("error") and r["scene"] is None else ""))
            md += [f"- {ch}" for ch in r.get("changes") or []] + [""]
        (c / "layout.md").write_text("\n".join(md) + "\n")
        total_cost = sum(r.get("cost_usd") or 0 for r in results)
        write_meta(c, "layout", writer, issues_before=n0, issues_after=n1, note=note,
                   scenes=[{k: r.get(k) for k in ("sid", "rounds", "seconds", "cost_usd", "error", "reverted")}
                           | {"before": len(before[r["sid"]]), "after": len(after.get(r["sid"], []))}
                           for r in results], cost_usd=round(total_cost, 4) or None)
        log(f"    layout: {n0} -> {n1} issue(s){' (' + note + ')' if note else ''}")
