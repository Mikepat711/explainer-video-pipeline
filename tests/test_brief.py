"""Producer briefs: required topics reach every writer prompt, the validators enforce them, --fresh sets the pack aside."""
import argparse
import contextlib
import copy
import functools
import io
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from explainer import cli
from explainer.brief import Brief, load_brief, parse_brief
from explainer.pipeline import Context
from explainer.plan.checks import check_plan, check_research, check_script, normalize_plan
from explainer.plan.docs import script_markdown
from explainer.plan.prompts import plan_prompt, research_prompt, script_prompt
from explainer.plan.schemas import PLAN, RESEARCH, SCRIPT
from explainer.schema import validate
from explainer.util import read_json
from explainer.writer import read_metas
from test_writer import FIX, TOPIC, FakeClaudeCase

REQUIRE = [{"id": "spin", "text": "how a spinning magnet makes alternating current"},
           {"id": "losses", "text": "why a higher voltage cuts line losses"}]
IDS = [r["id"] for r in REQUIRE]


def fixture(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text())


def covered() -> tuple[dict, dict, dict]:
    """The fixture research/script/plan, amended to cover REQUIRE."""
    research, script, plan = fixture("research"), fixture("script"), fixture("plan")
    research["required_topics"] = [{"id": r["id"], "explanation": r["text"], "mechanism": "m", "visual": "v"}
                                   for r in REQUIRE]
    script["scenes"][0]["covers"] = ["spin"]
    script["scenes"][1]["covers"] = ["losses"]
    actors = {a["id"]: a for sc in plan["scenes"] for a in sc["actors"]}
    actors["gen"]["covers"] = "spin"
    actors["line"]["covers"] = "losses"
    return research, script, plan


class BriefParsingTests(unittest.TestCase):
    TEXT = ("---\nconfig:\n  length: {target_seconds: 200}\n---\n# Brief: the grid\n<!-- for the humans -->\n"
            "Open on a kettle.\n\n## Required topics\n- spin: how the magnet\n  makes AC\n- losses: why voltage helps\n"
            "\n## Notes\nKeep it calm.\n")

    def test_requirements_notes_and_config(self):
        b = parse_brief(self.TEXT, "brief.md")
        self.assertEqual(b.ids, ["spin", "losses"])
        self.assertEqual(b.require[0]["text"], "how the magnet makes AC")
        self.assertEqual(b.config, {"length": {"target_seconds": 200}})
        self.assertIn("Open on a kettle.", b.notes)
        self.assertIn("Keep it calm.", b.notes)
        for gone in ("for the humans", "# Brief", "spin:"):
            self.assertNotIn(gone, b.notes)
        self.assertFalse(Brief())

    def test_bad_requirements_are_rejected(self):
        for text in ("## Required topics\n- Not an id\n", "## Required topics\n- wind - no colon\n"):
            with self.assertRaises(SystemExit):
                parse_brief(text)
        with self.assertRaises(SystemExit):
            load_brief(Path("/nonexistent"), requires=["Wind Power: x"])
        b = parse_brief("## Required topics\n- wind: rotor\n\nProse after the list is a note.\n")
        self.assertEqual((b.ids, b.notes), (["wind"], "Prose after the list is a note."))

    def test_sources_merge_and_later_ids_replace(self):
        with self._tmpdir() as tmp:
            topic = tmp / "topic"
            topic.mkdir()
            (topic / "brief.md").write_text(self.TEXT)
            extra = tmp / "extra.md"
            extra.write_text("## Required topics\n- solar: panels\n\nMore notes.\n")
            b = load_brief(topic, [str(extra)], ["spin: the rotor, not the magnet"])
        self.assertEqual(b.ids, ["spin", "losses", "solar"])
        self.assertEqual(b.require[0]["text"], "the rotor, not the magnet")
        self.assertIn("More notes.", b.notes)
        self.assertEqual(len(b.origins), 3)

    def test_cli_reads_the_topic_brief(self):
        with self._tmpdir() as tmp:
            (tmp / "topics" / "test-grid-lesson").mkdir(parents=True)
            (tmp / "topics" / "test-grid-lesson" / "brief.md").write_text(self.TEXT)
            build = functools.partial(Context, topics_root=tmp / "topics")
            args = argparse.Namespace(topic=TOPIC, config=None, set=None, aspect=None, scenes=None, tag=None,
                                      source=None, brief=None, require=["solar: panels"], fresh=True)
            with mock.patch.object(cli, "Context", build), contextlib.redirect_stderr(io.StringIO()):
                ctx = cli._ctx(args)
        self.assertEqual((ctx.brief.ids, ctx.fresh), (["spin", "losses", "solar"], True))
        self.assertEqual(ctx.cfg["length"]["target_seconds"], 200)

    @staticmethod
    @contextlib.contextmanager
    def _tmpdir():
        import shutil
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="explainer-brief-"))
        try:
            yield d
        finally:
            shutil.rmtree(d, ignore_errors=True)


