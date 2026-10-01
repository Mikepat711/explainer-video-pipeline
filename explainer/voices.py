"""Audition TTS voices on the same paragraph: `python -m explainer voices`."""
from __future__ import annotations

import time
from pathlib import Path

from .stages.voice import join_clips, paced_clips
from .tts import ENGINES, KokoroEngine, resolve_voice, with_voice
from .util import REPO_ROOT, log, run, split_sentences, write_json, write_wav

SAMPLE_TEXT = (
    "Flip a switch, and electricity reaches you from a power plant hundreds of kilometers away, in a fraction of "
    "a second. On the way, it's boosted to 400,000 volts, then stepped back down to the 120 volts at your wall. "
    "And the whole grid has to balance supply and demand, second by second, to keep humming at 60 Hz."
)
PIPER_SUGGESTIONS = ["en_US-lessac-high", "en_US-ryan-high", "en_US-lessac-medium", "en_US-amy-medium",
                     "en_GB-cori-high", "en_GB-alba-medium"]


def presets(cfg: dict) -> list[str]:
    return list((cfg["voice"].get("presets") or {}).keys())


def list_voices(cfg: dict) -> None:
    current = resolve_voice(cfg)["spec"] if cfg["voice"].get("use") != "auto" else "auto"
    print(f"current voice: {current}  (voice.use in config.yaml, or EXPLAINER_VOICE in ~/.config/explainer/config)")
    print(f"pace: {resolve_voice(cfg).get('target_wpm') or 'native'} wpm target\n")
    print("presets (voice.presets):")
    for spec in presets(cfg):
        engine = spec.partition(":")[0]
        ok = ENGINES[engine].available(cfg) if engine in ENGINES else False
        settings = ", ".join(f"{k}={v}" for k, v in (cfg["voice"]["presets"][spec] or {}).items())
        hint = "" if ok else f"  (not installed: {getattr(ENGINES.get(engine), 'setup_hint', '') or 'pip install'})"
        print(f"  {spec:24s} {settings}{hint}")
    if KokoroEngine.available():
        print("\nall kokoro voices (use kokoro:<id>; af_/am_ American, bf_/bm_ British female/male):")
        kokoro = KokoroEngine(dict(cfg, voice=resolve_voice(with_voice(cfg, "kokoro:af_heart"))))
        print("  " + ", ".join(kokoro.voices()))
    print("\npiper (piper:<id>; any id from https://huggingface.co/rhasspy/piper-voices):")
    print("  " + ", ".join(PIPER_SUGGESTIONS))
    print("chatterbox: `chatterbox` (default male voice) or `chatterbox:<reference.wav>` to clone a voice")
    print("parler: parler:<speaker>, e.g. parler:Jon, parler:Laura, parler:Gary")
    print("espeak (robotic fallback): espeak:en-us")


def audition(cfg: dict, specs: list[str], text: str, out_dir: Path) -> list[dict]:
    sr = cfg["audio"]["sample_rate"]
    sentences = split_sentences(text)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in specs:
        c = with_voice(cfg, spec)
        engine = resolve_voice(c)["engine"]
        if not ENGINES[engine].available(c):
            log(f"  skip {spec}: engine not installed {getattr(ENGINES[engine], 'setup_hint', '')}".rstrip())
            continue
        t0 = time.time()
        clips, info = paced_clips(c, [sentences], sr, REPO_ROOT / ".cache" / "tts-audition")
        audio, _ = join_clips(clips[0], sentences, c["length"], sr, lead_in=0.3, tail=0.6)
        name = f"voice-{spec.replace(':', '-').replace('/', '_')}"
        wav = out_dir / f"{name}.wav"
        write_wav(wav, audio, sr)
        mp3 = out_dir / f"{name}.mp3"
        run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(sr),
             "-ac", "1", "-c:a", "libmp3lame", "-b:a", "160k", "-map_metadata", "-1", "-fflags", "+bitexact",
             str(mp3)])
        res = {"voice": spec, **info, "file": mp3.name, "seconds": round(len(audio) / sr, 2),
               "synth_seconds": round(time.time() - t0, 1)}
        log(f"  {spec:24s} {res['seconds']:5.1f}s  {info['wpm']:5.1f} wpm (speed {info['speed']}, "
            f"tempo {info['tempo']})  -> {mp3}")
        results.append(res)
    write_json(out_dir / "voices.json", {"text": text, "results": results})
    return results
