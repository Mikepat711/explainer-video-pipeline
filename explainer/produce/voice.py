"""Bundle narration: existing TTS engines, toolkit-style per-sentence timing."""
from __future__ import annotations

import numpy as np

from ..pipeline import Stage
from ..tts import ElevenLabsEngine, TTSUnavailable, get_engine, warn_fallback, with_voice
from ..util import log, read_json, write_json, write_wav
from ..wordtime import find_binary, find_model, whisper_words
from .context import BundleContext

DEFAULT_VOICE = "kokoro:af_heart"
DEFAULT_TIMING = {
    "lead": 0.7,
    "tail": 1.0,
    "gap": 0.55,
    "comma_gap": 0.22,
    "tails": {},
}


def bundle_voice_spec(ctx: BundleContext) -> str:
    chosen = str(ctx.cfg.get("voice", {}).get("use") or "").strip()
    if chosen:
        return chosen
    return ctx.bundle.manifest.voice or DEFAULT_VOICE


def bundle_cfg(ctx: BundleContext) -> dict:
    spec = bundle_voice_spec(ctx)
    cfg = with_voice(ctx.cfg, spec)
    speed = ctx.bundle.manifest.timing.get("speed")
    if speed is not None:
        cfg = dict(cfg, voice=dict(cfg["voice"], speed=float(speed)))
        presets = dict((ctx.cfg.get("voice") or {}).get("presets") or {})
        # with_voice copies presets via load_config; apply speed onto the resolved use.
        cfg["voice"] = dict(cfg["voice"], use=spec)
        if spec not in (presets or {}):
            pass
        cfg["voice"]["presets"] = dict(presets, **{spec: dict(presets.get(spec) or {}, speed=float(speed))})
    return cfg


def synthesize_bundle_voice(ctx: BundleContext, cfg: dict, engine, sr: int) -> dict:
    from ..stages.voice import synthesize_clips, trim_silence

    T = {**DEFAULT_TIMING, **(ctx.bundle.manifest.timing or {})}
    tails = dict(T.get("tails") or {})
    vdir = ctx.common / "voice"
    vdir.mkdir(parents=True, exist_ok=True)
    cache = vdir / "sentences"
    scenes_out = []
    for sc in ctx.bundle.scenes:
        texts = sc.spoken
        clips = synthesize_clips(engine, texts, sr, cache)
        # synthesize_clips already trims; keep toolkit-like comma vs sentence gaps
        parts = [np.zeros(int(float(T["lead"]) * sr), np.float32)]
        t = float(T["lead"])
        segs = []
        for i, (clip, (cap, _)) in enumerate(zip(clips, sc.sentences)):
            x = trim_silence(np.asarray(clip, np.float32), sr)
            d = len(x) / sr
            segs.append({"text": cap, "spoken": texts[i], "start": round(t, 3), "end": round(t + d, 3)})
            parts.append(x)
            t += d
            if i < len(sc.sentences) - 1:
                gap = float(T["comma_gap"] if cap.endswith(",") else T["gap"])
                parts.append(np.zeros(int(gap * sr), np.float32))
                t += gap
        tail = float(tails.get(sc.id, T["tail"]))
        parts.append(np.zeros(int(tail * sr), np.float32))
        t += tail
        audio = np.concatenate(parts)
        write_wav(vdir / f"{sc.id}.wav", audio, sr)
        scenes_out.append({
            "id": sc.id, "index": sc.index, "title": sc.title,
            "duration": round(len(audio) / sr, 3), "sentences": segs,
        })
    total = sum(s["duration"] for s in scenes_out)
    info = {
        "sample_rate": sr,
        "total": round(total, 3),
        "engine": engine.identity(),
        "voice": bundle_voice_spec(ctx),
        "timing": {k: T[k] for k in ("lead", "tail", "gap", "comma_gap")},
        "tails": tails,
        "scenes": scenes_out,
    }
    write_json(vdir / "timing.json", info)
    return info


def maybe_word_times(ctx: BundleContext, cfg: dict) -> dict:
    """Optional whisper.cpp word times per scene, used by scene code and SFX."""
    caps = cfg.get("captions") or {}
    if str(caps.get("word_timing") or "auto") == "off":
        return {}
    binary = find_binary(caps.get("whisper_bin") or "")
    model = find_model(caps.get("whisper_model") or "")
    if not binary or not model:
        log("    word timing: whisper-cli or model not found; scene defaults will be used")
        return {}
    words = {}
    for sc in ctx.bundle.scenes:
        wav = ctx.common / "voice" / f"{sc.id}.wav"
        heard = whisper_words(wav, model, binary)
        if not heard:
            continue
        words[sc.id] = [[w["text"], round(w["start"], 3), round(w.get("end", w["start"]), 3)] for w in heard]
    write_json(ctx.common / "voice" / "words.json", words)
    return words


class Voice(Stage):
    name = "voice"
    scope = "common"
    deps = ()
    extra_code = ("tts", "textnorm.py", "produce/voice.py")
    owns = ("voice/*.wav",)
    description = "synthesize narration per sentence (Kokoro / ElevenLabs) with per-sentence timing"

    def still_fresh(self, ctx):
        tp = ctx.common / "voice" / "timing.json"
        info = read_json(tp) if tp.exists() else {}
        spec = bundle_voice_spec(ctx)
        return not (info.get("fallback") and spec.startswith("elevenlabs")
                    and info.get("fallback") != "no API key" and ElevenLabsEngine.available(ctx.cfg))

    def inputs(self, ctx):
        man = ctx.bundle.manifest
        return {
            "voice": bundle_voice_spec(ctx),
            "script": [(s.id, s.spoken) for s in ctx.bundle.scenes],
            "timing": man.timing,
            "sr": ctx.cfg["audio"]["sample_rate"],
        }

    def outputs(self, ctx):
        vdir = ctx.common / "voice"
        return [vdir / "timing.json", *[vdir / f"{s.id}.wav" for s in ctx.bundle.scenes]]

    def run(self, ctx):
        cfg = bundle_cfg(ctx)
        spec = bundle_voice_spec(ctx)
        sr = int(ctx.cfg["audio"]["sample_rate"])
        reason = None
        try:
            engine = get_engine(cfg)
        except (SystemExit, TTSUnavailable) as e:
            fallback = str((cfg.get("voice") or {}).get("fallback") or DEFAULT_VOICE)
            if spec == "silence" or spec.startswith("silence:") or fallback == spec:
                raise
            warn_fallback(spec, fallback, str(e))
            engine = get_engine(with_voice(cfg, fallback))
            reason = str(e)
        info = synthesize_bundle_voice(ctx, cfg, engine, sr)
        if reason:
            info["fallback"] = reason
            write_json(ctx.common / "voice" / "timing.json", info)
            log(f"    WARNING: narration used the fallback voice ({reason})")
        log(f"    voice {info['engine']}: {info['total']:.1f}s, {len(info['scenes'])} scenes")
        maybe_word_times(ctx, cfg)