class CoverageCheckTests(unittest.TestCase):
    def test_research_reports_every_required_topic(self):
        research, _, _ = covered()
        self.assertEqual(validate(research, RESEARCH) + check_research(research, IDS), [])
        self.assertEqual(len(check_research(fixture("research"), IDS)), 2)
        self.assertIn("not one of the required ids", " ".join(check_research(research, ["spin"])))
        self.assertEqual(check_research(fixture("research"), []), [])

    def test_script_must_teach_every_required_topic(self):
        _, script, _ = covered()
        self.assertEqual(validate(script, SCRIPT) + check_script(script, (60, 84), IDS), [])
        errors = check_script(fixture("script"), (60, 84), IDS)
        self.assertTrue(any("required topic 'spin' is not taught" in e for e in errors))
        self.assertEqual(len(errors), 2)
        script["scenes"][2]["covers"] = ["bogus"]
        self.assertIn("'bogus' is not a required topic id", " ".join(check_script(script, (60, 84), IDS)))

    def test_plan_needs_a_dedicated_animated_visual_per_topic(self):
        _, script, plan = covered()
        self.assertEqual(validate(plan, PLAN) + check_plan(plan, script, IDS), [])
        errors = check_plan(fixture("plan"), script, IDS)
        self.assertEqual(sum("has no dedicated visual" in e for e in errors), 2)

        texty = copy.deepcopy(plan)
        texty["scenes"][0]["actors"][0].pop("covers")
        texty["scenes"][0]["actors"][1]["covers"] = "spin"
        errors = " ".join(check_plan(texty, script, IDS))
        self.assertIn("a label cannot be the dedicated visual for 'spin'", errors)
        self.assertIn("required topic 'spin' has no dedicated visual", errors)

        still = copy.deepcopy(plan)
        still["scenes"][1]["beats"] = [b for b in still["scenes"][1]["beats"] if b.get("target") != "line"]
        self.assertIn("'losses' has no dedicated visual", " ".join(check_plan(still, script, IDS)))
        self.assertIn("drop covers", " ".join(check_plan(plan, script)))

    def test_inherited_actor_animated_later_counts(self):
        _, script, plan = covered()
        plan["scenes"][2]["inherit"] = "step-up"
        plan["scenes"][1]["beats"] = [b for b in plan["scenes"][1]["beats"] if b.get("target") != "line"]
        plan["scenes"][2]["beats"].append({"at": "s1", "do": "set", "target": "line", "param": "flow", "to": 0.5})
        self.assertEqual(check_plan(plan, script, IDS), [])

    def test_small_honesty_notes_grow_to_note_size(self):
        plan = {"scenes": [{"actors": [
            {"id": "a", "kind": "text", "params": {"text": "Change exaggerated for illustration", "size": "xs"}},
            {"id": "b", "kind": "text", "params": {"text": "Not to scale", "size": "xs"}},
            {"id": "c", "kind": "text", "params": {"text": "Fine print", "size": "xs"}},
            {"id": "d", "kind": "text", "params": {"text": "Exaggerated", "size": "m"}}]}]}
        sizes = [a["params"]["size"] for a in normalize_plan(plan)["scenes"][0]["actors"]]
        self.assertEqual(sizes, ["s", "s", "xs", "m"])

    def test_prompts_carry_the_brief(self):
        brief = Brief(REQUIRE, "Open on a kettle.")
        _, script, _ = covered()
        prompts = [research_prompt(TOPIC, [], brief), script_prompt(TOPIC, {}, (80, 60, 84), 30, brief),
                   plan_prompt(TOPIC, script, {}, True, "16:9", brief)]
        for p in prompts:
            self.assertIn("- spin: how a spinning magnet makes alternating current", p)
            self.assertIn("Open on a kettle.", p)
        self.assertIn("[spin] ", prompts[2])
        self.assertIn("| covers: spin |", prompts[2])
        self.assertIn('"covers" holds a single id', prompts[2])
        self.assertNotIn("REQUIRED TOPICS", plan_prompt(TOPIC, script, {}, True, "16:9"))
        self.assertIn('Leave out "covers"', plan_prompt(TOPIC, script, {}, True, "16:9"))


