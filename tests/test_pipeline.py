import unittest

from explainer.gfx.canvas import Motion, out_back, prog
from explainer.scriptfmt import parse_script, render_script
from explainer.stages.captions import chunk_sentence, ts
from explainer.stages.timeline import on_screen_words, resolve_spec, resolve_time, scene_duration
from explainer.stages.voice import sentence_pause
from explainer.tts import resolve_voice, with_voice
from explainer.util import split_sentences

SENTS = [{"start": 0.5, "end": 2.0}, {"start": 2.3, "end": 4.1}, {"start": 4.4, "end": 6.0}]


class TimelineTests(unittest.TestCase):
    def test_sentence_refs(self):
        self.assertEqual(resolve_time("s2", SENTS, 8.0), 2.3)
        self.assertEqual(resolve_time("s2+0.5", SENTS, 8.0), 2.8)
        self.assertEqual(resolve_time("e1", SENTS, 8.0), 2.0)
        self.assertEqual(resolve_time("end-1.5", SENTS, 8.0), 6.5)
        self.assertEqual(resolve_time(1.25, SENTS, 8.0), 1.25)
        self.assertEqual(resolve_time("s9", SENTS, 8.0), 4.4)

    def test_resolve_nested_and_clamped(self):
        found = []
        spec = resolve_spec({"items": [{"at": "s1"}, {"at": "s3+5"}], "note_at": "s2"}, SENTS, 8.0, found)
        self.assertEqual(spec["items"][0]["at"], 0.5)
        self.assertLessEqual(spec["items"][1]["at"], 7.4)
        self.assertEqual(spec["note_at"], 2.3)
        self.assertEqual(len(found), 3)


class PacingTests(unittest.TestCase):
    L = {"min_scene": 6.0, "reveal_hold": 2.5, "reading_wpm": 160, "sentence_gap": 0.5, "sentence_gap_extra": 0.25}

    def test_min_scene_and_reveal_hold(self):
        self.assertEqual(scene_duration({"heading": "Hi"}, 4.0, SENTS, self.L), 6.0)
        late = {"items": [{"text": "a", "at": "e3"}]}
        self.assertAlmostEqual(scene_duration(late, 7.0, SENTS, self.L), 6.0 + 2.5)

    def test_reading_time_stretches_wordy_scenes(self):
        wordy = {"heading": "word " * 40}
        self.assertAlmostEqual(scene_duration(wordy, 7.0, SENTS, self.L), 40 / 160 * 60 + 1.5)
        self.assertEqual(on_screen_words({"items": ["two words", {"text": "three more words", "icon": "x"}]}), 5)

    def test_sentence_pause_grows_with_length(self):
        short = sentence_pause("That's trilateration.", self.L)
        long = sentence_pause(" ".join(["word"] * 30) + ".", self.L)
        self.assertAlmostEqual(short, 0.524)
        self.assertAlmostEqual(long, 0.75)
        self.assertGreater(sentence_pause("Why does that matter?", self.L), sentence_pause("That matters.", self.L))

    def test_motion_pace_stretches_animations(self):
        Motion.configure({"motion": 2.0, "overshoot": 0.0})
        try:
            self.assertAlmostEqual(prog(1.5, 1.0, 0.5), 0.5)
            self.assertAlmostEqual(prog(1.5, 1.0, 0.5, paced=False), 1.0)
            self.assertLessEqual(max(out_back(i / 50) for i in range(51)), 1.0 + 1e-9)
        finally:
            Motion.configure({})


class VoiceSelectionTests(unittest.TestCase):
    def test_with_voice(self):
        cfg = {"voice": {"use": "kokoro:af_bella", "piper_voice": "x"}}
        k = resolve_voice(with_voice(cfg, "kokoro:am_michael"))
        self.assertEqual((k["engine"], k["kokoro_voice"]), ("kokoro", "am_michael"))
        p = resolve_voice(with_voice(cfg, "piper:en_US-ryan-high"))
        self.assertEqual((p["engine"], p["piper_voice"]), ("piper", "en_US-ryan-high"))
        self.assertEqual(cfg["voice"]["use"], "kokoro:af_bella")


class CaptionTests(unittest.TestCase):
    def test_no_orphans_and_limits(self):
        s = "GPS is a constellation of about thirty-one satellites, orbiting twenty thousand kilometers up."
        cues = chunk_sentence(s, 44, 2)
        self.assertEqual(" ".join(" ".join(c) for c in cues), s)
        for c in cues:
            self.assertLessEqual(len(c), 2)
            for ln in c:
                self.assertLessEqual(len(ln), 48)
        self.assertGreater(min(len(" ".join(c)) for c in cues), 15)

    def test_short_sentence_single_cue(self):
        self.assertEqual(chunk_sentence("That's trilateration.", 44, 2), [["That's trilateration."]])

    def test_timestamp(self):
        self.assertEqual(ts(3723.456), "01:02:03,456")


class ScriptTests(unittest.TestCase):
    def test_roundtrip(self):
        text = render_script("T", "S", [{"id": "hook", "heading": "Hi", "narration": "One. Two!"}])
        sc = parse_script(text)
        self.assertEqual(sc["title"], "T")
        self.assertEqual(sc["scenes"][0]["sentences"], ["One.", "Two!"])

    def test_split_sentences_keeps_abbrev(self):
        self.assertEqual(len(split_sentences("Use e.g. Galileo. Then stop.")), 2)


if __name__ == "__main__":
    unittest.main()
