from __future__ import annotations

import yaml

from .. import offline
from ..gfx.scenes import TEMPLATES
from ..pipeline import Stage
from ..scriptfmt import parse_script
from ..util import log, write_json
from .common import optional_file, plan_engine


def _describe(shot: dict) -> str:
    t = shot["template"]
    bits = []
    for key in ("title", "value", "unit"):
        if shot.get(key):
            bits.append(str(shot[key]))
    for key in ("items", "steps", "nodes", "layers", "cards", "anchors", "labels", "packet"):
        vals = shot.get(key) or []
        names = [(v.get("text") or v.get("label") or v.get("title") or "") if isinstance(v, dict) else str(v)
                 for v in vals]
        if names:
            bits.append(f"{key}: " + ", ".join(n for n in names if n))
    return f"{t} — " + "; ".join(bits)


class Shots(Stage):
    name = "shots"
    scope = "common"
    deps = ("script", "plan")
    description = "template shot list (legacy topic packs and the fallback path only)"
    extra_code = ("offline.py", "stages/common.py")

    def inputs(self, ctx):
        return {"override": optional_file(ctx.topic_dir / "shots.yaml"), "templates": sorted(TEMPLATES),
                "engine": ctx.cfg["render"].get("engine", "auto")}

    def outputs(self, ctx):
        return [ctx.common / "shots.json", ctx.common / "shots.md"]

    def run(self, ctx):
        script = parse_script((ctx.common / "script.md").read_text())
        if plan_engine(ctx) is not None:
            # Overwrites any shot list left by an older build so it can never be rendered by mistake.
            write_json(ctx.common / "shots.json", {"title": script["title"], "subtitle": script["subtitle"],
                                                   "scenes": [], "unused": "this topic renders its visual plan"})
            (ctx.common / "shots.md").write_text("# Shot list\n\nNot used: this topic renders plan.json.\n")
            log("    not needed: the visual plan renders this topic")
            return
        override = ctx.topic_dir / "shots.yaml"
        if override.exists():
            log("    using hand-authored shots.yaml from topic pack")
            plan = yaml.safe_load(override.read_text())
        else:
            plan = offline.shots_from_script(script)
        by_id = {s["id"]: s for s in (plan or {}).get("scenes", []) if isinstance(s, dict) and "id" in s}
        fallback = {s["id"]: s for s in offline.shots_from_script(script)["scenes"]}
        shots = []
        for sc in script["scenes"]:
            shot = dict(by_id.get(sc["id"]) or fallback[sc["id"]])
            if shot.get("template") not in TEMPLATES:
                log(f"    scene {sc['id']}: unknown template {shot.get('template')!r}; using fallback")
                shot = dict(fallback[sc["id"]])
            shot.setdefault("heading", sc["heading"])
            shot["id"] = sc["id"]
            shots.append(shot)
        write_json(ctx.common / "shots.json", {"title": script["title"], "subtitle": script["subtitle"],
                                               "scenes": shots})
        lines = [f"# Shot list — {script['title']}", "", "| # | Scene | Template | On screen | Narration |",
                 "|---|---|---|---|---|"]
        for i, (sh, sc) in enumerate(zip(shots, script["scenes"]), 1):
            narr = sc["narration"][:110] + ("…" if len(sc["narration"]) > 110 else "")
            lines.append(f"| {i} | {sh['heading']} | `{sh['template']}` | {_describe(sh)} | {narr} |")
        (ctx.common / "shots.md").write_text("\n".join(lines) + "\n")
