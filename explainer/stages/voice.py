from __future__ import annotations

from pathlib import Path

import numpy as np

from ..pipeline import Stage
from ..scriptfmt import parse_script
from ..textnorm import normalize
from ..tts import TTSEngine, get_engine, resolve_voice
from ..util import log, read_wav, resample_to, run, sha256_json, write_json, write_wav


def trim_silence(x: np.ndarray, sr: int, thresh_db: float = -45.0, pad: float = 0.03) -> np.ndarray:
    mono = np.abs(x.mean(axis=1) if x.ndim > 1 else x)
    win = max(1, int(sr * 0.01))
    env = np.convolve(mono, np.ones(win) / win, mode="same")
    idx = np.where(env > 10 ** (thresh_db / 20))[0]
    if len(idx) == 0:
        return x
    a = max(0, idx[0] - int(pad * sr))
    b = min(len(x), idx[-1] + int(pad * sr))
    return x[a:b]


def sentence_pause(text: str, L: dict) -> float:
    """Breath after a sentence: long sentences and questions earn a slightly longer pause."""
    extra = min(float(L.get("sentence_gap_extra", 0.25)), 0.012 * len(text.split()))
    if text.rstrip().endswith(("?", "!")):
        extra += 0.1
    return float(L["sentence_gap"]) + extra


def spoken(text: str, cfg: dict) -> str:
    return normalize(text, cfg["voice"].get("pronounce"))


def synthesize_clips(engine: TTSEngine, texts: list[str], sr: int, cache: Path, tempo: float = 1.0) -> list[np.ndarray]:
    """Trimmed mono clips for already-spoken texts; uncached sentences are synthesized in one batch."""
    cache.mkdir(parents=True, exist_ok=True)
    keys = [sha256_json({"t": t, "e": engine.identity(), "sr": sr})[:16] for t in texts]
    todo = {k: t for k, t in zip(keys, texts) if not (cache / f"{k}.wav").exists()}
    if todo:
        engine.synthesize_many([(t, cache / f"{k}.raw.wav") for k, t in todo.items()])
        for k in todo:
            resample_to(cache / f"{k}.raw.wav", cache / f"{k}.wav", sr, 1)
            (cache / f"{k}.raw.wav").unlink(missing_ok=True)
    clips = []
    for k in keys:
        wav = cache / f"{k}.wav"
        if abs(tempo - 1.0) > 1e-3:
            slowed = cache / f"{k}.t{tempo:.3f}.wav"
            if not slowed.exists():
                run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", f"atempo={tempo:.3f}", "-ar", str(sr),
                     "-ac", "1", "-sample_fmt", "s16", str(slowed)])
            wav = slowed
        x, _ = read_wav(wav)
        clips.append(trim_silence(x[:, 0], sr).astype(np.float32))
    return clips


def join_clips(clips: list[np.ndarray], sentences: list[str], L: dict, sr: int,
               lead_in: float | None = None, tail: float | None = None) -> tuple[np.ndarray, list[dict]]:
    """Sentences joined with natural pauses. Returns (mono audio, [{text, start, end}])."""
    lead_in = float(L["scene_lead_in"] if lead_in is None else lead_in)
    tail = float(L["scene_tail"] if tail is None else tail)
    parts, timing, cur = [np.zeros(int(lead_in * sr), np.float32)], [], lead_in
    for i, (x, s) in enumerate(zip(clips, sentences)):
        d = len(x) / sr
        timing.append({"text": s, "start": round(cur, 3), "end": round(cur + d, 3)})
        gap = sentence_pause(s, L) if i < len(sentences) - 1 else tail
        parts += [x, np.zeros(int(gap * sr), np.float32)]
        cur += d + gap
    return np.concatenate(parts), timing


def pace_of(groups: list[list[str]], spoken_groups: list[list[str]], clips: list[list[np.ndarray]],
            L: dict, sr: int) -> dict:
    """wpm counts spoken words over speech plus the pauses between sentences (scene lead-ins/tails excluded)."""
    words = sum(len(t.split()) for g in spoken_groups for t in g)
    speech = sum(len(x) / sr for g in clips for x in g)
    pauses = sum(sentence_pause(s, L) for g in groups for s in g[:-1])
    return {"words": words, "speech": speech, "pauses": pauses, "wpm": words / max(speech + pauses, 1e-6) * 60,
            "speaking_wpm": words / max(speech, 1e-6) * 60}


def speech_factor(p: dict, target: float) -> float:
    """How much faster speech must run for the whole to hit the target (pauses do not scale)."""
    want = p["words"] * 60 / target - p["pauses"]
    return p["speech"] / want if want > 0 else float("inf")


