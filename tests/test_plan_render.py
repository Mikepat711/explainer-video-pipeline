"""Visual-plan renderer: animation model, timeline in plan mode, transitions, stale-output cleanup, frames."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from explainer.config import load_config
from explainer.frames import contact_sheet, estimate_timing, render_frames
from explainer.gfx.model import MAX_VISUAL_RPM, SceneModel, Track, spin_budget
from explainer.gfx.render import make_renderer
from explainer.pipeline import Context, Stage, execute
from explainer.plan.checks import check_plan, normalize_plan
from explainer.plan.prompts import plan_prompt
from explainer.plan.schemas import PLAN
from explainer.plan.vocab import ICONS, KINDS
from explainer.schema import validate
from explainer.scriptfmt import parse_script
from explainer.stages.assemble import transition
from explainer.stages.timeline import plan_scene_duration, plan_timeline
from explainer.util import read_json, write_json

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures" / "claude"
REPO = HERE.parent
GRID = REPO / "topics" / "how-the-electrical-grid-works"


def fixture_plan() -> dict:
    return json.loads((FIX / "plan.json").read_text())


def fixture_script() -> dict:
    return json.loads((FIX / "script.json").read_text())


def scene(actors, beats, **kw) -> dict:
    return {"id": "s", "concept": "c", "mechanism": "m", "visual_cue": "v", "composition": "x",
            "actors": actors, "beats": beats, **kw}


class TrackTests(unittest.TestCase):
    def test_numbers_tween_and_enums_switch_at_the_end(self):
        tr = Track(0.0)
        tr.add(1.0, 2.0, 10.0, "linear")
        self.assertEqual(tr.value(0.5), 0.0)
        self.assertAlmostEqual(tr.value(2.0), 5.0)
        self.assertEqual(tr.value(3.5), 10.0)
        st = Track("closed")
        st.add(1.0, 0.5, "open")
        self.assertEqual(st.value(1.2), "closed")
        self.assertEqual(st.value(1.6), "open")
        self.assertEqual(st.changed_at(2.0), (1.5, "closed"))

    def test_integral_keeps_phase_continuous_through_speed_changes(self):
        tr = Track(60.0)
        self.assertAlmostEqual(tr.integral(2.0), 120.0)
        tr.add(1.0, 1.0, 0.0, "linear")
        self.assertAlmostEqual(tr.integral(1.0), 60.0, places=2)
        self.assertAlmostEqual(tr.integral(2.0), 90.0, places=2)
        self.assertAlmostEqual(tr.integral(5.0), 90.0, places=2)


class SceneModelTests(unittest.TestCase):
    def test_enter_move_and_final_state_for_inherit(self):
        sc = scene([{"id": "r", "kind": "rotor", "at": [100, 100], "params": {"rpm": 60}},
                    {"id": "m", "kind": "meter", "at": [500, 200], "visible": False, "params": {"value": 0}}],
                   [{"at": 1.0, "do": "enter", "target": "m", "anim": "fade", "dur": 0.5},
                    {"at": 1.0, "do": "move", "target": "r", "to": [300, 100], "dur": 1.0, "ease": "linear"},
                    {"at": 2.0, "do": "set", "target": "m", "param": "value", "to": 50, "dur": 1.0}])
        m = SceneModel(sc, spin=1.0)
        r, me = m.actors["r"], m.actors["m"]
        self.assertEqual(me.presence(0.5).alpha, 0.0)
        self.assertEqual(me.presence(2.0).alpha, 1.0)
        self.assertEqual(r.position(1.5), (200.0, 100.0))
        self.assertAlmostEqual(m.last_change(), 3.0)
        final = {s["id"]: s for s in m.final_state(4.0)}
        self.assertEqual(final["r"]["at"], [300, 100])
        self.assertEqual(final["m"]["params"]["value"], 50)
        self.assertTrue(final["m"]["visible"])
        self.assertAlmostEqual(final["r"]["_carry"]["rpm"], 240.0, places=1)
        nxt = SceneModel(scene([], []), base=m.final_state(4.0))
        self.assertAlmostEqual(nxt.actors["r"].phase("rpm", 0.0), 240.0, places=1)

    def test_spin_budget_preserves_ratios(self):
        sc = scene([{"id": "g", "kind": "generator", "params": {"rpm": 3600}}],
                   [{"at": 1, "do": "set", "target": "g", "param": "rpm", "to": 1800}])
        k = spin_budget([sc])
        self.assertAlmostEqual(3600 * k, MAX_VISUAL_RPM)
        self.assertEqual(spin_budget([scene([{"id": "w", "kind": "rotor", "params": {"rpm": 20}}], [])]), 1.0)


class PlanTimelineTests(unittest.TestCase):
    L = {"min_scene": 3.0, "reveal_hold": 1.5, "reading_wpm": 160}

    def timing(self, plan):
        return {sc["id"]: {"duration": 6.0, "sentences": [{"start": 0.5, "end": 2.5}, {"start": 3.0, "end": 5.5}]}
                for sc in plan["scenes"]}

    def test_scenes_resolve_beats_and_follow_the_voice(self):
        plan = fixture_plan()
        out = plan_timeline(plan, self.timing(plan), self.L, 30)
        self.assertEqual([s["id"] for s in out], [s["id"] for s in plan["scenes"]])
        for s in out:
            self.assertGreaterEqual(s["duration"], 6.0)
            self.assertEqual(s["spec"]["engine"], "plan")
            for b in s["spec"]["scene"]["beats"]:
                self.assertIsInstance(b["at"], float)
                self.assertLess(b["at"], s["duration"])
        self.assertEqual(out[1]["transition"], "slide_left")

    def test_late_reveal_stretches_scene_by_at_most_three_seconds(self):
        sc = scene([{"id": "t", "kind": "text", "at": [800, 300], "visible": False, "params": {"text": "hi"}}],
                   [{"at": "e2", "do": "enter", "target": "t"}], hold=0.5)
        sents = [{"start": 0.5, "end": 2.5}, {"start": 3.0, "end": 5.5}]
        self.assertAlmostEqual(plan_scene_duration(sc, 6.0, sents, self.L), 6.5 + 0.5)
        sc["actors"][0]["params"]["text"] = "word " * 60
        self.assertAlmostEqual(plan_scene_duration(sc, 6.0, sents, self.L), 6.5 + 3.0)

    def test_inherit_and_continue_carry_state_and_camera(self):
        plan = fixture_plan()
        a, b = plan["scenes"][0], copy.deepcopy(plan["scenes"][0])
        a["beats"].append({"at": "s1", "do": "camera", "region": [0, 0, 800, 450], "dur": 1})
        b.update(id="again", inherit=a["id"], transition="continue", actors=[], beats=[])
        plan["scenes"] = [a, b]
        out = plan_timeline(plan, self.timing(plan), self.L, 30)
        self.assertEqual({x["id"] for x in out[1]["spec"]["base"]}, {x["id"] for x in a["actors"]})
        self.assertEqual(out[1]["spec"]["camera0"], [0, 0, 800, 450])

    def test_cut_and_continue_are_one_frame_joins(self):
        self.assertEqual(transition({"transition": "cut"}, 0.9, 30), ("fade", round(1 / 30, 4)))
        self.assertEqual(transition({"transition": "continue"}, 0.9, 30)[1], round(1 / 30, 4))
        self.assertEqual(transition({"transition": "slide_left"}, 0.9, 30), ("slideleft", 0.9))
        self.assertEqual(transition({}, 0.9, 30), ("fade", 0.9))


class RendererTests(unittest.TestCase):
    def spec(self, sc, plan):
        return {"engine": "plan", "style": plan["style"], "scene": sc, "base": None, "camera0": None,
                "spin": spin_budget(plan["scenes"])}

    def test_every_fixture_scene_draws_in_both_aspects(self):
        plan, cfg = fixture_plan(), load_config()
        out = plan_timeline(plan, PlanTimelineTests().timing(plan), PlanTimelineTests.L, 30)
        for size in ((480, 270), (270, 480)):
            for s in out:
                r = make_renderer(s["spec"], s["duration"], {"index": 1}, cfg, size)
                surf = r.frame(s["duration"] * 0.7)
                data = bytes(surf.get_data())
                self.assertGreater(len(set(data[::97])), 8, f"{s['id']} looks blank at {size}")
                probe = r.probe(1.0)
                self.assertTrue(probe["boxes"], s["id"])

    def test_readouts_stay_inside_a_zoomed_camera(self):
        plan = fixture_plan()
        sc = scene([{"id": "m", "kind": "meter", "at": [780, 120], "params": {"value": 5, "unit": "V", "size": "l"}}],
                   [], camera=[0, 100, 800, 450])
        r = make_renderer(self.spec(sc, plan), 3.0, {"index": 1}, load_config(), (800, 450))
        r.probe(0.5)
        k, tx, ty = r.view(0.5)
        x, y, s = r._readout(r.model.actors["m"], r.model.actors["m"].params(0.5), 780, 120, 1.0, 0.5)
        self.assertLess(s, 1.0)
        self.assertLess(x, 780)
        self.assertGreater(y, 120)

    def test_kettle_icon_is_in_the_vocabulary(self):
        self.assertIn("kettle", ICONS)
        self.assertIn("kettle", KINDS["icon"].params["name"]["values"])

    def test_lever_bounds_follow_the_arm(self):
        sc = {"id": "s", "actors": [{"id": "arm", "kind": "lever", "at": [800, 400],
                                     "params": {"length": 300, "angle": -90, "width": 20}}],
              "beats": [{"at": 1.0, "do": "set", "target": "arm", "param": "angle", "to": 0, "dur": 1.0}]}
        m = SceneModel(sc)
        x0, y0, x1, y1 = m.bounds(m.actors["arm"], 0.0)
        self.assertLess(x1 - x0, 40)
        self.assertAlmostEqual(y0, 100 - 15, delta=1)
        x0, y0, x1, y1 = m.bounds(m.actors["arm"], 2.5)
        self.assertLess(y1 - y0, 40)
        self.assertAlmostEqual(x1, 1100 + 15, delta=1)


class WriterGuardrailTests(unittest.TestCase):
    def test_prompt_states_hard_limits_and_honest_scale(self):
        text = plan_prompt("how the grid works", fixture_script(), {"key_concepts": []}, True, "16:9")
        self.assertIn("Hard limits", text)
        self.assertIn("exaggerated for illustration", text)
        self.assertIn("load", text)
        self.assertIn("str≤6ch", text)

    def test_unknown_network_node_kinds_are_normalised(self):
        plan = fixture_plan()
        plan["scenes"][0]["actors"].append({"id": "net", "kind": "network", "params": {
            "nodes": [{"id": "a", "at": [100, 100], "kind": "consumer"}, {"id": "b", "at": [300, 100], "kind": "wat"}],
            "edges": [{"from": "a", "to": "b"}]}})
        normalize_plan(plan)
        kinds = [n["kind"] for n in plan["scenes"][0]["actors"][-1]["params"]["nodes"]]
        self.assertEqual(kinds, ["load", "generic"])
        self.assertEqual(validate(plan, PLAN), [])

    def test_pinned_grid_plan_is_valid_and_labels_its_exaggerations(self):
        plan = json.loads((GRID / "plan.json").read_text())
        self.assertEqual(plan["provenance"]["writer"], "claude:opus")
        self.assertEqual(validate(plan, PLAN), [])
        notes = {sc["id"]: [a["params"]["text"] for a in sc["actors"] if a["kind"] == "text"
                            and "xaggerated" in a["params"]["text"]] for sc in plan["scenes"]}
        for sid in ("kettle-moment", "balance-frequency", "heartbeat"):
            self.assertTrue(notes[sid], f"{sid} shows a magnified kettle effect without a label")

    def test_derailleur_example_is_valid_against_its_script(self):
        ex = REPO / "examples" / "how-a-bike-derailleur-works"
        plan = json.loads((ex / "plan.json").read_text())
        script = parse_script((ex / "script.md").read_text())
        self.assertEqual(validate(plan, PLAN), [])
        self.assertEqual(check_plan(plan, script), [])
        self.assertFalse(any(a["kind"] in ("generator", "plant", "network", "powerline")
                             for sc in plan["scenes"] for a in sc["actors"]))


class StaleOutputTests(unittest.TestCase):
    """A shared stage that changes its result clears what its shared dependents built from the old one."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="explainer-stale-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.ctx = Context(topic="stale test", cfg=load_config(), build_root=self.tmp / "build",
                           out_root=self.tmp / "out")
        self.word = "one"
        test = self

        class Up(Stage):
            name, scope = "up", "common"

            def outputs(self, ctx):
                return [ctx.common / "up.txt"]

            def run(self, ctx):
                (ctx.common / "up.txt").write_text(test.word)

        class Down(Stage):
            name, scope, deps, owns = "down", "common", ("up",), ("tracks/*.wav",)

            def outputs(self, ctx):
                return [ctx.common / "down.json"]

            def run(self, ctx):
                write_json(ctx.common / "down.json", {"from": (ctx.common / "up.txt").read_text()})

        class Late(Stage):
            name, scope, deps = "late", "variant", ("down",)

            def outputs(self, ctx):
                return [ctx.vdir / "late.txt"]

            def run(self, ctx):
                ctx.vdir.mkdir(parents=True, exist_ok=True)
                (ctx.vdir / "late.txt").write_text("x")

        self.reg = {s.name: s for s in (Up(), Down(), Late())}

    def test_partial_run_never_leaves_old_dependent_outputs(self):
        for name in ("up", "down", "late"):
            execute(self.ctx, self.reg[name], self.reg)
        c = self.ctx.common
        (c / "tracks").mkdir()
        (c / "tracks" / "old-scene.wav").write_bytes(b"RIFF")
        self.assertEqual(read_json(c / "down.json"), {"from": "one"})
        self.assertFalse(execute(self.ctx, self.reg["up"], self.reg))
        self.assertTrue((c / "down.json").exists())
        self.word = "two"
        execute(self.ctx, self.reg["up"], self.reg, force=True)
        self.assertFalse((c / "down.json").exists())
        self.assertFalse((c / "tracks" / "old-scene.wav").exists())
        self.assertFalse(self.ctx.stamp_path(self.reg["down"]).exists())
        self.assertTrue((self.ctx.vdir / "late.txt").exists())
        execute(self.ctx, self.reg["down"], self.reg)
        self.assertEqual(read_json(c / "down.json"), {"from": "two"})


class FramesTests(unittest.TestCase):
    def test_frames_and_contact_sheet_without_narration(self):
        tmp = Path(tempfile.mkdtemp(prefix="explainer-frames-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        plan, script = fixture_plan(), fixture_script()
        timing = estimate_timing(script)
        self.assertEqual(set(timing), {s["id"] for s in script["scenes"]})
        shots = render_frames(plan, script, load_config(), tmp, (480, 270), 2, timing, None)
        self.assertGreaterEqual(len(shots), len(plan["scenes"]))
        sheet = contact_sheet(shots, tmp / "sheet.jpg", title=script["title"])
        self.assertTrue(sheet.exists() and sheet.stat().st_size > 5000)
        self.assertEqual(check_plan(normalize_plan(plan), script), [])


if __name__ == "__main__":
    unittest.main()
