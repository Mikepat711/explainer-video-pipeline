from __future__ import annotations

import json

import yaml

from .. import offline
from ..claude import ClaudeError
from ..pipeline import Stage
from ..plan.checks import check_plan, normalize_plan
from ..plan.docs import plan_markdown
from ..plan.prompts import plan_prompt
from ..plan.schemas import PLAN
from ..schema import validate
from ..util import log, read_json, write_json
from ..writer import banner, fallback_is_stale, get_writer, require_claude, write_meta, writer_identity
from .common import optional_file


class Plan(Stage):
    name = "plan"
    scope = "common"
    deps = ("script",)
    description = "design the lesson-specific visual/animation plan (Claude)"
    extra_code = ("offline.py", "claude.py", "writer.py", "plan")

    def _override(self, ctx):
        return next(filter(None, map(ctx.pack_file, ("plan.json", "plan.yaml", "plan.yml"))), None)

    def inputs(self, ctx):
        return {"writer": writer_identity(ctx.cfg), "captions": ctx.cfg["captions"]["burn_in"],
                "override": optional_file(self._override(ctx)),
                "legacy_shots": optional_file(ctx.pack_file("shots.yaml")), "brief": ctx.brief.inputs()}

    def outputs(self, ctx):
        c = ctx.common
        return [c / "plan.json", c / "plan.md", c / "plan.meta.json"]

    def still_fresh(self, ctx):
        return not fallback_is_stale(ctx.common, self.name, ctx.cfg)

    def run(self, ctx):
        c = ctx.common
        script = read_json(c / "script.json")
        ov = self._override(ctx)
        if ov:
            log(f"    using hand-authored {ov.name} from topic pack")
            plan = json.loads(ov.read_text()) if ov.suffix == ".json" else yaml.safe_load(ov.read_text())
            errors = validate(plan, PLAN) or check_plan(normalize_plan(plan), script, ctx.brief.ids)
            for err in errors[:20]:
                log(f"    plan warning: {err}")
            if any("required topic" in e for e in errors):
                log("    the pinned plan misses required topics from the brief; --fresh has Claude write one that "
                    "covers them")
            self._write(c, plan, script)
            origin = plan.get("provenance") or {}
            write_meta(c, self.name, "topic-pack", **({"origin": origin} if origin else {}))
            return
        if ctx.pack_file("shots.yaml"):
            log("    topic pack has a hand-authored shots.yaml (legacy templates); no visual plan needed")
            write_json(c / "plan.json", {"legacy_shots": True, "scenes": []})
            (c / "plan.md").write_text("# Visual plan\n\nThis topic uses the hand-authored shots.yaml.\n")
            write_meta(c, self.name, "topic-pack")
            return
        research = read_json(c / "research.json")
        writer, reason = get_writer(ctx.cfg)
        if writer:
            try:
                prompt = plan_prompt(ctx.topic, script, research, ctx.cfg["captions"]["burn_in"],
                                     "16:9 (the 9:16 version is cropped from the same plan)", ctx.brief)
                plan, meta = writer.generate("plan", prompt, PLAN,
                                             check=lambda p: check_plan(normalize_plan(p), script, ctx.brief.ids))
                self._write(c, plan, script)
                write_meta(c, self.name, **meta)
                return
            except ClaudeError as exc:
                reason = str(exc)
        require_claude(ctx, self.name, reason)
        banner(self.name, reason)
        self._write(c, offline.plan_from_script(script), script)
        write_meta(c, self.name, "offline", fallback=True, reason=reason)

    @staticmethod
    def _write(c, plan: dict, script: dict) -> None:
        write_json(c / "plan.json", plan)
        (c / "plan.md").write_text(plan_markdown(plan, script))
        n_act = sum(len(s["actors"]) for s in plan["scenes"])
        n_beat = sum(len(s["beats"]) for s in plan["scenes"])
        kinds = sorted({a["kind"] for s in plan["scenes"] for a in s["actors"]})
        log(f"    {len(plan['scenes'])} scenes, {n_act} actors, {n_beat} beats; kinds: {', '.join(kinds)}")
