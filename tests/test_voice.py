"""Voice selection (one config line + machine-local override), presets, and the pace controller."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from explainer import localconf
from explainer.config import apply_local, load_config
from explainer.stages.voice import paced_clips
from explainer.tts import ENGINES, ChatterboxEngine, ParlerEngine, TTSEngine, resolve_voice, with_voice
from explainer.util import write_wav

SENTENCES = [["Flip a switch, and electricity reaches you from a power plant far away.",
              "On the way, it is boosted to a very high voltage, then stepped back down."],
             ["The whole grid has to balance supply and demand, second by second, to keep humming."]]


def no_local_config():
    env = {k: v for k, v in os.environ.items() if not k.startswith("EXPLAINER_")}
    env["EXPLAINER_CONFIG"] = "/nonexistent/explainer-config"
    return mock.patch.dict(os.environ, env, clear=True)


class FakeEngine(TTSEngine):
    """Speaks `rate` words per minute at speed 1.0 (noise bursts, so silence trimming has edges)."""
    name = "fake"
    speed_param = "speed"
    calls = 0

    def __init__(self, cfg):
        v = cfg["voice"]
        self.rate, self.speed = float(v.get("rate", 150)), float(v.get("speed", 1.0))

    @staticmethod
    def available(cfg=None):
        return True

    def identity(self):
        return {"engine": self.name, "rate": self.rate, "speed": self.speed}

    def synthesize(self, text, out_wav):
        FakeEngine.calls += 1
        sr = 24000
        seconds = len(text.split()) / (self.rate * self.speed) * 60
        rng = np.random.default_rng(len(text))
        write_wav(Path(out_wav), (0.3 * rng.standard_normal(int(seconds * sr))).astype(np.float32), sr)


class FixedSpeedEngine(FakeEngine):
    name = "fixed"
    speed_param = ""


class VoiceConfigTests(unittest.TestCase):
    def setUp(self):
        p = no_local_config()
        p.start()
        self.addCleanup(p.stop)

    def test_repo_default_is_af_heart_at_its_natural_pace(self):
        cfg = load_config()
        self.assertEqual(cfg["voice"]["use"], "kokoro:af_heart")
        v = resolve_voice(cfg)
        self.assertEqual((v["engine"], v["kokoro_voice"], v["speed"]), ("kokoro", "af_heart", 0.85))
        self.assertEqual(v["target_wpm"], 0)  # never re-paced or time-stretched
        self.assertEqual(resolve_voice(with_voice(cfg, "kokoro:af_bella"))["target_wpm"], 165)

    def test_every_preset_is_selectable(self):
        cfg = load_config()
        speeds = {"kokoro:af_bella": 0.88, "kokoro:bm_george": 0.96, "kokoro:bm_fable": 0.85,
                  "kokoro:am_michael": 0.96}
        for spec, speed in speeds.items():
            v = resolve_voice(with_voice(cfg, spec))
            self.assertEqual((v["kokoro_voice"], v["speed"]), (spec.split(":")[1], speed))
        for spec in cfg["voice"]["presets"]:
            self.assertIn(resolve_voice(with_voice(cfg, spec))["engine"], ENGINES)
        cb = ChatterboxEngine(dict(cfg, voice=resolve_voice(with_voice(cfg, "chatterbox"))))
        self.assertEqual((cb.options()["exaggeration"], cb.options()["cfg_weight"]), (0.4, 0.3))
        pa = ParlerEngine(dict(cfg, voice=resolve_voice(with_voice(cfg, "parler:Jon"))))
        self.assertTrue(pa.options()["description"].startswith("Jon's voice is warm"))
        self.assertEqual(resolve_voice(cfg, speed=1.0)["speed"], 1.0)

    def test_machine_local_voice_override(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "config"
            f.write_text("EXPLAINER_REPO=~/src/explainer\nEXPLAINER_VOICE=kokoro:bm_fable  # this machine\n")
            os.environ["EXPLAINER_CONFIG"] = str(f)
            cfg = load_config()
            self.assertEqual(resolve_voice(cfg)["speed"], 0.85)
            self.assertEqual(load_config(sets=["voice.use=kokoro:af_bella"])["voice"]["use"], "kokoro:af_bella")
            os.environ["EXPLAINER_VOICE"] = "chatterbox"
            self.assertEqual(load_config()["voice"]["use"], "chatterbox")
            self.assertEqual(load_config(local=False)["voice"]["use"], "kokoro:af_heart")

    def test_localconf_parsing(self):
        vals = localconf.parse(
            "# comment\n\nexport EXPLAINER_LLM_MODEL=opus\nEXPLAINER_VOICE = 'kokoro:bm_george'  # note\n"
            'EXPLAINER_CLAUDE_BIN="$HOME/bin/claude"\nnot a setting\nEXPLAINER_LLM_TIMEOUT=600\n')
        self.assertEqual(vals["EXPLAINER_LLM_MODEL"], "opus")
        self.assertEqual(vals["EXPLAINER_VOICE"], "kokoro:bm_george")
        self.assertEqual(vals["EXPLAINER_CLAUDE_BIN"], os.path.expandvars("$HOME/bin/claude"))
        cfg = load_config(local=False)
        applied = apply_local(cfg, vals)
        self.assertIn("llm.timeout=600.0", applied)
        with self.assertRaises(SystemExit):
            apply_local(cfg, {"EXPLAINER_LLM_RETRIES": "many"})


class PaceTests(unittest.TestCase):
    def setUp(self):
        p = no_local_config()
        p.start()
        self.addCleanup(p.stop)
        engines = mock.patch.dict(ENGINES, {"fake": FakeEngine, "fixed": FixedSpeedEngine})
        engines.start()
        self.addCleanup(engines.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = load_config()
        self.cfg["voice"]["presets"]["fake:x"] = {"speed": 1.0}

    def pace(self, spec, rate):
        cfg = with_voice(self.cfg, spec)
        cfg["voice"]["rate"] = rate
        return paced_clips(cfg, SENTENCES, 24000, Path(self.tmp.name) / spec.replace(":", "-"))

    def test_preset_speed_kept_when_on_target(self):
        clips, info = self.pace("fake:x", 172)
        self.assertEqual((info["speed"], info["tempo"]), (1.0, 1.0))
        self.assertAlmostEqual(info["wpm"], 165, delta=165 * 0.04)
        self.assertEqual([len(g) for g in clips], [2, 1])

    def test_slow_voice_resynthesized_faster(self):
        _, info = self.pace("fake:x", 140)
        self.assertGreater(info["speed"], 1.0)
        self.assertLess(info["first_pass_wpm"], 150)
        self.assertAlmostEqual(info["wpm"], 165, delta=165 * 0.04)

    def test_engine_without_speed_control_is_time_stretched(self):
        _, info = self.pace("fixed", 215)
        self.assertIsNone(info["speed"])
        self.assertLess(info["tempo"], 1.0)
        self.assertAlmostEqual(info["wpm"], 165, delta=165 * 0.04)

    def test_zero_target_keeps_natural_speed_without_stretching(self):
        self.cfg["voice"]["presets"]["fake:x"] = {"speed": 1.0, "target_wpm": 0}
        for rate in (120, 215):
            _, info = self.pace("fake:x", rate)
            self.assertEqual((info["speed"], info["tempo"], info["target_wpm"]), (1.0, 1.0, None))
            self.assertAlmostEqual(info["speaking_wpm"], rate, delta=rate * 0.08)

    def test_cached_sentences_are_not_resynthesized(self):
        self.pace("fake:x", 172)
        before = FakeEngine.calls
        self.pace("fake:x", 172)
        self.assertEqual(FakeEngine.calls, before)


if __name__ == "__main__":
    unittest.main()
