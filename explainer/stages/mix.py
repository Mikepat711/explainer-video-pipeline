from __future__ import annotations

import json
import re

import numpy as np

from ..pipeline import Stage
from ..util import log, read_json, read_wav, run, write_json, write_wav


def duck_envelope(voice: np.ndarray, sr: int, lookahead: float = 0.12, attack: float = 0.08,
                  release: float = 0.6) -> np.ndarray:
    """0..1 'voice active' envelope at audio rate (smoothed, with lookahead)."""
    hop = sr // 100
    frames = len(voice) // hop + 1
    pad = np.zeros(frames * hop, np.float32)
    pad[: len(voice)] = voice
    rms = np.sqrt(np.mean(pad.reshape(frames, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    target = np.clip((db + 48) / 14, 0, 1)
    la = int(lookahead * 100)
    target = np.concatenate([target[la:], np.zeros(la)])
    env = np.zeros_like(target)
    ca, cr = np.exp(-1 / (attack * 100)), np.exp(-1 / (release * 100))
    acc = 0.0
    for i, v in enumerate(target):
        c = ca if v > acc else cr
        acc = c * acc + (1 - c) * v
        env[i] = acc
    return np.interp(np.arange(len(voice)) / hop, np.arange(frames), env).astype(np.float32)


def db(x):
    return 10 ** (x / 20)


class Mix(Stage):
    name = "mix"
    deps = ("timeline", "music", "voice")
    description = "mix voice + ducked music + SFX, loudness-normalize"

    def inputs(self, ctx):
        return {"audio": ctx.cfg["audio"]}

    def outputs(self, ctx):
        return [ctx.vdir / "audio" / "mix.wav", ctx.vdir / "audio" / "mix_report.json"]

    def run(self, ctx):
        a = ctx.cfg["audio"]
        sr = a["sample_rate"]
        tl = read_json(ctx.vdir / "timeline.json")
        n = int(round(tl["total"] * sr))
        voice = np.zeros(n, np.float32)
        for sc in tl["scenes"]:
            x, _ = read_wav(ctx.common / "voice" / f"{sc['id']}.wav")
            x = x[:, 0][: int(sc["duration"] * sr)]
            s = int(round(sc["start"] * sr))
            voice[s:s + len(x)] += x[: max(0, n - s)]
        # Level the voice by its speech RMS, not its peak: TTS engines differ a lot in crest factor, and
        # peak-normalizing would shift the voice/music balance whenever the engine changes.
        env = duck_envelope(voice / (np.max(np.abs(voice)) or 1), sr)
        talking = env > 0.6
        speech_rms = float(np.sqrt(np.mean(voice[talking] ** 2))) if talking.any() else 0.0
        voice *= db(a.get("voice_rms_db", -19.0)) / (speech_rms or float(np.max(np.abs(voice))) or 1)
        music, _ = read_wav(ctx.vdir / "audio" / "music.wav")
        sfx, _ = read_wav(ctx.vdir / "audio" / "sfx.wav")
        music = np.pad(music, ((0, max(0, n - len(music))), (0, 0)))[:n]
        sfx = np.pad(sfx, ((0, max(0, n - len(sfx))), (0, 0)))[:n]
        mgain = db(a["music_gain_db"] + a["duck_db"] * env)[:, None]
        sgain = db(a["sfx_gain_db"] + 0.4 * a["duck_db"] * env)[:, None]
        mixed = voice[:, None] * np.ones((1, 2), np.float32) + music * mgain + sfx * sgain
        speech, gaps = talking, env < 0.3

        def rms_db(x, mask):
            return round(float(10 * np.log10(np.mean(x[mask] ** 2) + 1e-12)), 1) if mask.any() else None
        ducked = (music * mgain).mean(axis=1)
        balance = {"voice_rms_db": rms_db(voice, speech), "music_under_voice_rms_db": rms_db(ducked, speech),
                   "music_in_gaps_rms_db": rms_db(ducked, gaps)}
        if balance["voice_rms_db"] is not None and balance["music_under_voice_rms_db"] is not None:
            balance["voice_over_music_db"] = round(balance["voice_rms_db"] - balance["music_under_voice_rms_db"], 1)
        log(f"    balance: {balance}")
        pre = ctx.vdir / "audio" / "premaster.wav"
        write_wav(pre, mixed / max(1.0, float(np.max(np.abs(mixed))) / 0.98), sr)
        tgt = f"I={a['target_lufs']}:TP={a['true_peak']}:LRA=11"

        def measure(path):
            res = run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", f"loudnorm={tgt}:print_format=json",
                       "-f", "null", "-"])
            return json.loads(re.findall(r"\{[^{}]*\}", res.stderr, re.S)[-1])
        meas = measure(pre)
        gain = a["target_lufs"] - float(meas["input_i"])
        allowed = a["true_peak"] - gain - 0.6
        if float(meas["input_tp"]) > allowed:
            limited = ctx.vdir / "audio" / "premaster_limited.wav"
            run(["ffmpeg", "-y", "-v", "error", "-i", str(pre), "-af",
                 f"alimiter=limit={10 ** (allowed / 20):.4f}:attack=3:release=60:level=disabled:asc=1",
                 str(limited)])
            limited.replace(pre)
            meas = measure(pre)
        filt = (f"loudnorm={tgt}:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
                f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:"
                f"offset={meas['target_offset']}:linear=true:print_format=json")
        res2 = run(["ffmpeg", "-y", "-hide_banner", "-i", str(pre), "-af", filt, "-ar", str(sr),
                    "-map_metadata", "-1", str(ctx.vdir / "audio" / "mix.wav")])
        out = json.loads(re.findall(r"\{[^{}]*\}", res2.stderr, re.S)[-1])
        report = {"premaster": {k: meas[k] for k in ("input_i", "input_tp", "input_lra")},
                  "normalized": {k: out[k] for k in ("output_i", "output_tp", "output_lra", "normalization_type")},
                  "music_bed_db": a["music_gain_db"], "duck_db": a["duck_db"], "balance": balance}
        log(f"    loudness: {out['output_i']} LUFS, true peak {out['output_tp']} dBTP ({out['normalization_type']})")
        write_json(ctx.vdir / "audio" / "mix_report.json", report)
        pre.unlink(missing_ok=True)