class BriefStageTests(FakeClaudeCase):
    def pack(self) -> Path:
        d = self.tmp / "topics" / "test-grid-lesson"
        d.mkdir(parents=True)
        (d / "research.md").write_text("# Research\n\nHand-written notes.\n")
        (d / "script.md").write_text(script_markdown(fixture("script")))
        (d / "plan.json").write_text(json.dumps(fixture("plan")))
        return d

    def ctx(self, cfg, **kw) -> Context:
        return Context(topic=TOPIC, cfg=cfg, build_root=self.tmp / "build", out_root=self.tmp / "out",
                       topics_root=self.tmp / "topics", **kw)

    def writers(self, ctx) -> list[str]:
        return [m["writer"] for m in read_metas(ctx.common)]

    def test_fresh_sets_the_pinned_pack_aside(self):
        self.pack()
        ctx = self.ctx(self.cfg())
        self.assertEqual(self.run_until_plan(ctx), ["research", "script", "plan"])
        self.assertEqual(self.writers(ctx), ["topic-pack"] * 3)
        self.assertEqual(self.calls(), [])
        fresh = self.ctx(self.cfg(), fresh=True)
        self.assertEqual(self.run_until_plan(fresh), ["research", "script", "plan"])
        self.assertEqual(self.writers(fresh), ["claude:opus"] * 3)
        self.assertEqual([c["task"] for c in self.calls()], ["research", "script", "plan"])
        self.assertEqual(self.run_until_plan(self.ctx(self.cfg(), fresh=True)), [])

    def test_fresh_changes_nothing_without_a_pack(self):
        self.assertEqual(self.run_until_plan(self.ctx(self.cfg())), ["research", "script", "plan"])
        self.assertEqual(self.run_until_plan(self.ctx(self.cfg(), fresh=True)), [])

    def test_required_topics_reach_claude_and_are_validated(self):
        fixtures = self.tmp / "fixtures"
        fixtures.mkdir()
        for name, doc in zip(("research", "script", "plan"), covered()):
            (fixtures / f"{name}.json").write_text(json.dumps(doc))
        os.environ["FAKE_CLAUDE_FIXTURES"] = str(fixtures)
        ctx = self.ctx(self.cfg(), brief=Brief(REQUIRE))
        self.assertEqual(self.run_until_plan(ctx), ["research", "script", "plan"])
        for call in self.calls():
            prompt = call["argv"][call["argv"].index("-p") + 1]
            self.assertIn("- losses: why a higher voltage cuts line losses", prompt)
        c = ctx.common
        self.assertIn("## Required topics", (c / "research.md").read_text())
        self.assertIn("covers: spin", (c / "script.md").read_text())
        self.assertIn("**Required topics shown:** spin (`gen`, generator)", (c / "plan.md").read_text())
        self.assertEqual(read_json(c / "script.json")["scenes"][0]["covers"], ["spin"])

    def test_required_topics_never_fall_back_to_the_offline_writer(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            self.run_until_plan(self.ctx(self.cfg(), brief=Brief(REQUIRE)))
        self.assertIn("research needs the Claude writer (the brief has required topics)", str(cm.exception))
        self.assertIn("required_topics: 'spin' is missing", str(cm.exception))
        self.assertNotIn("UNAVAILABLE", err.getvalue())
        self.assertFalse((self.ctx(self.cfg()).common / "research.json").exists())
        with self.assertRaises(SystemExit) as cm:
            self.run_until_plan(self.ctx(self.cfg(claude_bin=str(self.tmp / "nope" / "claude")), fresh=True))
        self.assertIn("(--fresh)", str(cm.exception))

    def test_pinned_plan_missing_required_topics_only_warns(self):
        self.pack()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(err):
            ran = self.run_until_plan(self.ctx(self.cfg(), brief=Brief(REQUIRE)))
        self.assertEqual(ran, ["research", "script", "plan"])
        self.assertIn("required topic 'spin' has no dedicated visual", err.getvalue())
        self.assertIn("--fresh has Claude write one that covers them", err.getvalue())
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
