"""Recorded or generated sound samples (a breaker click, a transformer hum) placed on the timeline next to the
procedural cues. Configured per topic under `audio.samples`; each entry:
  {file, scene, at: "s2+0.3" (same syntax as plan beats; default scene start), gain_db: 0, loop: seconds (repeat
   the sample to fill this long, for beds such as a hum), fade: seconds (fade in/out, default 0.02, longer for beds)}
Samples go on the SFX track, so they get the same level and ducking under narration as the procedural cues."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from ..util import REPO_ROOT, log


def load(path: Path, sr: int) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 2).copy()


def resolve_path(file: str) -> Path:
    p = Path(file).expanduser()
    return p if p.is_absolute() else REPO_ROOT / p


def place(track: np.ndarray, samples: list[dict], scenes: list[dict], sr: int) -> list[str]:
    """Mix each sample into `track` (n, 2) in place; returns one log line per sample."""
    from ..stages.timeline import resolve_time
    by_id = {sc["id"]: sc for sc in scenes}
    notes = []
    for spec in samples or []:
        sc = by_id.get(spec.get("scene", ""))
        path = resolve_path(spec["file"])
        if sc is None or not path.exists():
            notes.append(f"skipped {spec.get('file')} (scene {spec.get('scene')!r} or file missing)")
            continue
        t = sc["start"] + resolve_time(spec.get("at", 0), sc["sentences"], sc["duration"])
        x = load(path, sr) * float(10 ** (spec.get("gain_db", 0) / 20))
        if spec.get("loop"):
            want = int(float(spec["loop"]) * sr)
            x = np.tile(x, (-(-want // len(x)), 1))[:want]
        fade = int(float(spec.get("fade", 0.02)) * sr)
        if fade and len(x) > 2 * fade:
            ramp = np.linspace(0, 1, fade, dtype=np.float32)[:, None]
            x[:fade] *= ramp
            x[-fade:] *= ramp[::-1]
        s = int(round(t * sr))
        if s >= len(track):
            continue
        x = x[: len(track) - s]
        track[s:s + len(x)] += x
        notes.append(f"{path.name} at {t:.2f}s ({len(x) / sr:.1f}s, {spec.get('gain_db', 0):+g} dB)")
    return notes
