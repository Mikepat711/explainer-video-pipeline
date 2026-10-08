"""Toolkit-style music bed, SFX, mix and loudness (-16 LUFS, true peak under -1 dBTP)."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ..pipeline import Stage
from ..util import log, read_json, write_json, write_wav
from .render import _timing_map

SR_MIX = 48000


def _need(name: str):
    try:
        return __import__(name)
    except ImportError as e:
        raise SystemExit(
            f"bundle build needs {name}. Install the bundle extras: "
            f"`pip install -r requirements-bundle.txt`"
        ) from e


def scene_starts(timing: dict, fps: int) -> tuple[dict[str, float], float]:
    tm = _timing_map(timing)
    order = [k for k, _ in sorted(tm.items(), key=lambda kv: kv[1].get("index", 0))]
    start, acc = {}, 0
    for k in order:
        start[k] = acc / fps
        acc += int(math.ceil(tm[k]["duration"] * fps))
    return start, acc / fps


def _place_voice(timing: dict, voice_dir: Path, start: dict[str, float], total: float, sr: int) -> np.ndarray:
    import soundfile as sf
    from scipy.signal import resample_poly, butter, sosfilt
    n = int(round(total * sr))
    voice = np.zeros(n, np.float32)
    tm = _timing_map(timing)
    for sid, row in tm.items():
        wav = voice_dir / f"{sid}.wav"
        if not wav.is_file():
            continue
        a, in_sr = sf.read(str(wav), dtype="float32")
        if a.ndim > 1:
            a = a.mean(axis=1)
        if in_sr != sr:
            # integer ratio when possible (24k -> 48k)
            g = math.gcd(sr, in_sr)
            a = resample_poly(a, sr // g, in_sr // g).astype(np.float32)
        i0 = int(round(start[sid] * sr))
        a = a[: max(0, n - i0)]
        voice[i0:i0 + len(a)] += a
    voice = sosfilt(butter(2, 70, "hp", fs=sr, output="sos"), voice).astype(np.float32)
    return voice


def _music(total: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    from scipy.signal import butter, sosfilt, fftconvolve
    n = int(round(total * sr))
    t = np.arange(n) / sr
    L = np.zeros(n)
    R = np.zeros(n)

    def note_hz(m):
        return 440 * 2 ** ((m - 69) / 12)

    chords = [[50, 57, 64, 66, 69], [47, 54, 61, 62, 66], [43, 50, 57, 59, 66], [45, 52, 59, 61, 64]]
    chord_len = 8.0
    nch = int(math.ceil(total / chord_len)) + 1
    for ci in range(nch):
        t0 = ci * chord_len - 1.5
        t1 = t0 + chord_len + 3.0
        i0 = max(0, int(t0 * sr))
        i1 = min(n, int(t1 * sr))
        if i1 <= i0:
            continue
        tt = t[i0:i1] - t0
        dur = t1 - t0
        env = np.minimum(1, tt / 2.5) * np.minimum(1, (dur - tt) / 2.5)
        env = np.clip(env, 0, 1) ** 1.5
        for m in chords[ci % 4]:
            f = note_hz(m)
            for det, pan in ((-0.12, 0.25), (0.12, 0.75)):
                ff = f * 2 ** (det / 12)
                ph = rng.uniform(0, 2 * np.pi)
                sig = (np.sin(2 * np.pi * ff * tt + ph)
                       + 0.28 * np.sin(4 * np.pi * ff * tt + ph * 1.3)
                       + 0.1 * np.sin(6 * np.pi * ff * tt))
                sig *= (1 + 0.15 * np.sin(2 * np.pi * 0.13 * tt + ph))
                L[i0:i1] += sig * env * (1 - pan) / (1 + (m > 60))
                R[i0:i1] += sig * env * pan / (1 + (m > 60))
    for k in range(int(total / 3.1)):
        tc = 1.0 + k * 3.1 + rng.uniform(-0.4, 0.4)
        m = rng.choice([72, 74, 76, 79, 81, 84])
        i0 = int(tc * sr)
        i1 = min(n, i0 + int(4 * sr))
        if i0 >= n:
            break
        tt = t[i0:i1] - tc
        env = (1 - np.exp(-tt * 6)) * np.exp(-tt * 0.9)
        sig = np.sin(2 * np.pi * note_hz(m) * tt) * env * 0.12
        pan = rng.uniform(0.2, 0.8)
        L[i0:i1] += sig * (1 - pan)
        R[i0:i1] += sig * pan
    lp = butter(2, 1800, "lp", fs=sr, output="sos")
    L = sosfilt(lp, L)
    R = sosfilt(lp, R)
    ir_t = np.arange(int(2.8 * sr)) / sr
    irL = rng.standard_normal(len(ir_t)) * np.exp(-ir_t * 2.2)
    irR = rng.standard_normal(len(ir_t)) * np.exp(-ir_t * 2.2)
    irL[0] += 8
    irR[0] += 8
    L = fftconvolve(L, irL)[:n]
    R = fftconvolve(R, irR)[:n]
    fade = np.minimum(1, t / 2.0) * np.minimum(1, (total - t) / 3.5)
    return np.stack([L, R], 1) * fade[:, None]


def _sfx_bank(sr: int, rng: np.random.Generator) -> dict:
    from scipy.signal import butter, sosfilt

    def env_exp(n, tau):
        return np.exp(-np.arange(n) / sr / tau)

    def bp(x, lo, hi):
        return sosfilt(butter(2, [lo, hi], "bp", fs=sr, output="sos"), x)

    def lpf(x, fc):
        return sosfilt(butter(2, fc, "lp", fs=sr, output="sos"), x)

    def rumble(gain=1.0, dur=2.4):
        n = int(dur * sr)
        tt = np.arange(n) / sr
        br = np.cumsum(rng.standard_normal(n))
        br -= lpf(br, 8)
        br = lpf(br, 110)
        br /= np.max(np.abs(br)) + 1e-9
        env = np.sin(np.pi * np.clip(tt / dur, 0, 1)) ** 1.2
        creak = bp(rng.standard_normal(n), 300, 900) * 0.05 * env
        return (br * env + creak) * gain

    def crack(gain=1.0, length=0.35):
        n = int(0.8 * sr)
        x = np.zeros(n)
        x[: int(0.03 * sr)] += rng.standard_normal(int(0.03 * sr)) * np.linspace(1, 0, int(0.03 * sr))
        for _k in range(9):
            i = int(rng.uniform(0.01, length) * sr)
            m = int(0.006 * sr)
            x[i:i + m] += rng.standard_normal(m) * rng.uniform(0.2, 0.6) * np.linspace(1, 0, m)
        x = bp(x, 900, 7000) + 0.5 * lpf(x, 300)
        return x * gain

    def click(gain=1.0, f=2600, dur=0.25):
        n = int(dur * sr)
        tt = np.arange(n) / sr
        x = bp(rng.standard_normal(n), 1500, 7000) * env_exp(n, 0.004)
        x += np.sin(2 * np.pi * f * tt) * env_exp(n, 0.012) * 0.35
        x += np.sin(2 * np.pi * 180 * tt) * env_exp(n, 0.03) * 0.5
        return x * gain

    def whoosh(gain=1.0, dur=1.4, lo=200, hi=2500):
        n = int(dur * sr)
        tt = np.arange(n) / sr
        x = bp(rng.standard_normal(n), lo, hi)
        env = np.clip(tt / 0.08, 0, 1) * np.exp(-tt * 2.2)
        body = lpf(rng.standard_normal(n), 300) * env * 1.5
        return (x * env + body) * gain

    def hiss(gain=1.0, dur=1.6):
        n = int(dur * sr)
        tt = np.arange(n) / sr
        x = bp(rng.standard_normal(n), 3000, 9000)
        env = np.clip(tt / 0.15, 0, 1) * np.clip((dur - tt) / 0.6, 0, 1)
        return x * env * gain

    def drip(gain=1.0):
        n = int(0.5 * sr)
        tt = np.arange(n) / sr
        f = 900 + 1400 * np.clip(tt / 0.05, 0, 1)
        return np.sin(2 * np.pi * np.cumsum(f) / sr) * env_exp(n, 0.06) * gain

    def chime(gain=1.0):
        n = int(1.5 * sr)
        tt = np.arange(n) / sr
        x = sum(np.sin(2 * np.pi * f * tt) * env_exp(n, d) * g
                for f, d, g in ((1318.5, 0.5, 0.6), (1975.5, 0.3, 0.3), (2637, 0.2, 0.15)))
        return x * np.clip(tt / 0.005, 0, 1) * gain

    def blip(gain=1.0, f=880):
        n = int(0.6 * sr)
        tt = np.arange(n) / sr
        x = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)) * env_exp(n, 0.09) * np.clip(tt / 0.004, 0, 1)
        return lpf(x, 3000) * gain

    def tick(gain=1.0):
        n = int(0.12 * sr)
        tt = np.arange(n) / sr
        x = bp(rng.standard_normal(n), 2500, 9000) * env_exp(n, 0.003) * 1.2
        x += np.sin(2 * np.pi * 3200 * tt) * env_exp(n, 0.01) * 0.2
        return x * gain

    return {
        "blip": lambda: blip(0.3),
        "blip_lo": lambda: blip(0.3, 660),
        "tick": lambda: tick(0.5),
        "whoosh": lambda: whoosh(0.9),
        "whoosh_soft": lambda: whoosh(0.35, 1.8, 150, 1200),
        "hiss": lambda: hiss(0.25),
        "drip": lambda: drip(0.35),
        "chime": lambda: chime(0.3),
        "rumble": lambda: rumble(0.8, 2.4),
        "crack": lambda: crack(0.45),
        "click": lambda: click(0.55),
        "click_soft": lambda: click(0.3, 3000),
    }


def _limit(x: np.ndarray, sr: int, ceil_db: float = -1.2) -> tuple[np.ndarray, float]:
    from scipy.ndimage import maximum_filter1d
    thr = 10 ** (ceil_db / 20)
    la = int(0.005 * sr)
    pk = maximum_filter1d(np.max(np.abs(x), 1), size=2 * la + 1)
    g = np.minimum(1.0, thr / np.maximum(pk, 1e-9))
    rel = math.exp(-1 / (0.12 * sr))
    out = np.empty_like(g)
    cur = 1.0
    for i in range(len(g)):
        v = g[i]
        cur = v if v < cur else (cur * rel + v * (1 - rel))
        out[i] = cur
    return x * out[:, None], float(np.mean(out < 0.999))


def mix_bundle(timing: dict, voice_dir: Path, events: list, out_mix: Path, out_music: Path,
               sr: int = SR_MIX, fps: int = 30, target_lufs: float = -16.0) -> dict:
    pyln = _need("pyloudnorm")
    _need("soundfile")
    _need("scipy")
    start, total = scene_starts(timing, fps)
    n = int(round(total * sr))
    if n < sr // 2:
        # smoke / still-short: keep a minimum bed so loudness code has something to measure
        total = max(total, 1.0)
        n = int(round(total * sr))
    rng = np.random.default_rng(7)
    voice = _place_voice(timing, voice_dir, start, total, sr)
    music = _music(total, sr, rng)
    bank = _sfx_bank(sr, rng)
    sfx = np.zeros(n, np.float32)
    placed = []
    for item in events:
        sid, lt, kind = item[0], float(item[1]), item[2]
        if sid not in start or kind not in bank:
            continue
        x = np.asarray(bank[kind](), np.float32)
        i0 = int((start[sid] + lt) * sr)
        if i0 >= n or i0 < 0:
            continue
        x = x[: n - i0]
        sfx[i0:i0 + len(x)] += x
        placed.append({"scene": sid, "at": round(start[sid] + lt, 2), "kind": kind})
    meter = pyln.Meter(sr)
    voice64 = voice.astype(np.float64)
    try:
        vl = meter.integrated_loudness(voice64)
    except Exception:
        vl = -23.0
    if not np.isfinite(vl):
        vl = -23.0
    try:
        ml = meter.integrated_loudness(music)
    except Exception:
        ml = -30.0
    if np.isfinite(ml):
        music = music * (10 ** (((vl - 15.0) - ml) / 20))
    peak_v = float(np.max(np.abs(voice)) or 1e-9)
    peak_s = float(np.max(np.abs(sfx)) or 1e-9)
    sfx = sfx * (peak_v * 10 ** (-5 / 20)) / peak_s
    mix = np.stack([voice, voice], 1) + music + np.stack([sfx, sfx], 1)
    try:
        ln = meter.integrated_loudness(mix)
    except Exception:
        ln = -20.0
    if np.isfinite(ln):
        mix = mix * (10 ** ((target_lufs - ln) / 20))
    frac = 0.0
    for _ in range(2):
        mix, frac = _limit(mix, sr)
        try:
            ln = meter.integrated_loudness(mix)
        except Exception:
            ln = target_lufs
        if np.isfinite(ln):
            mix = mix * (10 ** ((target_lufs - ln) / 20))
    mix, frac = _limit(mix, sr)
    try:
        final = float(meter.integrated_loudness(mix))
    except Exception:
        final = None
    peak = float(20 * np.log10(np.max(np.abs(mix)) + 1e-12))
    write_wav(out_mix, mix.astype(np.float32), sr)
    write_wav(out_music, (music / (np.max(np.abs(music)) + 1e-9) * 0.5).astype(np.float32), sr)
    return {
        "duration_s": round(total, 3),
        "target_lufs": target_lufs,
        "integrated_lufs": None if final is None else round(final, 2),
        "peak_dbfs": round(peak, 2),
        "limiter_fraction": round(frac, 4),
        "sfx": placed,
    }


class Music(Stage):
    name = "music"
    scope = "variant"
    deps = ("voice",)
    extra_code = ("produce/music.py",)
    description = "procedural music bed + scene SFX, mix and loudness-normalize"

    def inputs(self, ctx):
        return {"audio": {k: ctx.cfg["audio"].get(k) for k in ("target_lufs", "true_peak", "sample_rate")},
                "fps": ctx.fps}

    def outputs(self, ctx):
        a = ctx.vdir / "audio"
        return [a / "mix.wav", a / "music.wav", a / "mix_report.json"]

    def run(self, ctx):
        timing = read_json(ctx.common / "voice" / "timing.json")
        words_p = ctx.common / "voice" / "words.json"
        words = read_json(words_p) if words_p.exists() else {}
        # sfx_events wants the toolkit timing map {id: {index, sentences, ...}}
        tm = _timing_map(timing)
        events = ctx.bundle.sfx_events(tm, words)
        if ctx.scenes_filter:
            allow = set(ctx.scenes_filter)
            events = [e for e in events if e[0] in allow]
        audio = ctx.vdir / "audio"
        audio.mkdir(parents=True, exist_ok=True)
        report = mix_bundle(
            timing, ctx.common / "voice", events,
            audio / "mix.wav", audio / "music.wav",
            sr=int(ctx.cfg["audio"]["sample_rate"]),
            fps=ctx.fps,
            target_lufs=float(ctx.cfg["audio"]["target_lufs"]),
        )
        write_json(audio / "mix_report.json", report)
        log(f"    mix {report['integrated_lufs']} LUFS, peak {report['peak_dbfs']} dBFS, "
            f"{len(report['sfx'])} sfx")
