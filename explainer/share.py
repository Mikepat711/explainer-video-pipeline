"""Size-capped share copies: 2-pass H.264 fitted to a byte budget + AAC, web-optimized (+faststart)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .util import ffprobe_duration, log, run


def _video_kbps(src: Path) -> int | None:
    res = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=bit_rate", "-of", "json",
               str(src)])
    rate = (json.loads(res.stdout).get("streams") or [{}])[0].get("bit_rate")
    return int(rate) // 1000 if rate else None


def _encode(src: Path, dst: Path, video_kbps: int, audio_kbps: int, vf: list[str], preset: str) -> None:
    common = ["-c:v", "libx264", "-preset", preset, "-tune", "animation", "-profile:v", "high",
              "-b:v", f"{video_kbps}k", "-maxrate", f"{int(video_kbps * 2.5)}k", "-bufsize", f"{video_kbps * 4}k",
              "-vf", ",".join(vf)]
    with tempfile.TemporaryDirectory() as td:
        log_prefix = str(Path(td) / "x264")
        run(["ffmpeg", "-y", "-v", "error", "-i", str(src), *common, "-pass", "1", "-passlogfile", log_prefix,
             "-an", "-f", "mp4", "/dev/null"])
        run(["ffmpeg", "-y", "-v", "error", "-i", str(src), *common, "-pass", "2", "-passlogfile", log_prefix,
             "-c:a", "aac", "-b:a", f"{audio_kbps}k", "-ac", "2", "-movflags", "+faststart",
             "-map_metadata", "0", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
             str(dst)])


def share_copy(src: Path, dst: Path, max_mb: float = 15.0, audio_kbps: int = 128, height: int | None = None,
               preset: str = "slow") -> dict:
    """Encode `src` so the result stays under `max_mb` (decimal megabytes, 1 MB = 10^6 bytes).

    Short clips that already fit are not inflated: the target never exceeds 1.25x the source video bitrate.
    """
    dur = ffprobe_duration(src)
    budget_kbits = max_mb * 1e6 * 8 / 1000 * 0.97
    video_kbps = int(budget_kbits / dur - audio_kbps)
    if video_kbps < 150:
        raise SystemExit(f"{src.name}: {dur:.0f}s cannot fit in {max_mb} MB at a watchable bitrate")
    source_kbps = _video_kbps(src)
    if source_kbps:
        video_kbps = min(video_kbps, int(source_kbps * 1.25))
    vf = ["format=yuv420p"] if not height else [f"scale=-2:{height}:flags=lanczos", "format=yuv420p"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    cap = max_mb * 1e6
    # two-pass x264 can overshoot its target on short or very static clips; retry at a proportionally lower rate
    for attempt in range(3):
        _encode(src, dst, video_kbps, audio_kbps, vf, preset)
        size = dst.stat().st_size
        if size <= cap:
            break
        if attempt == 2:
            raise RuntimeError(f"{dst.name} came out at {size / 1e6:.2f} MB, over the {max_mb} MB cap")
        video_kbps = int(video_kbps * cap / size * 0.95)
        log(f"  {dst.name}: {size / 1e6:.2f} MB is over the cap; re-encoding at {video_kbps} kb/s")
        if video_kbps < 150:
            raise SystemExit(f"{src.name}: {dur:.0f}s cannot fit in {max_mb} MB at a watchable bitrate")
    log(f"  {dst.name}: {size / 1e6:.2f} MB ({video_kbps} kb/s video + {audio_kbps} kb/s audio, {dur:.1f}s)")
    return {"file": dst.name, "bytes": size, "video_kbps": video_kbps, "audio_kbps": audio_kbps,
            "duration_s": round(dur, 2)}
