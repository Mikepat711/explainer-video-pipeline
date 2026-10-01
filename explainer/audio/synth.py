"""Procedural, license-free background score and sound design (pure numpy)."""
from __future__ import annotations

import math

import numpy as np

NOTES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7,
         "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}

# Voicings (semitones from the key root) for I - vi - IV - V with added colour tones.
PROGRESSION = [
    [0, 4, 7, 11, 14],      # Imaj9
    [-3, 0, 4, 7, 11],      # vi9
    [-7, -3, 0, 4, 7],      # IVmaj9
    [-5, -1, 2, 4, 9],      # V6/9
]


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _env_adsr(n: int, sr: int, a: float, r: float) -> np.ndarray:
    env = np.ones(n, np.float32)
    na, nr = min(n, int(a * sr)), min(n, int(r * sr))
    if na:
        env[:na] = np.linspace(0, 1, na) ** 2
    if nr:
        env[-nr:] *= np.linspace(1, 0, nr) ** 1.5
    return env


def _add(buf: np.ndarray, x: np.ndarray, start: int, pan: float = 0.0, gain: float = 1.0):
    if start >= len(buf):
        return
    end = min(len(buf), start + len(x))
    seg = x[: end - start] * gain
    lg, rg = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
    buf[start:end, 0] += seg * lg
    buf[start:end, 1] += seg * rg


def _reverb(x: np.ndarray, sr: int, seconds: float = 2.2, decay: float = 0.55, rng=None) -> np.ndarray:
    rng = rng or np.random.default_rng(3)
    m = int(seconds * sr)
    t = np.arange(m) / sr
    out = np.zeros_like(x)
    for ch in range(x.shape[1]):
        ir = rng.standard_normal(m).astype(np.float32) * np.exp(-t / decay)
        ir = np.convolve(ir, np.ones(12) / 12, mode="same")
        ir[: int(0.012 * sr)] = 0
        ir /= np.sqrt(np.sum(ir ** 2))
        nfft = 1 << (len(x) + m - 1).bit_length()
        y = np.fft.irfft(np.fft.rfft(x[:, ch], nfft) * np.fft.rfft(ir, nfft), nfft)[: len(x)]
        out[:, ch] = y
    return out


