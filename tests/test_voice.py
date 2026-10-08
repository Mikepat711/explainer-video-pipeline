"""Voice selection (one config line + machine-local override), presets, and the pace controller."""
import argparse
import contextlib
import io
import json
import os
import subprocess
import tempfile
import urllib.error
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from explainer import localconf
from explainer.config import apply_local, load_config
from explainer.stages.voice import paced_clips
from explainer.cli import _common, _sets
from explainer.tts import (ENGINES, ChatterboxEngine, ElevenLabsEngine, ParlerEngine, TTSEngine, get_engine,
                           resolve_voice, with_voice)
from explainer.util import write_wav

SENTENCES = [["Flip a switch, and electricity reaches you from a power plant far away.",
              "On the way, it is boosted to a very high voltage, then stepped back down."],
             ["The whole grid has to balance supply and demand, second by second, to keep humming."]]


def no_local_config():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EXPLAINER_", "ELEVENLABS_"))}
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

    def test_no_default_narrator_and_max_todd_presets(self):
        cfg = load_config()
        self.assertEqual(cfg["voice"]["use"], "")
        with self.assertRaises(SystemExit) as e:
            resolve_voice(cfg)
        self.assertIn("--voice elevenlabs:max or --voice elevenlabs:todd", str(e.exception))
        for name, vid, speed in (("max", "Gfpl8Yo74Is0W6cPUWWT", 1.08), ("todd", "g14YnDYCsy3k7XLlcKlO", 0.8)):
            v = resolve_voice(with_voice(cfg, f"elevenlabs:{name}"))
            eng = ElevenLabsEngine(dict(cfg, voice=v))
            self.assertEqual((eng.voice_id, eng.speed, eng.settings["stability"], eng.settings["style"], v["target_wpm"]),
                             (vid, speed, 0.4, 0.2, 0))
        m = resolve_voice(with_voice(cfg, "elevenlabs:marie"))
        self.assertEqual((m["speed"], ElevenLabsEngine(dict(cfg, voice=m)).voice_id), (1.1, "wsL2AB1kHVzgox3WvQP2"))
        self.assertNotIn("jessica", cfg["voice"]["elevenlabs"]["voices"])
        self.assertEqual(cfg["voice"]["fallback"], "kokoro:af_heart")
        a = resolve_voice(with_voice(cfg, "elevenlabs:Arabella"))  # any capitalisation finds the preset
        self.assertEqual((a["spec"], a["speed"]), ("elevenlabs:arabella", 0.95))  # per-voice preset wins
        self.assertEqual(ElevenLabsEngine(dict(cfg, voice=a)).voice_id, "Z3R5wn05IrDiVCyEkUrK")
        river = resolve_voice(with_voice(cfg, "elevenlabs:river"))
        self.assertEqual((river["speed"], river["target_wpm"]), (0.85, 0))
        self.assertEqual(ElevenLabsEngine(dict(cfg, voice=river)).voice_id, "SAz9YHcvj6GT2YYXdXww")
        self.assertEqual(cfg["voice"]["fallback"], "kokoro:af_heart")

    def test_every_mapped_elevenlabs_name_resolves(self):
        cfg = load_config()
        voices = cfg["voice"]["elevenlabs"]["voices"]
        self.assertIn("arabella", voices)
        for name, vid in voices.items():
            for spelled in (name, name.title(), name.upper()):
                v = resolve_voice(with_voice(cfg, f"elevenlabs:{spelled}"))
                self.assertEqual((v["engine"], v["elevenlabs_voice"], v["target_wpm"]), ("elevenlabs", name, 0))
                self.assertEqual(ElevenLabsEngine(dict(cfg, voice=v)).voice_id, vid)
        raw = resolve_voice(with_voice(cfg, "elevenlabs:AbCdEfGhIj0123456789"))
        self.assertEqual(ElevenLabsEngine(dict(cfg, voice=raw)).voice_id, "AbCdEfGhIj0123456789")
        with self.assertRaises(SystemExit) as e:
            resolve_voice(with_voice(cfg, "elevenlabs:mari"))
        self.assertIn("marie", str(e.exception))

    def test_af_heart_keeps_its_natural_pace(self):
        cfg = load_config()
        v = resolve_voice(with_voice(cfg, "kokoro:af_heart"))
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
        self.assertEqual(resolve_voice(with_voice(cfg, "elevenlabs:max"), speed=1.0)["speed"], 1.0)

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
            self.assertEqual(load_config(local=False)["voice"]["use"], "")

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


