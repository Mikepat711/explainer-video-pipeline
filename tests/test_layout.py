"""Per-stage writers and the grind (layout-fix) stage, against the mocked CLI."""
import contextlib
import copy
import io
import os
from unittest import mock

from explainer.pipeline import describe, execute
from explainer.stages import ORDER, REGISTRY
from explainer.stages.layout import Probe, intent_errors
from explainer.stages.qa import writer_report
from explainer.util import read_json, write_json
from explainer.writer import read_metas, stage_cfg, stage_writer_name, writer_identity

from test_writer import FakeClaudeCase


class StageWriterTests(FakeClaudeCase):
    def test_stage_writer_selection(self):
        cfg = self.cfg(grind="grok", grok_bin=str(self.bin))
        self.assertEqual([stage_writer_name(cfg, s) for s in ("research", "script", "plan", "layout")],
                         ["claude", "claude", "claude", "grok"])
        cfg["llm"]["stage_writers"] = {"script": "grok"}
        self.assertEqual(stage_writer_name(cfg, "script"), "grok")
        self.assertEqual(stage_writer_name(self.cfg(), "layout"), "off")  # grind is off by default
        sc = stage_cfg(self.cfg(grind="grok", grind_timeout=99, grind_effort="medium", grind_retries=3), "layout")
        self.assertEqual((sc["llm"]["timeout"], sc["llm"]["grok_effort"], sc["llm"]["retries"]),
                         (99, "medium", 3))
        self.assertEqual(writer_identity(self.cfg(grind="grok", grok_bin=str(self.bin)), "layout"),
                         "grok:grok-4.7@medium")
        self.assertEqual(writer_identity(self.cfg(grind="grok"), "plan"), "claude:opus")

    def test_grind_tag_and_describe(self):
        ctx = self.ctx(self.cfg(grind="grok", grok_bin=str(self.bin)))
        self.assertEqual(ctx.common.name, "common")  # Claude's writing is shared with the plain build
        self.assertTrue(ctx.variant.endswith("-grokfix"))
        self.assertIn("(Grok", describe(ctx, REGISTRY["layout"]))
        self.assertFalse(self.ctx(self.cfg()).variant.endswith("fix"))

    def test_intent_errors(self):
        sc = {"id": "s", "concept": "c", "actors": [{"id": "a", "kind": "label", "at": [1, 2],
                                                      "params": {"text": "Hi"}}],
              "beats": [{"do": "enter", "target": "a", "at": 0}, {"do": "pulse", "target": "a", "at": 1}]}
        ok = copy.deepcopy(sc)
        ok["actors"][0]["at"] = [5, 6]
        ok["beats"].insert(1, {"do": "exit", "target": "a", "at": 0.5})
        self.assertEqual(intent_errors(sc, ok), [])
        for change in (lambda s: s["actors"][0]["params"].update(text="Hello"),
                       lambda s: s["actors"][0].update(kind="gauge"),
                       lambda s: s.update(concept="other"),
                       lambda s: s["beats"].reverse(),
                       lambda s: s["beats"].append({"do": "pulse", "target": "a"}),
                       lambda s: s["actors"].append({"id": "b", "kind": "label"})):
            bad = copy.deepcopy(sc)
            change(bad)
            self.assertTrue(intent_errors(sc, bad), bad)


class LayoutStageTests(FakeClaudeCase):
    def prepare(self, **llm):
        ctx = self.ctx(self.cfg(grok_bin=str(self.bin), **llm))
        with contextlib.redirect_stderr(io.StringIO()):
            self.run_until_plan(ctx)
        plan = read_json(ctx.common / "plan.json")
        sc = plan["scenes"][0]  # force an overlap: every actor in the same spot
        for a in sc["actors"]:
            a["at"] = [960, 500]
            a["scale"] = 3
        write_json(ctx.common / "plan.json", plan)
        timing = {"scenes": [{"id": s["id"], "duration": 6.0, "sentences": [
            {"text": "x", "start": 0.5 + 2 * i, "end": 2.0 + 2 * i} for i in range(2)]} for s in plan["scenes"]]}
        (ctx.common / "voice").mkdir(exist_ok=True)
        write_json(ctx.common / "voice" / "timing.json", timing)
        return ctx, plan

    def run_layout(self, ctx):
        err = io.StringIO()
        with mock.patch.object(REGISTRY["voice"], "run"), contextlib.redirect_stderr(err):
            self.assertTrue(REGISTRY["layout"].run(ctx) is None)
        return read_json(ctx.common / "layout.meta.json"), err.getvalue()

    def test_off_copies_the_plan(self):
        ctx, plan = self.prepare()
        meta, _ = self.run_layout(ctx)
        self.assertEqual(read_json(ctx.common / "plan.fixed.json"), plan)
        self.assertEqual(meta["writer"], "off")
        self.assertGreater(meta["issues_before"], 0)
        self.assertNotIn("layout", [c["task"] for c in self.calls()])

    def test_grok_fix_is_rechecked_and_kept_only_if_better(self):
        ctx, plan = self.prepare(grind="grok", grind_retries=1)
        n0 = sum(map(len, Probe(ctx).issues(plan).values()))
        os.environ["FAKE_LAYOUT_SPREAD"] = "1"
        meta, log = self.run_layout(ctx)
        fixed = read_json(ctx.common / "plan.fixed.json")
        self.assertEqual(meta["writer"], "grok:grok-4.7@medium")
        self.assertEqual(meta["issues_before"], n0)
        self.assertLess(meta["issues_after"], n0)
        self.assertEqual(fixed["scenes"][0]["actors"][0]["scale"], 0.6)
        self.assertEqual(meta["scenes"][0]["sid"], plan["scenes"][0]["id"])
        self.assertIsNotNone(meta["scenes"][0]["cost_usd"])
        argv = [c for c in self.calls() if c["task"] == "layout"][0]["argv"]
        self.assertEqual(argv[argv.index("--reasoning-effort") + 1], "medium")
        self.assertIn("--no-subagents", argv)
        self.assertIn("layout = grok:grok-4.7@medium", "\n".join(writer_report(read_metas(ctx.common))))

    def test_fix_that_breaks_intent_is_rejected(self):
        ctx, plan = self.prepare(grind="grok", grind_retries=1)
        os.environ.update(FAKE_LAYOUT_SPREAD="1", FAKE_LAYOUT_RENAME="1")
        meta, _ = self.run_layout(ctx)
        self.assertEqual(read_json(ctx.common / "plan.fixed.json"), plan)
        self.assertEqual(meta["issues_after"], meta["issues_before"])
        self.assertEqual(meta["scenes"][0]["rounds"], 2)
        self.assertIn("same actors", [c for c in self.calls() if c["task"] == "layout"][1]["argv"][1])

    def test_registered_between_voice_and_timeline(self):
        names = [s.name for s in ORDER]
        self.assertEqual(names[names.index("voice") + 1], "layout")
        self.assertIn("layout", REGISTRY["timeline"].deps)
