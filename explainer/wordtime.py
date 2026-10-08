"""Word-level timestamps for narration, found locally with whisper.cpp (`whisper-cli`), so captions can switch
exactly on word boundaries instead of being spread over a sentence by character count. Costs nothing and needs no
network; anything missing (binary, model, a failed run) just returns None and captions fall back to estimates."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .util import REPO_ROOT, log

MODEL_NAME = "ggml-base.en.bin"


def find_model(cfg_path: str = "") -> Path | None:
    for cand in (cfg_path, os.environ.get("EXPLAINER_WHISPER_MODEL", ""),
                 str(REPO_ROOT / ".cache" / "whisper" / MODEL_NAME)):
        if cand and Path(cand).expanduser().is_file():
            return Path(cand).expanduser()
    return None


def find_binary(cfg_bin: str = "") -> str | None:
    for cand in (cfg_bin, "whisper-cli", "/opt/homebrew/bin/whisper-cli", "whisper-cpp"):
        if cand and (shutil.which(cand) or Path(cand).is_file()):
            return shutil.which(cand) or cand
    return None


def norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def whisper_words(wav: Path, model: Path, binary: str) -> list[dict] | None:
    """[{text, start, end}] in seconds from the start of `wav`; cached next to the model by audio hash."""
    digest = hashlib.sha1(wav.read_bytes() + model.name.encode()).hexdigest()[:16]
    cache = model.parent / "words" / f"{digest}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    cache.parent.mkdir(parents=True, exist_ok=True)
    stem = cache.with_suffix("")
    dtw = model.name.removeprefix("ggml-").removesuffix(".bin")
    # DTW token timestamps track the audio far better than whisper's default ones (which can be ~0.5 s off at
    # sentence starts); DTW needs flash attention off.
    cmd = [binary, "-m", str(model), "-f", str(wav), "-ojf", "-of", str(stem), "-np", "--dtw", dtw, "-nfa"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        data = json.loads(Path(str(stem) + ".json").read_text())
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        log(f"    word timing: whisper failed on {wav.name} ({e}); using estimated caption timing")
        return None
    finally:
        Path(str(stem) + ".json").unlink(missing_ok=True)
    words: list[dict] = []
    for seg in data.get("transcription", []):
        for tok in seg.get("tokens", []):
            text = tok.get("text", "")
            if text.startswith("[_") or not text.strip():
                continue
            t = tok.get("t_dtw", -1)
            t = t / 100 if t is not None and t >= 0 else tok["offsets"]["from"] / 1000
            if text.startswith(" ") or not words:
                words.append({"text": text.strip(), "start": t, "end": t})
            else:
                words[-1]["text"] += text
    words = [w for w in words if norm(w["text"])]
    for a, b in zip(words, words[1:]):
        a["end"] = max(a["start"], b["start"])
    if words:
        words[-1]["end"] = words[-1]["start"] + 0.4
    cache.write_text(json.dumps(words))
    return words


def align(script_words: list[str], heard: list[dict]) -> list[tuple[float, float] | None]:
    """(start, end) for each script word that matches a heard word; None where nothing matched (numbers spoken
    differently, words whisper merged or split). Callers interpolate the gaps."""
    a = [norm(w) for w in script_words]
    b = [norm(h["text"]) for h in heard]
    out: list[tuple[float, float] | None] = [None] * len(a)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            h = heard[blk.b + k]
            out[blk.a + k] = (h["start"], h["end"])
    return out