def music(duration: float, sr: int, bpm: float = 92, key: str = "D", seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(duration * sr) + sr
    dry = np.zeros((n, 2), np.float32)
    wet_send = np.zeros((n, 2), np.float32)
    root = 50 + (NOTES.get(key, 2) - 2)
    beat = 60.0 / bpm
    chord_len = beat * 8
    n_chords = int(math.ceil(duration / chord_len)) + 1
    intro_end = chord_len * 1
    outro_start = duration - 4.0

    # pad
    for ci in range(n_chords):
        chord = PROGRESSION[ci % len(PROGRESSION)]
        start = ci * chord_len
        seg_len = chord_len + 1.6
        m = int(seg_len * sr)
        t = np.arange(m) / sr
        env = _env_adsr(m, sr, 1.3, 1.8)
        trem = 1 + 0.08 * np.sin(2 * np.pi * 0.23 * t + ci)
        for k, st in enumerate(chord):
            f = hz(root + st)
            for det, pan in ((-5, -0.55), (5, 0.55)):
                ff = f * 2 ** (det / 1200)
                wave = sum(np.sin(2 * np.pi * ff * h * t + rng.uniform(0, 6)) / h ** 1.6 for h in range(1, 5))
                _add(dry, (wave * env * trem).astype(np.float32), int(start * sr), pan, 0.028)
                _add(wet_send, (wave * env).astype(np.float32), int(start * sr), pan, 0.02)

    # plucked arpeggio
    pat = [0, 2, 1, 3, 2, 4, 3, 1]
    pl = int(0.9 * sr)
    tp = np.arange(pl) / sr
    step = beat / 2
    k = 0
    tt = intro_end
    while tt < outro_start:
        ci = int(tt // chord_len)
        chord = PROGRESSION[ci % len(PROGRESSION)]
        note = root + 12 + chord[pat[k % len(pat)] % len(chord)]
        f = hz(note)
        env = np.exp(-tp / 0.28) * np.minimum(1, tp / 0.004)
        x = (np.sin(2 * np.pi * f * tp) + 0.28 * np.sin(4 * np.pi * f * tp) + 0.08 * np.sin(6 * np.pi * f * tp))
        vel = 0.75 + 0.25 * ((k % 4) == 0) + rng.uniform(-0.08, 0.08)
        pan = 0.35 if k % 2 else -0.35
        _add(dry, (x * env).astype(np.float32), int(tt * sr), pan, 0.05 * vel)
        _add(wet_send, (x * env).astype(np.float32), int(tt * sr), pan, 0.05 * vel)
        tt += step
        k += 1

    # bass
    bl = int(1.2 * sr)
    tb = np.arange(bl) / sr
    tt = intro_end
    while tt < outro_start + beat * 2:
        ci = int(tt // chord_len)
        chord = PROGRESSION[ci % len(PROGRESSION)]
        f = hz(root - 12 + chord[0])
        for off, vel in ((0, 1.0), (beat * 1.5, 0.7), (beat * 4, 0.9), (beat * 5.5, 0.6)):
            env = np.exp(-tb / 0.45) * np.minimum(1, tb / 0.01)
            x = np.sin(2 * np.pi * f * tb) + 0.18 * np.sin(4 * np.pi * f * tb)
            _add(dry, (x * env).astype(np.float32), int((tt + off) * sr), 0, 0.11 * vel)
        tt += chord_len

    # soft drums (enter after the intro)
    kl = int(0.4 * sr)
    tk = np.arange(kl) / sr
    kick = np.sin(2 * np.pi * (45 * tk + (110 - 45) * 0.03 * (1 - np.exp(-tk / 0.03)))) * np.exp(-tk / 0.16)
    hl = int(0.08 * sr)
    noise = rng.standard_normal(hl)
    hat = np.diff(noise, prepend=0) * np.exp(-np.arange(hl) / sr / 0.022)
    tt = intro_end + chord_len
    b = 0
    while tt < outro_start:
        if b % 4 in (0, 2):
            _add(dry, kick.astype(np.float32), int(tt * sr), 0, 0.16)
        _add(dry, hat.astype(np.float32), int((tt + beat / 2) * sr), 0.2, 0.018)
        tt += beat
        b += 1

    mixed = dry + 0.55 * _reverb(wet_send, sr, rng=rng)
    mixed = mixed[: int(duration * sr)]
    fade_in, fade_out = int(1.5 * sr), int(3.5 * sr)
    mixed[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    mixed[-fade_out:] *= (np.linspace(1, 0, fade_out) ** 2)[:, None]
    peak = np.max(np.abs(mixed)) or 1
    return (mixed / peak * 0.7).astype(np.float32)


def _lowpass_sweep(x: np.ndarray, sr: int, f0: float, f1: float, env_peak: float) -> np.ndarray:
    n = len(x)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(n):
        u = i / n
        f = f0 + (f1 - f0) * (u / env_peak if u < env_peak else 1 - (u - env_peak) / (1 - env_peak))
        a = 1 - math.exp(-2 * math.pi * f / sr)
        acc += a * (x[i] - acc)
        y[i] = acc
    return y


def sfx(events: list[dict], duration: float, sr: int, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    out = np.zeros((n, 2), np.float32)
    wl = int(0.9 * sr)
    peak_at = 0.62
    base_noise = rng.standard_normal(wl).astype(np.float32)
    whoosh = _lowpass_sweep(base_noise, sr, 250, 4200, peak_at)
    whoosh -= _lowpass_sweep(whoosh, sr, 120, 400, peak_at)
    u = np.arange(wl) / wl
    wenv = np.where(u < peak_at, (u / peak_at) ** 2.2, np.exp(-(u - peak_at) * 9))
    whoosh = whoosh * wenv
    whoosh /= np.max(np.abs(whoosh)) or 1

    pl = int(0.09 * sr)
    tp = np.arange(pl) / sr
    il = int(1.4 * sr)
    ti = np.arange(il) / sr
    boom = np.sin(2 * np.pi * (48 * ti + 42 * 0.08 * (1 - np.exp(-ti / 0.08)))) * np.exp(-ti / 0.45)
    burst = rng.standard_normal(il) * np.exp(-ti / 0.05)
    burst = np.convolve(burst, np.ones(24) / 24, mode="same")
    impact = boom * 0.9 + burst * 0.5
    impact /= np.max(np.abs(impact)) or 1

    for e in events:
        t = e["t"]
        if e["kind"] == "whoosh":
            start = int((t - peak_at * 0.9) * sr)
            if start >= 0:
                seg = whoosh[: max(0, min(wl, n - start))]
                ramp = np.linspace(-0.6, 0.6, len(seg))
                out[start:start + len(seg), 0] += seg * np.cos((ramp + 1) * np.pi / 4) * 0.55
                out[start:start + len(seg), 1] += seg * np.sin((ramp + 1) * np.pi / 4) * 0.55
        elif e["kind"] == "pop":
            f0 = 1250 * rng.uniform(0.92, 1.1)
            ph = 2 * np.pi * (f0 * tp - (f0 * 0.45) * tp ** 2 / (2 * 0.09))
            pop = (np.sin(ph) * np.exp(-tp / 0.022) * np.minimum(1, tp / 0.002)).astype(np.float32)
            _add(out, pop, int(t * sr), rng.uniform(-0.3, 0.3), 0.22)
        elif e["kind"] == "impact":
            _add(out, impact.astype(np.float32), int(t * sr), 0, 0.6)
    return out