def paced_clips(cfg: dict, groups: list[list[str]], sr: int, cache: Path) -> tuple[list[list[np.ndarray]], dict]:
    """Synthesize every sentence and steer the pace toward voice.target_wpm.

    The preset's native speed is kept when the result is within voice.pace_tolerance. Otherwise
    engines with a native speed control re-synthesize once at a corrected speed, and any residual
    is closed with a gentle time-stretch (atempo), which keeps the voice's character. A preset may
    set its own target_wpm and pace_tolerance.
    """
    v, L = resolve_voice(cfg), cfg["length"]
    target, tol = float(v.get("target_wpm") or 0), float(v.get("pace_tolerance", 0.04))
    lo, hi = float(v.get("speed_adjust_min", 0.75)), float(v.get("speed_adjust_max", 1.35))
    spoken_groups = [[spoken(s, cfg) for s in g] for g in groups]
    flat = [t for g in spoken_groups for t in g]

    def regroup(clips):
        out, i = [], 0
        for g in groups:
            out.append(clips[i:i + len(g)])
            i += len(g)
        return out

    engine = get_engine(cfg)
    speed_key = engine.speed_param
    base_speed = float(v.get(speed_key) or 1.0) if speed_key else None
    speed, tempo = base_speed, 1.0
    clips = regroup(synthesize_clips(engine, flat, sr, cache))
    p = pace_of(groups, spoken_groups, clips, L, sr)
    first = p["wpm"]
    off = lambda q: target and abs(q["wpm"] / target - 1) > tol  # noqa: E731
    if off(p) and speed_key:
        speed = round(base_speed * min(hi, max(lo, speech_factor(p, target))), 3)
        log(f"    pace {p['wpm']:.0f} wpm vs target {target:.0f}: re-synthesizing at {speed_key}={speed}")
        engine = get_engine(cfg, **{speed_key: speed})
        clips = regroup(synthesize_clips(engine, flat, sr, cache))
        p = pace_of(groups, spoken_groups, clips, L, sr)
    if off(p):
        tempo = round(min(hi, max(lo, speech_factor(p, target))) * 200) / 200
        log(f"    pace {p['wpm']:.0f} wpm vs target {target:.0f}: time-stretching speech by {tempo:.3f}")
        clips = regroup(synthesize_clips(engine, flat, sr, cache, tempo=tempo))
        p = pace_of(groups, spoken_groups, clips, L, sr)
    info = {"engine": engine.identity(), "target_wpm": target or None, "wpm": round(p["wpm"], 1),
            "speaking_wpm": round(p["speaking_wpm"], 1), "first_pass_wpm": round(first, 1),
            "speed": speed, "preset_speed": base_speed, "tempo": tempo}
    return clips, info


class Voice(Stage):
    name = "voice"
    scope = "common"
    deps = ("script",)
    description = "synthesize narration per sentence (pluggable TTS), paced to voice.target_wpm"
    extra_code = ("tts", "textnorm.py")
    owns = ("voice/*.wav",)

    def inputs(self, ctx):
        L, v = ctx.cfg["length"], resolve_voice(ctx.cfg)
        return {"tts": get_engine(ctx.cfg).identity(), "sr": ctx.cfg["audio"]["sample_rate"],
                "pauses": {k: L.get(k) for k in ("scene_lead_in", "sentence_gap", "sentence_gap_extra",
                                                 "scene_tail")},
                "pace": {k: v.get(k) for k in ("target_wpm", "pace_tolerance", "speed_adjust_min",
                                               "speed_adjust_max", "pronounce")}}

    def outputs(self, ctx):
        vdir = ctx.common / "voice"
        md = ctx.common / "script.md"
        tracks = [vdir / f"{sc['id']}.wav" for sc in parse_script(md.read_text())["scenes"]] if md.exists() else []
        return [vdir / "timing.json", *tracks]

    def run(self, ctx):
        script = parse_script((ctx.common / "script.md").read_text())
        L = ctx.cfg["length"]
        sr = ctx.cfg["audio"]["sample_rate"]
        vdir = ctx.common / "voice"
        current = {f"{sc['id']}.wav" for sc in script["scenes"]}
        stale = sorted(p for p in vdir.glob("*.wav") if p.name not in current) if vdir.exists() else []
        for p in stale:
            p.unlink()
        if stale:
            log(f"    removed voice tracks for scenes no longer in the script: {', '.join(p.stem for p in stale)}")
        groups = [sc["sentences"] for sc in script["scenes"]]
        clips, info = paced_clips(ctx.cfg, groups, sr, vdir / "sentences")
        log(f"    voice {info['engine']}: {info['wpm']:.0f} wpm (target {info['target_wpm']}), "
            f"{info['speaking_wpm']:.0f} wpm while talking")
        scenes = []
        for sc, sc_clips in zip(script["scenes"], clips):
            audio, sents = join_clips(sc_clips, sc["sentences"], L, sr)
            write_wav(vdir / f"{sc['id']}.wav", audio, sr)
            scenes.append({"id": sc["id"], "duration": round(len(audio) / sr, 3), "sentences": sents})
        total = sum(s["duration"] for s in scenes)
        lo, hi = 0.7 * L["target_seconds"], L.get("max_seconds", 1.5 * L["target_seconds"])
        log(f"    narration total {total:.1f}s (target {L['target_seconds']}s, flex up to {hi:.0f}s)")
        if not lo <= total <= hi:
            log("    warning: narration length is outside the target range; trim the script or adjust the pace")
        write_json(vdir / "timing.json", {"sample_rate": sr, "total": round(total, 3), **info, "scenes": scenes})
