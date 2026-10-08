"""Claude writer, research/script/plan stages and the fallback path, against a mocked Claude CLI."""
import contextlib
import functools
import io
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from explainer import cli
from explainer.claude import ClaudeError, ClaudeUnavailable, ClaudeWriter, GrokWriter, extract_json
from explainer.config import load_config
from explainer.pipeline import Context, execute
from explainer.plan.checks import check_plan, check_script
from explainer.plan.prompts import plan_prompt, research_prompt
from explainer.plan.schemas import PLAN, RESEARCH, SCRIPT
from explainer.schema import validate
from explainer.scriptfmt import parse_script
from explainer.stages import ORDER, REGISTRY
from explainer.stages.qa import writer_report
from explainer.util import read_json
from explainer.writer import get_writer, read_metas

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures" / "claude"
TOPIC = "test grid lesson"
WIKI = ("https://en.wikipedia.org/wiki/Electrical_grid", (HERE / "fixtures" / "wiki_grid.txt").read_text())


class FakeClaudeCase(unittest.TestCase):
    """Each test gets a temp dir, an executable fake `claude`, and no machine-local settings."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="explainer-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.state = self.tmp / "state"
        self.bin = self.tmp / "bin" / "claude"
        self.bin.parent.mkdir()
        self.bin.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{HERE / "fake_claude.py"}" "$@"\n')
        self.bin.chmod(self.bin.stat().st_mode | stat.S_IXUSR)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("EXPLAINER_", "FAKE_CLAUDE_"))}
        env.update(EXPLAINER_CONFIG=str(self.tmp / "no-local-config"), FAKE_CLAUDE_STATE=str(self.state))
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        sleeper = mock.patch("explainer.claude.time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def mode(self, mode: str, tasks: str = "") -> None:
        os.environ["FAKE_CLAUDE_MODE"] = mode
        os.environ["FAKE_CLAUDE_TASKS"] = tasks

    def cfg(self, **llm) -> dict:
        cfg = load_config()
        cfg["llm"].update({"claude_bin": str(self.bin), "retries": 1, "timeout": 30, **llm})
        cfg["length"].update(target_seconds=30, words_per_minute=140)
        return cfg

    def calls(self) -> list[dict]:
        f = self.state / "calls.jsonl"
        return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []

    def ctx(self, cfg) -> Context:
        return Context(topic=TOPIC, cfg=cfg, build_root=self.tmp / "build", out_root=self.tmp / "out")

    def run_until_plan(self, ctx) -> list[str]:
        ran = []
        for stg in ORDER:
            if execute(ctx, stg, REGISTRY):
                ran.append(stg.name)
            if stg.name == "plan":
                return ran


class GrokWriterTests(FakeClaudeCase):
    """The Grok Build writer: same prompts and checks, its own command line and envelope."""

    def gcfg(self, **llm):
        return self.cfg(writer="grok", grok_bin=str(self.bin), **llm)

    def test_selected_by_config_and_headless_command(self):
        writer, _ = get_writer(self.gcfg())
        self.assertIsInstance(writer, GrokWriter)
        prompt = research_prompt("how the grid works", [])
        brief, meta = writer.generate("research", prompt, RESEARCH, web=True)
        self.assertEqual(brief["topic"], "how the electrical grid works")
        self.assertEqual((meta["writer"], meta["cost_usd"]), ("grok:grok-4.7", 0.02))
        call = self.calls()[0]
        argv = call["argv"]
        self.assertEqual(argv[argv.index("-p") + 1], prompt)  # the prompt is passed unchanged
        self.assertEqual(argv[argv.index("-m") + 1], "grok-4.7")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "auto")
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        self.assertIn("run_terminal_command", argv[argv.index("--disallowed-tools") + 1])
        self.assertNotIn("web_search", argv[argv.index("--disallowed-tools") + 1])
        self.assertNotIn("--disable-web-search", argv)
        self.assertIn("Bash", argv)
        self.assertIn("Do not run shell commands", argv[argv.index("--rules") + 1])
        self.assertTrue(call["stdin_empty"])
        self.assertNotEqual(Path(call["cwd"]).resolve(), Path.cwd().resolve())

    def test_no_web_tools_without_web(self):
        GrokWriter(self.gcfg()).generate("script", "TASK: script\n", SCRIPT)
        argv = self.calls()[0]["argv"]
        self.assertIn("--disable-web-search", argv)
        self.assertIn("web_search", argv[argv.index("--disallowed-tools") + 1])

    def test_fenced_retry_and_auth_handling(self):
        self.mode("fenced")
        payload, _ = GrokWriter(self.gcfg()).generate("research", "TASK: research\n", RESEARCH)
        self.assertEqual(len(payload["key_concepts"]), 3)
        self.mode("error-once")
        os.environ["FAKE_CLAUDE_STATE"] = str(self.tmp / "state2")
        _, meta = GrokWriter(self.gcfg()).generate("research", "TASK: research\n", RESEARCH)
        self.assertEqual([a["ok"] for a in meta["attempts"]], [False, True])
        self.assertIn("grok error", meta["attempts"][0]["error"])
        self.mode("auth-stderr")
        with self.assertRaises(ClaudeUnavailable):
            GrokWriter(self.gcfg(retries=3)).generate("script", "TASK: script\n", SCRIPT)

    def test_missing_cli_and_flags(self):
        writer, reason = get_writer(self.cfg(writer="grok", grok_bin=str(self.tmp / "nope" / "grok")))
        self.assertIsNone(writer)
        self.assertIn("Grok Build CLI not found", reason)
        os.environ["EXPLAINER_WRITER"] = "grok"
        self.assertEqual(load_config()["llm"]["writer"], "grok")
        args = cli.argparse.ArgumentParser()
        cli._common(args)
        ns = args.parse_args(["topic", "--writer", "claude"])
        self.assertEqual(load_config(sets=cli._sets(ns))["llm"]["writer"], "claude")

    def test_stages_record_grok_and_keep_separate_build_folders(self):
        claude_ctx = self.ctx(self.cfg())
        grok_ctx = self.ctx(self.gcfg())
        self.assertEqual(grok_ctx.common.name, "common-grok")
        self.assertTrue(grok_ctx.variant.endswith("-grok"))
        self.assertEqual(claude_ctx.common.name, "common")
        from explainer.pipeline import describe
        self.assertIn("(Grok;", describe(grok_ctx, REGISTRY["research"]))
        self.assertIn("(Claude;", describe(claude_ctx, REGISTRY["research"]))
        self.run_until_plan(grok_ctx)
        metas = read_metas(grok_ctx.common)
        self.assertEqual({m["writer"] for m in metas}, {"grok:grok-4.7"})
        self.assertFalse(any(m["fallback"] for m in metas))
        self.assertFalse(claude_ctx.common.exists())
        self.assertIn("grok:grok-4.7", "\n".join(writer_report(metas)))


class ClaudeWriterTests(FakeClaudeCase):
    def test_success_and_headless_command(self):
        writer = ClaudeWriter(self.cfg())
        brief, meta = writer.generate("research", research_prompt("how the grid works", []), RESEARCH, web=True)
        self.assertEqual(brief["topic"], "how the electrical grid works")
        self.assertEqual((meta["writer"], len(meta["attempts"]), meta["duration_ms"]), ("claude:opus", 1, 1234))
        call = self.calls()[0]
        argv = call["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "opus")
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        self.assertIn("WebSearch,WebFetch", argv)
        self.assertIn("Bash,Edit,Write,NotebookEdit", argv)
        self.assertTrue(call["stdin_empty"])
        self.assertNotEqual(Path(call["cwd"]).resolve(), Path.cwd().resolve())

    def test_fenced_reply_is_accepted(self):
        self.mode("fenced")
        payload, _ = ClaudeWriter(self.cfg()).generate("research", "TASK: research\n", RESEARCH)
        self.assertEqual(len(payload["key_concepts"]), 3)
        self.assertEqual(extract_json('Sure:\n{"a": 1}\nDone.'), {"a": 1})

    def test_retries_after_is_error(self):
        self.mode("error-once")
        _, meta = ClaudeWriter(self.cfg()).generate("research", "TASK: research\n", RESEARCH)
        self.assertEqual([a["ok"] for a in meta["attempts"]], [False, True])
        self.assertIn("is_error", meta["attempts"][0]["error"])

    def test_invalid_reply_is_repaired_with_feedback(self):
        self.mode("invalid-once")
        script = json.loads((FIX / "script.json").read_text())
        writer = ClaudeWriter(self.cfg())
        plan, meta = writer.generate("plan", plan_prompt(TOPIC, script, {}, True, "16:9"), PLAN,
                                     check=lambda p: check_plan(p, script))
        self.assertEqual(check_plan(plan, script), [])
        self.assertEqual([c["repair"] for c in self.calls()], [False, True])
        self.assertIn("ghost", meta["attempts"][0]["error"])

    def test_gives_up_after_retries(self):
        self.mode("error-always")
        with self.assertRaises(ClaudeError) as cm:
            ClaudeWriter(self.cfg(retries=2)).generate("script", "TASK: script\n", SCRIPT)
        self.assertNotIsInstance(cm.exception, ClaudeUnavailable)
        self.assertEqual(len(self.calls()), 3)

    def test_timeout_kills_the_call(self):
        self.mode("timeout")
        t0 = time.time()
        with self.assertRaises(ClaudeError) as cm:
            ClaudeWriter(self.cfg(timeout=1.0, retries=0)).generate("research", "TASK: research\n", RESEARCH)
        self.assertLess(time.time() - t0, 15)
        self.assertIn("no reply within", str(cm.exception))

    def test_signed_out_skips_retries(self):
        for mode in ("auth", "auth-stderr"):
            self.mode(mode)
            with self.assertRaises(ClaudeUnavailable):
                ClaudeWriter(self.cfg(retries=3)).generate("script", "TASK: script\n", SCRIPT)
        self.assertEqual(len(self.calls()), 2)

    def test_missing_or_disabled_cli_is_unavailable(self):
        writer, reason = get_writer(self.cfg(claude_bin=str(self.tmp / "nope" / "claude")))
        self.assertIsNone(writer)
        self.assertIn("not found", reason)
        writer, reason = get_writer(self.cfg(writer="off"))
        self.assertIsNone(writer)
        self.assertIn("disabled", reason)

    def test_local_config_sets_model_and_binary(self):
        local = self.tmp / "local-config"
        local.write_text(f"# machine-local\nEXPLAINER_LLM_MODEL=sonnet\nexport EXPLAINER_CLAUDE_BIN='{self.bin}'\n"
                         "EXPLAINER_VOICE=kokoro:bm_george  # British\n")
        os.environ["EXPLAINER_CONFIG"] = str(local)
        cfg = load_config()
        self.assertEqual((cfg["llm"]["model"], cfg["llm"]["claude_bin"]), ("sonnet", str(self.bin)))
        self.assertEqual(cfg["voice"]["use"], "kokoro:bm_george")
        os.environ["EXPLAINER_LLM_MODEL"] = "opus"
        writer = ClaudeWriter(load_config())
        cmd = writer.command("TASK: plan\n", web=False)
        self.assertEqual(cmd[cmd.index("--model") + 1], "opus")
        self.assertNotIn("--allowedTools", cmd)
        self.assertEqual(load_config(sets=["llm.model=haiku"])["llm"]["model"], "haiku")


class WriterStageTests(FakeClaudeCase):
    def test_until_plan_with_claude_then_cached(self):
        ctx = self.ctx(self.cfg())
        self.assertEqual(self.run_until_plan(ctx), ["research", "script", "plan"])
        c = ctx.common
        self.assertEqual(read_json(c / "research.json")["mode"], "claude")
        script = read_json(c / "script.json")
        self.assertEqual(validate(script, SCRIPT), [])
        self.assertEqual(check_script(script, (60, 84)), [])
        parsed = parse_script((c / "script.md").read_text())
        self.assertEqual([s["sentences"] for s in parsed["scenes"]], [s["sentences"] for s in script["scenes"]])
        plan = read_json(c / "plan.json")
        self.assertEqual([s["id"] for s in plan["scenes"]], ["spin", "step-up", "balance"])
        self.assertIn("rpm", (c / "plan.md").read_text())
        metas = read_metas(c)
        self.assertEqual([(m["stage"], m["writer"], m["fallback"]) for m in metas],
                         [("research", "claude:opus", False), ("script", "claude:opus", False),
                          ("plan", "claude:opus", False)])
        n = len(self.calls())
        self.assertEqual(self.run_until_plan(self.ctx(self.cfg())), [])
        self.assertEqual(len(self.calls()), n)
        self.assertEqual(self.run_until_plan(self.ctx(self.cfg(model="sonnet"))), ["research", "script", "plan"])

    def test_cli_runs_only_the_writer_stages(self):
        os.environ["EXPLAINER_CLAUDE_BIN"] = str(self.bin)
        build = functools.partial(Context, build_root=self.tmp / "build", out_root=self.tmp / "out")
        err = io.StringIO()
        with mock.patch.object(cli, "Context", build), contextlib.redirect_stderr(err):
            rc = cli.main(["run", TOPIC, "--until", "plan", "--set", "length.target_seconds=30",
                           "--set", "length.words_per_minute=140"])
        self.assertEqual(rc, 0)
        common = self.tmp / "build" / "test-grid-lesson" / "common"
        self.assertTrue((common / "plan.json").exists())
        self.assertFalse((common / "voice").exists())
        self.assertIn("llm.claude_bin=", err.getvalue())
        self.assertNotIn("UNAVAILABLE", err.getvalue())

    def test_full_run_without_a_narrator_stops_before_any_writer_call(self):
        os.environ["EXPLAINER_CLAUDE_BIN"] = str(self.bin)
        build = functools.partial(Context, build_root=self.tmp / "build", out_root=self.tmp / "out")
        with mock.patch.object(cli, "Context", build), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as e:
            cli.main(["run", TOPIC])
        self.assertIn("--voice elevenlabs:max or --voice elevenlabs:todd", str(e.exception))
        self.assertEqual(self.calls(), [])

    def test_fallback_warns_loudly_and_flags_qa(self):
        cfg = self.cfg(claude_bin=str(self.tmp / "missing" / "claude"))
        cfg["length"].update(target_seconds=150, words_per_minute=140)
        err = io.StringIO()
        with mock.patch("explainer.sources.wikipedia_extract", return_value=WIKI), contextlib.redirect_stderr(err):
            self.run_until_plan(self.ctx(cfg))
        self.assertEqual(err.getvalue().count("CLAUDE WRITER UNAVAILABLE"), 3)
        c = self.ctx(cfg).common
        metas = read_metas(c)
        self.assertTrue(all(m["fallback"] and m["writer"] == "offline" for m in metas))
        self.assertIn("wikipedia.org", metas[0]["sources"][0])
        script, plan = read_json(c / "script.json"), read_json(c / "plan.json")
        self.assertGreaterEqual(len(script["scenes"]), 4)
        self.assertEqual([e for e in check_script(script, (0, 10_000))], [])
        self.assertNotIn("two-minute", json.dumps(script).lower())
        self.assertEqual(validate(plan, PLAN) + check_plan(plan, script), [])
        report = "\n".join(writer_report(metas))
        self.assertIn("WARNING: FALLBACK WRITER USED for research, script, plan", report)
        self.assertIn("not found", report)
        self.assertIn("research = claude:opus", "\n".join(writer_report(
            [{"stage": "research", "writer": "claude:opus", "fallback": False}])))

    def test_fallback_is_retried_once_claude_answers(self):
        self.mode("error-always")
        cfg = self.cfg(retries=0)
        with mock.patch("explainer.sources.wikipedia_extract", return_value=WIKI), \
                contextlib.redirect_stderr(io.StringIO()):
            self.run_until_plan(self.ctx(cfg))
        self.assertTrue(read_metas(self.ctx(cfg).common)[0]["fallback"])
        self.mode("ok")
        with contextlib.redirect_stderr(io.StringIO()):
            ran = self.run_until_plan(self.ctx(cfg))
        self.assertEqual(ran, ["research", "script", "plan"])
        self.assertFalse(any(m["fallback"] for m in read_metas(self.ctx(cfg).common)))


if __name__ == "__main__":
    unittest.main()
