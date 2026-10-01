from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "topic"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, default=str).encode())


def file_fingerprint(path: Path) -> str:
    """Content hash for small files, size+mtime for large media."""
    st = path.stat()
    if st.st_size > 32 * 1024 * 1024:
        return f"{st.st_size}:{st.st_mtime_ns}"
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def read_json(path: Path):
    return json.loads(path.read_text())


def run(cmd: list[str], cwd: Path | None = None, capture: bool = False) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if res.returncode != 0:
        tail = "\n".join((res.stderr or "").splitlines()[-25:])
        raise RuntimeError(f"command failed ({cmd[0]}):\n{tail}")
    return res


_ABBREV = r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)(?<!\bDr\.)(?<!\bMr\.)(?<!\bSt\.)"


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    parts = re.split(_ABBREV + r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text)
    return [p.strip() for p in parts if p.strip()]


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Returns float32 array shaped (n, channels) in [-1, 1]."""
    with wave.open(str(path), "rb") as w:
        sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {sw} in {path.name}")
    return data.reshape(-1, ch), sr


def write_wav(path: Path, data: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if data.ndim == 1:
        data = data[:, None]
    pcm = (np.clip(data, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def ffprobe_duration(path: Path) -> float:
    res = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    return float(json.loads(res.stdout)["format"]["duration"])


def resample_to(path_in: Path, path_out: Path, sr: int, channels: int = 1) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-i", str(path_in), "-ar", str(sr), "-ac", str(channels),
         "-sample_fmt", "s16", "-map_metadata", "-1", str(path_out)])


LIBASS_HELP = ("burned-in captions need an ffmpeg built with libass (the 'ass' filter), and none was found.\n"
               "  macOS:  brew install ffmpeg-full   (Homebrew's plain `ffmpeg` formula lacks libass)\n"
               "  Linux:  apt install ffmpeg\n"
               "  or point EXPLAINER_FFMPEG at a full build in ~/.config/explainer/config,\n"
               "  or skip burned-in captions: --set captions.burn_in=false (the .srt is still written)")


def has_libass(ffmpeg: str) -> bool:
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-filters"], text=True, capture_output=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool(re.search(r"^\s*\S+\s+ass\s", out, re.M))


def ffmpeg_with_libass() -> str | None:
    """EXPLAINER_FFMPEG, then ffmpeg on PATH, then Homebrew's keg-only ffmpeg-full."""
    import shutil
    from . import localconf
    candidates = [localconf.get("EXPLAINER_FFMPEG"), shutil.which("ffmpeg")]
    brew = shutil.which("brew")
    if brew:
        try:
            prefix = subprocess.run([brew, "--prefix", "ffmpeg-full"], text=True, capture_output=True,
                                    timeout=30).stdout.strip()
            candidates.append(str(Path(prefix) / "bin" / "ffmpeg") if prefix else None)
        except (OSError, subprocess.TimeoutExpired):
            pass
    candidates += ["/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg", "/usr/local/opt/ffmpeg-full/bin/ffmpeg"]
    for c in candidates:
        if c and Path(c).is_file() and has_libass(c):
            return c
    return None
