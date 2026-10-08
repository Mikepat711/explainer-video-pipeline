"""Optional ASR check of narration against the script, using local whisper.cpp."""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from ..util import log, run
from ..wordtime import find_binary, find_model, norm as norm_word


def _norm_text(s: str) -> list[str]:
    s = s.lower().replace("-", " ").replace("’", "'")
    s = re.sub(r"(\d),(\d)", r"\1\2", s)
    repl = {
        "two million": "2 million", "thirty five": "35",
        "eight one one": "811", "nine one one": "911",
        "fifteen hundred": "1500",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return [w for w in re.findall(r"[a-z0-9']+", s) if w]


def whisper_transcript(media: Path, binary: str, model: Path) -> str | None:
    """Best-effort full transcript from whisper-cli JSON."""
    import json
    import tempfile
    wav = media
    tmp = None
    if media.suffix.lower() != ".wav":
        tmp = Path(tempfile.mkdtemp(prefix="explainer-asr-")) / "audio.wav"
        run(["ffmpeg", "-y", "-v", "error", "-i", str(media), "-ac", "1", "-ar", "16000", str(tmp)])
        wav = tmp
    stem = wav.with_suffix("")
    cmd = [binary, "-m", str(model), "-f", str(wav), "-ojf", "-of", str(stem), "-np"]
    try:
        run(cmd)
        data = json.loads(Path(str(stem) + ".json").read_text())
    except Exception as e:
        log(f"    asr: whisper failed ({e})")
        return None
    finally:
        Path(str(stem) + ".json").unlink(missing_ok=True)
        if tmp:
            tmp.unlink(missing_ok=True)
            tmp.parent.rmdir()
    parts = []
    for seg in data.get("transcription", data.get("transcriptions", [])):
        text = seg.get("text") or ""
        parts.append(text.strip())
    if not parts:
        # token fallback
        for seg in data.get("transcription", []):
            for tok in seg.get("tokens", []):
                t = tok.get("text", "")
                if t.startswith("[_"):
                    continue
                parts.append(t)
    return " ".join(parts).strip() or None


def wer(ref_words: list[str], hyp_words: list[str]) -> tuple[float, int]:
    sm = difflib.SequenceMatcher(None, ref_words, hyp_words, autojunk=False)
    errs = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            errs += max(i2 - i1, j2 - j1)
    return (errs / len(ref_words) if ref_words else 0.0), errs


def asr_check(media: Path, captions: list[str], cfg: dict, want: str = "auto") -> dict | None:
    if want in ("off", "false", "0", ""):
        return None
    caps = cfg.get("captions") or {}
    binary = find_binary(caps.get("whisper_bin") or "")
    model = find_model(caps.get("whisper_model") or "")
    if not binary or not model:
        if want in ("on", "true", "1"):
            return {"skipped": True, "reason": "whisper-cli or model not found"}
        log("    asr: whisper-cli not configured; skipped")
        return None
    hyp = whisper_transcript(media, binary, model)
    if hyp is None:
        return {"skipped": True, "reason": "whisper failed"}
    ref = _norm_text(" ".join(captions))
    hyp_w = _norm_text(hyp)
    rate, errs = wer(ref, hyp_w)
    return {
        "wer": round(rate, 3),
        "errors": errs,
        "ref_words": len(ref),
        "hyp_words": len(hyp_w),
        "passed": rate <= 0.12,
        "hypothesis": hyp[:2000],
    }