FAKE_KEY = "test-key-not-real-123"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class ElevenLabsTests(unittest.TestCase):
    """The ElevenLabs engine: request shape, key handling, the billing cache, and the Kokoro fallback."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.mp3 = Path(cls.dir.name) / "tone.mp3"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=1.2",
                        "-ac", "1", "-c:a", "libmp3lame", str(cls.mp3)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def setUp(self):
        p = no_local_config()
        p.start()
        self.addCleanup(p.stop)
        engines = mock.patch.dict(ENGINES, {"fake": FakeEngine})
        engines.start()
        self.addCleanup(engines.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        vd = mock.patch("explainer.tts.VOICE_DIR", Path(self.tmp.name) / "voices")
        vd.start()
        self.addCleanup(vd.stop)
        self.cfg = load_config()
        self.cfg["voice"]["use"] = "elevenlabs:marie"  # no repo default; a voice without its own stability/style
        self.cfg["voice"]["fallback"] = "fake:x"
        self.cfg["voice"]["presets"]["fake:x"] = {"speed": 1.0, "target_wpm": 0}
        self.cfg["voice"]["elevenlabs"]["retries"] = 0
        self.requests = []

    def ok(self, req, timeout=None):
        self.requests.append(req)
        return FakeResponse(self.mp3.read_bytes())

    def pace(self, cache="c"):
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            clips, info = paced_clips(self.cfg, SENTENCES, 24000, Path(self.tmp.name) / cache)
        return clips, info, log.getvalue()

    def test_request_uses_key_header_model_and_voice_settings(self):
        os.environ["ELEVENLABS_API_KEY"] = FAKE_KEY
        with mock.patch("urllib.request.urlopen", side_effect=self.ok):
            clips, info, log = self.pace()
        self.assertEqual(len(self.requests), 3)
        req = self.requests[0]
        self.assertIn("/v1/text-to-speech/wsL2AB1kHVzgox3WvQP2?output_format=mp3_44100_128", req.full_url)
        self.assertEqual(req.get_header("Xi-api-key"), FAKE_KEY)
        body = json.loads(req.data)
        self.assertEqual(body["model_id"], "eleven_multilingual_v2")
        self.assertEqual(body["voice_settings"]["speed"], 1.1)  # the marie preset
        self.assertEqual(body["voice_settings"]["style"], 0.0)
        self.assertEqual(info["engine"]["engine"], "elevenlabs")
        self.assertNotIn("fallback", info)
        self.assertEqual([len(g) for g in clips], [2, 1])
        self.assertNotIn(FAKE_KEY, log)
        self.assertIn("characters billed", log)

    def test_text_is_spelled_out_before_it_is_sent(self):
        os.environ["ELEVENLABS_API_KEY"] = FAKE_KEY
        with mock.patch("urllib.request.urlopen", side_effect=self.ok), contextlib.redirect_stderr(io.StringIO()):
            paced_clips(self.cfg, [["The line runs at 400,000 V."]], 24000, Path(self.tmp.name) / "n")
        self.assertIn("four hundred thousand volts", json.loads(self.requests[0].data)["text"])

    def test_cache_survives_a_cleaned_build_so_nothing_is_billed_twice(self):
        os.environ["ELEVENLABS_API_KEY"] = FAKE_KEY
        with mock.patch("urllib.request.urlopen", side_effect=self.ok):
            self.pace("first")
            self.pace("second")  # a fresh build folder: the voice cache still has every sentence
        self.assertEqual(len(self.requests), 3)
        self.cfg["voice"]["elevenlabs"]["stability"] = 0.7  # different settings are a different take
        with mock.patch("urllib.request.urlopen", side_effect=self.ok):
            self.pace("third")
        self.assertEqual(len(self.requests), 6)

    def test_key_file_and_named_or_raw_voice_ids(self):
        f = Path(self.tmp.name) / "elevenlabs.env"
        f.write_text(f"# ElevenLabs\nELEVENLABS_API_KEY={FAKE_KEY}\n")
        os.environ["EXPLAINER_ELEVENLABS_KEY_FILE"] = str(f)
        self.assertTrue(ElevenLabsEngine.available())
        self.assertEqual(get_engine(with_voice(self.cfg, "elevenlabs:Brian")).voice_id, "nPczCjzI2devNBz1zQrb")
        self.assertEqual(get_engine(with_voice(self.cfg, "elevenlabs:abc123")).voice_id, "abc123")

    def test_missing_key_falls_back_with_a_warning(self):
        os.environ["EXPLAINER_ELEVENLABS_KEY_FILE"] = str(Path(self.tmp.name) / "missing.env")
        with mock.patch("urllib.request.urlopen", side_effect=self.ok):
            _, info, log = self.pace()
        self.assertEqual(self.requests, [])
        self.assertEqual((info["engine"]["engine"], info["fallback"]), ("fake", "no API key"))
        self.assertIn("WARNING", log)

    def test_quota_error_redoes_the_whole_narration_with_the_fallback(self):
        os.environ["ELEVENLABS_API_KEY"] = FAKE_KEY
        calls = []

        def quota(req, timeout=None):
            calls.append(req)
            if len(calls) == 1:
                return FakeResponse(self.mp3.read_bytes())
            body = io.BytesIO(json.dumps({"detail": {"status": "quota_exceeded", "message": "out of credits"}}).encode())
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, body)

        with mock.patch("urllib.request.urlopen", side_effect=quota):
            clips, info, log = self.pace()
        self.assertEqual(len(calls), 2)  # quota errors are not retried
        self.assertEqual(info["engine"]["engine"], "fake")  # one voice for the whole video
        self.assertIn("quota_exceeded", info["fallback"])
        self.assertIn("WARNING", log)
        self.assertEqual([len(g) for g in clips], [2, 1])

    def test_voice_flag_overrides_the_machine_setting(self):
        p = argparse.ArgumentParser()
        _common(p)
        args = p.parse_args(["topic", "--voice", "elevenlabs:george"])
        os.environ["EXPLAINER_VOICE"] = "kokoro:bm_fable"
        self.assertEqual(load_config(sets=_sets(args))["voice"]["use"], "elevenlabs:george")


if __name__ == "__main__":
    unittest.main()
