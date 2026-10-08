from __future__ import annotations

from .. import offline
from ..claude import ClaudeError
from ..pipeline import Stage
from ..plan.checks import check_script, script_coverage, script_words
from ..plan.docs import script_markdown
from ..plan.prompts import script_prompt
from ..plan.schemas import SCRIPT
from ..scriptfmt import parse_script
from ..util import log, read_json, write_json
from ..writer import banner, fallback_is_stale, get_writer, require_claude, write_meta, writer_identity, writer_name
from .common import optional_file


def _covers(notes: list[str]) -> list[str]:
    return [c.strip() for n in notes if n.startswith("covers:") for c in n[7:].split(",") if c.strip()]


def word_range(L: dict) -> tuple[int, int, int]:
    target = round(L["target_seconds"] / 60 * L["words_per_minute"])
    return target, round(target * 0.85), round(target * 1.2)


class Script(Stage):
    name = "script"
    scope = "common"
    deps = ("research",)
    description = "write the narration and per-scene teaching ideas (Claude)"
    extra_code = ("offline.py", "scriptfmt.py", "claude.py", "writer.py", "plan")

    def inputs(self, ctx):
        L = ctx.cfg["length"]
        return {"topic": ctx.topic, "length": {k: L[k] for k in ("target_seconds", "words_per_minute")},
                "writer": writer_identity(ctx.cfg, self.name), "override": optional_file(ctx.pack_file("script.md")),
                "brief": ctx.brief.inputs()}

    def outputs(self, ctx):
        c = ctx.common
        return [c / "script.md", c / "script.json", c / "script.meta.json"]

    def still_fresh(self, ctx):
        return not fallback_is_stale(ctx.common, self.name, ctx.cfg)

    def run(self, ctx):
        c = ctx.common
        L = ctx.cfg["length"]
        target, lo, hi = word_range(L)
        override = ctx.pack_file("script.md")
        if override:
            log("    using hand-authored script.md from topic pack")
            text = override.read_text()
            parsed = parse_script(text)
            script = {"mode": "topic-pack", "title": parsed["title"], "subtitle": parsed["subtitle"], "logline": "",
                      "scenes": [{"id": s["id"], "heading": s["heading"], "sentences": s["sentences"], "concept": "",
                                  "visual_idea": " ".join(s["notes"]), "covers": _covers(s["notes"])}
                                 for s in parsed["scenes"]]}
            (c / "script.md").write_text(text)
            missing = script_coverage(script, ctx.brief.ids)
            for err in missing:
                log(f"    script warning: {err}")
            if missing:
                log("    the pinned script misses required topics from the brief; --fresh has Claude write one that "
                    "covers them")
            self._finish(c, script, L)
            write_meta(c, self.name, "topic-pack")
            return
        research = read_json(c / "research.json")
        writer, reason = get_writer(ctx.cfg, self.name)
        if writer:
            try:
                brief = {k: v for k, v in research.items() if k != "mode"}
                if research.get("mode") == "topic-pack":
                    brief["notes"] = (c / "research.md").read_text()[:20000]
                payload, meta = writer.generate(
                    "script", script_prompt(ctx.topic, brief, (target, lo, hi), L["target_seconds"], ctx.brief),
                    SCRIPT, check=lambda s: check_script(s, (lo, hi), ctx.brief.ids))
                script = {"mode": "claude", **payload}
                (c / "script.md").write_text(script_markdown(script))
                self._finish(c, script, L)
                write_meta(c, self.name, **meta)
                return
            except ClaudeError as exc:
                reason = str(exc)
        require_claude(ctx, self.name, reason)
        banner(self.name, reason, writer_name(ctx.cfg, self.name))
        sections = research.get("sections") or []
        script = {"mode": "offline", **offline.teaching_script(ctx.topic, sections, target)}
        (c / "script.md").write_text(script_markdown(script))
        self._finish(c, script, L)
        write_meta(c, self.name, "offline", fallback=True, reason=reason)

    @staticmethod
    def _finish(c, script: dict, L: dict) -> None:
        write_json(c / "script.json", script)
        wc = script_words(script)
        log(f"    {len(script['scenes'])} scenes, {wc} words (~{wc / L['words_per_minute'] * 60:.0f}s of content)")
