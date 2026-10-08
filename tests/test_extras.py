"""Word-timed captions and placed sound samples."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from explainer.audio.samples import place
from explainer.stages.captions import build_cues, karaoke
from explainer.util import write_wav
from explainer.wordtime import align

TL = {"scenes": [{"id": "a", "start": 10.0, "duration": 8.0, "sentences": [
    {"text": "One line makes thousands of cans every single minute, all day and all night long.",
     "start": 0.5, "end": 6.5}]}]}


def heard(words, t0=0.5, step=0.4):
    return [{"text": w, "start": t0 + i * step, "end": t0 + (i + 1) * step} for i, w in enumerate(words)]


class WordTimingTests(unittest.TestCase):
    def test_align_tolerates_mismatched_words(self):
        hits = align(["It", "takes", "4", "tonnes."], heard(["It", "takes", "four", "tonnes"]))
        self.assertIsNotNone(hits[0])
        self.assertIsNone(hits[2])
        self.assertAlmostEqual(hits[3][0], 0.5 + 3 * 0.4)

    def test_splits_follow_the_spoken_words_but_sentence_start_stays(self):
        est = build_cues(TL, 30, 1)
        words = TL["scenes"][0]["sentences"][0]["text"].split()
        timed = build_cues(TL, 30, 1, {"a": heard(words, step=0.42)})
        self.assertEqual(len(est), len(timed))
        self.assertGreater(len(timed), 1)
        self.assertEqual(timed[0]["start"], est[0]["start"])
        n0 = len(" ".join(timed[0]["lines"]).split())
        self.assertAlmostEqual(timed[1]["start"], 10.0 + 0.5 + n0 * 0.42, places=2)
        for a, b in zip(timed, timed[1:]):
            self.assertLessEqual(a["end"], b["start"])

    def test_no_words_means_estimated_timing(self):
        self.assertEqual(build_cues(TL, 30, 1, None), build_cues(TL, 30, 1))
        self.assertTrue(all("times" not in c for c in build_cues(TL, 30, 1)))

    def test_karaoke_durations_cover_the_cue(self):
        words = TL["scenes"][0]["sentences"][0]["text"].split()
        cue = build_cues(TL, 44, 2, {"a": heard(words)})[0]
        text = karaoke(cue)
        self.assertEqual(text.count(r"\kf"), len(" ".join(cue["lines"]).split()))
        self.assertEqual(text.count(r"\N"), len(cue["lines"]) - 1)
        self.assertNotIn("{\\kf0}", text)


class SampleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg needed to decode samples")
    def test_samples_land_at_beat_time_and_loop(self):
        tmp = Path(tempfile.mkdtemp(prefix="explainer-samples-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        sr = 8000
        write_wav(tmp / "tick.wav", np.full((sr // 10, 2), 0.5, np.float32), sr)
        track = np.zeros((sr * 20, 2), np.float32)
        notes = place(track, [{"file": str(tmp / "tick.wav"), "scene": "a", "at": "s1+1.0", "fade": 0},
                              {"file": str(tmp / "tick.wav"), "scene": "a", "at": 0, "loop": 2.0, "gain_db": -6,
                               "fade": 0},
                              {"file": str(tmp / "missing.wav"), "scene": "a"}], TL["scenes"], sr)
        self.assertEqual(len(notes), 3)
        self.assertIn("skipped", notes[2])
        at = int((10.0 + 0.5 + 1.0) * sr)
        self.assertGreater(track[at + 10, 0], 0.4)
        self.assertAlmostEqual(float(track[int(11.0 * sr), 0]), 0.5 * 10 ** (-6 / 20), places=2)
        self.assertEqual(float(track[int(13.0 * sr), 0]), 0.0)


if __name__ == "__main__":
    unittest.main()
