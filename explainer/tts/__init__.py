"""Pluggable text-to-speech engines.

The voice is chosen by one setting, `voice.use` ("engine:voice", e.g. elevenlabs:river or
kokoro:af_heart), with per-voice settings from `voice.presets` (an engine-wide preset such as
`elevenlabs` applies first, then the exact spec). If the chosen engine is unavailable (no API key) or
fails at run time (quota, network), narration falls back to `voice.fallback` with a warning. Every engine implements `synthesize(text, out_wav)`
writing a mono WAV at any sample rate (the voice stage resamples); `synthesize_many` batches.
Add an engine by subclassing `TTSEngine` and registering it in ENGINES.
"""
from __future__ import annotations

import re

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from ..util import REPO_ROOT, log, run, sha256_json, write_wav

VOICE_DIR = Path(os.environ.get("EXPLAINER_VOICE_DIR", REPO_ROOT / ".cache" / "voices"))
KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"    downloading {dest.name} …")
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)


class TTSUnavailable(RuntimeError):
    """The engine cannot speak right now (no key, quota, network); a fallback voice can take over."""


class TTSEngine:
    name = "base"
    speed_param = ""  # config key that scales the speaking rate natively (larger = faster), if any

    def identity(self) -> dict:
        return {"engine": self.name}

    def synthesize(self, text: str, out_wav: Path) -> None:
        raise NotImplementedError

    def synthesize_many(self, items: list[tuple[str, Path]]) -> None:
        for text, out in items:
            self.synthesize(text, out)


class KokoroEngine(TTSEngine):
    """Kokoro-82M (Apache-2.0) through kokoro-onnx: the most natural of the offline voices.

    Model files (~350 MB) download to the voice cache on first use. Voice ids start with a
    language/gender prefix: af_/am_ = American female/male, bf_/bm_ = British female/male.
    """
    name = "kokoro"
    speed_param = "speed"
    LANGS = {"a": "en-us", "b": "en-gb", "e": "es", "f": "fr-fr", "h": "hi", "i": "it", "p": "pt-br"}

    def __init__(self, cfg: dict):
        v = cfg["voice"]
        self.voice = v.get("kokoro_voice", "af_heart")
        self.speed = float(v.get("speed", 0.9))
        self.model = v.get("kokoro_model", "kokoro-v1.0.onnx")
        self._tts = None

    @staticmethod
    def available(cfg=None) -> bool:
        try:
            import kokoro_onnx  # noqa: F401
            return True
        except ImportError:
            return False

    def identity(self):
        return {"engine": self.name, "voice": self.voice, "speed": round(self.speed, 4), "model": self.model}

    def _load(self):
        if self._tts is None:
            from kokoro_onnx import Kokoro
            d = VOICE_DIR / "kokoro"
            model, voices = d / self.model, d / "voices-v1.0.bin"
            for f in (model, voices):
                if not f.exists():
                    _download(f"{KOKORO_RELEASE}/{f.name}", f)
            self._tts = Kokoro(str(model), str(voices))
            if self.voice not in self._tts.get_voices():
                raise SystemExit(f"unknown kokoro voice {self.voice!r}; run `python -m explainer voices --list`")
        return self._tts

    def voices(self) -> list[str]:
        return sorted(self._load().get_voices())

    def synthesize(self, text, out_wav):
        samples, sr = self._load().create(text, voice=self.voice, speed=self.speed,
                                          lang=self.LANGS.get(self.voice[:1], "en-us"))
        write_wav(Path(out_wav), samples, sr)


class PiperEngine(TTSEngine):
    """Local neural TTS (https://github.com/OHF-Voice/piper1-gpl). Voices auto-download on first use."""
    name = "piper"
    speed_param = "speed"

    def __init__(self, cfg: dict):
        v = cfg["voice"]
        self.voice = v["piper_voice"]
        self.length_scale = 1.0 / float(v["speed"]) if v.get("speed") else float(v.get("length_scale", 1.0))
        self._model = None

    @staticmethod
    def available(cfg=None) -> bool:
        try:
            import piper  # noqa: F401
            return True
        except ImportError:
            return False

    def identity(self):
        return {"engine": self.name, "voice": self.voice, "length_scale": round(self.length_scale, 4)}

    def _load(self):
        if self._model is None:
            from piper import PiperVoice
            VOICE_DIR.mkdir(parents=True, exist_ok=True)
            onnx = VOICE_DIR / f"{self.voice}.onnx"
            if not onnx.exists():
                log(f"    downloading piper voice {self.voice} …")
                run([sys.executable, "-m", "piper.download_voices", "--download-dir", str(VOICE_DIR),
                     self.voice])
            self._model = PiperVoice.load(str(onnx))
        return self._model

    def synthesize(self, text, out_wav):
        from piper import SynthesisConfig
        voice = self._load()
        with wave.open(str(out_wav), "wb") as w:
            voice.synthesize_wav(text, w, SynthesisConfig(length_scale=self.length_scale))


class EspeakEngine(TTSEngine):
    """espeak-ng: robotic but tiny, always-available fallback."""
    name = "espeak"

    def __init__(self, cfg):
        self.voice = cfg["voice"].get("espeak_voice", "en-us")
        self.wpm = int(cfg["voice"].get("espeak_wpm", 165))
        self.bin = shutil.which("espeak-ng") or shutil.which("espeak")

    @staticmethod
    def available(cfg=None):
        return bool(shutil.which("espeak-ng") or shutil.which("espeak"))

    def identity(self):
        return {"engine": self.name, "voice": self.voice, "wpm": self.wpm}

    def synthesize(self, text, out_wav):
        run([self.bin, "-v", self.voice, "-s", str(self.wpm), "-w", str(out_wav), text])


class OpenAIEngine(TTSEngine):
    """OpenAI-compatible /audio/speech endpoint (needs OPENAI_API_KEY)."""
    name = "openai"

    def __init__(self, cfg):
        self.model = cfg["voice"].get("openai_model", "gpt-4o-mini-tts")
        self.voice = cfg["voice"].get("openai_voice", "alloy")

    @staticmethod
    def available(cfg=None):
        return bool(os.environ.get("OPENAI_API_KEY"))

    def identity(self):
        return {"engine": self.name, "model": self.model, "voice": self.voice}

    def synthesize(self, text, out_wav):
        import json
        import urllib.request
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        body = json.dumps({"model": self.model, "voice": self.voice, "input": text,
                           "response_format": "wav"}).encode()
        req = urllib.request.Request(f"{base}/audio/speech", data=body, headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            Path(out_wav).write_bytes(r.read())


class SilenceEngine(TTSEngine):
    """Inaudible speech sized from word count (~160 wpm). For tests and layout review, not delivery."""
    name = "silence"

    def __init__(self, cfg=None):
        self.wpm = 160

    @staticmethod
    def available(cfg=None):
        return True

    def identity(self):
        return {"engine": self.name, "wpm": self.wpm}

    def synthesize(self, text, out_wav):
        import numpy as np
        words = max(1, len(str(text).split()))
        dur = max(0.35, words / self.wpm * 60)
        write_wav(Path(out_wav), np.zeros(int(dur * 24000), np.float32), 24000)


class CommandEngine(TTSEngine):
    """Any CLI: `voice.command` with {text} and {out} placeholders (output in any ffmpeg-readable format)."""
    name = "command"

    def __init__(self, cfg):
        self.template = cfg["voice"].get("command", "")

    @staticmethod
    def available(cfg=None):
        return True

    def identity(self):
        return {"engine": self.name, "command": self.template}

    def synthesize(self, text, out_wav):
        if not self.template:
            raise SystemExit("voice.use=command requires voice.command, e.g. 'say -o {out} {text}'")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "speech.aiff"
            cmd = self.template.format(text=shlex.quote(text), out=shlex.quote(str(tmp)))
            subprocess.run(cmd, shell=True, check=True)
            run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp), str(out_wav)])


ELEVENLABS_API = "https://api.elevenlabs.io/v1"


def elevenlabs_key_file() -> Path:
    """`elevenlabs.env` next to the machine-local config (default ~/.config/explainer/elevenlabs.env)."""
    from ..localconf import config_path
    override = os.environ.get("EXPLAINER_ELEVENLABS_KEY_FILE")
    return Path(override).expanduser() if override else config_path().parent / "elevenlabs.env"


def elevenlabs_key() -> str | None:
    """ELEVENLABS_API_KEY from the environment, else from the key file. Never logged."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    f = elevenlabs_key_file()
    if f.is_file():
        from ..localconf import parse
        return parse(f.read_text()).get("ELEVENLABS_API_KEY") or None
    return None


class ElevenLabsEngine(TTSEngine):
    """ElevenLabs text-to-speech over its REST API (needs an API key; billed per character).

    Voices are ElevenLabs voice ids or names from `voice.elevenlabs.voices` (elevenlabs:river).
    Every reply is kept in the voice cache keyed by text, voice and settings, so re-renders, cleaned
    builds and other topics never pay for the same sentence twice.
    """
    name = "elevenlabs"
    speed_param = "speed"
    SETTINGS = ("stability", "similarity_boost", "style", "speaker_boost")

    def __init__(self, cfg: dict):
        v = cfg["voice"]
        el = dict(v.get("elevenlabs") or {})
        el.update({k: v[k] for k in self.SETTINGS if k in v})  # a preset may override any setting
        voices = {str(k).lower(): str(x) for k, x in (el.get("voices") or {}).items()}
        self.voice = str(v.get("elevenlabs_voice") or el.get("voice") or "river")
        self.voice_id = voices.get(self.voice.lower(), self.voice)
        self.model = str(el.get("model") or "eleven_multilingual_v2")
        self.output_format = str(el.get("output_format") or "mp3_44100_128")
        self.speed = min(1.2, max(0.7, float(v.get("speed", 1.0))))  # the API accepts 0.7-1.2
        self.settings = {"stability": float(el.get("stability", 0.5)),
                         "similarity_boost": float(el.get("similarity_boost", 0.75)),
                         "style": float(el.get("style", 0.0)),
                         "use_speaker_boost": bool(el.get("speaker_boost", True)),
                         "speed": self.speed}
        self.seed = el.get("seed")
        self.timeout = float(el.get("timeout", 60))
        self.retries = int(el.get("retries", 2))
        self.billed_chars = 0

    @staticmethod
    def available(cfg=None) -> bool:
        return bool(elevenlabs_key())

    def identity(self):
        return {"engine": self.name, "voice_id": self.voice_id, "model": self.model, "format": self.output_format,
                "settings": self.settings, "seed": self.seed}

    def cache_path(self, text: str) -> Path:
        ext = self.output_format.split("_")[0]
        return VOICE_DIR / "elevenlabs" / f"{sha256_json({'t': text, **self.identity()})[:24]}.{ext}"

    def _request(self, text: str) -> bytes:
        key = elevenlabs_key()
        if not key:
            raise TTSUnavailable(f"no ElevenLabs API key (set ELEVENLABS_API_KEY or create {elevenlabs_key_file()})")
        body = {"text": text, "model_id": self.model, "voice_settings": self.settings}
        if self.seed is not None:
            body["seed"] = int(self.seed)
        req = urllib.request.Request(
            f"{ELEVENLABS_API}/text-to-speech/{self.voice_id}?output_format={self.output_format}",
            data=json.dumps(body).encode(), method="POST",
            headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/*"})
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                try:
                    detail = json.loads(e.read().decode() or "{}").get("detail") or {}
                except (ValueError, UnicodeDecodeError):
                    detail = {}
                if isinstance(detail, dict):
                    why = ": ".join(str(x) for x in (detail.get("status"), detail.get("message")) if x)
                else:
                    why = str(detail)[:200]
                retry = (e.code == 429 or e.code >= 500) and "quota" not in why
                if not retry or attempt == self.retries:
                    raise TTSUnavailable(f"ElevenLabs HTTP {e.code}{': ' + why if why else ''}") from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt == self.retries:
                    raise TTSUnavailable(f"ElevenLabs unreachable: {getattr(e, 'reason', e)}") from None
            time.sleep(2 ** attempt)
        raise TTSUnavailable("ElevenLabs request failed")

    def fetch(self, text: str) -> Path:
        """Encoded audio for `text`, from the cache or the API."""
        path = self.cache_path(text)
        if not path.exists():
            audio = self._request(text)
            path.parent.mkdir(parents=True, exist_ok=True)
            part = path.with_suffix(path.suffix + ".part")
            part.write_bytes(audio)
            part.replace(path)
            self.billed_chars += len(text)
        return path

    def synthesize(self, text, out_wav):
        run(["ffmpeg", "-y", "-v", "error", "-i", str(self.fetch(text)), "-ac", "1", str(out_wav)])

    def synthesize_many(self, items):
        cached = sum(self.cache_path(t).exists() for t, _ in items)
        before = self.billed_chars
        for text, out in items:
            self.synthesize(text, out)
        if items:
            log(f"    elevenlabs {self.voice}: {len(items) - cached} sentence(s) synthesized, {cached} from cache, "
                f"{self.billed_chars - before} characters billed")


WORKER = Path(__file__).with_name("torch_worker.py")


def _repo_path(p: str) -> Path:
    q = Path(p).expanduser()
    return q if q.is_absolute() else REPO_ROOT / q


class TorchWorkerEngine(TTSEngine):
    """A PyTorch TTS model run in its own virtualenv (pinned torch) through tts/torch_worker.py.

    The model loads once per batch. A worker that dies or overruns its time budget fails the
    stage instead of hanging it.
    """
    python_key = ""
    setup_hint = ""

    def __init__(self, cfg: dict):
        v = cfg["voice"]
        self.v = v
        self.python = _repo_path(v.get(self.python_key) or "")
        self.device = v.get("torch_device", "auto")
        self.per_item = float(v.get("worker_seconds_per_sentence", 120))

    @classmethod
    def available(cls, cfg=None) -> bool:
        v = (cfg or {}).get("voice", {})
        default = {"chatterbox_python": ".venv-chatterbox/bin/python", "parler_python": ".venv-parler/bin/python"}
        return _repo_path(v.get(cls.python_key) or default[cls.python_key]).is_file()

    def options(self) -> dict:
        raise NotImplementedError

    def identity(self):
        return {"engine": self.name, **self.options()}

    def synthesize(self, text, out_wav):
        self.synthesize_many([(text, Path(out_wav))])

    def synthesize_many(self, items):
        if not items:
            return
        if not self.python.is_file():
            raise SystemExit(f"voice engine {self.name} is not installed: {self.setup_hint}")
        job = {"engine": self.name, "device": self.device, "options": self.options(),
               "items": [{"text": t, "out": str(o)} for t, o in items]}
        with tempfile.TemporaryDirectory() as td:
            jf = Path(td) / "job.json"
            jf.write_text(json.dumps(job))
            budget = 300 + self.per_item * len(items)
            log(f"    {self.name}: synthesizing {len(items)} sentence(s) (time budget {budget:.0f}s)")
            proc = subprocess.Popen([str(self.python), str(WORKER), str(jf)], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, text=True, start_new_session=True)
            timer = threading.Timer(budget, proc.kill)
            timer.start()
            tail: list[str] = []
            try:
                for line in proc.stderr:
                    line = line.rstrip()
                    tail = (tail + [line])[-30:]
                    if line.startswith("[worker]"):
                        log(f"    {line}")
                rc = proc.wait()
            finally:
                timer.cancel()
        if rc != 0:
            why = "timed out and was killed" if rc in (-9, 137) else f"exited with code {rc}"
            raise SystemExit(f"{self.name} worker {why}:\n" + "\n".join(tail[-15:]))
        missing = [str(o) for _, o in items if not Path(o).exists()]
        if missing:
            raise SystemExit(f"{self.name} worker produced no audio for {len(missing)} sentence(s)")


class ChatterboxEngine(TorchWorkerEngine):
    """Chatterbox (Resemble AI, MIT): expressive male default voice; outputs carry an inaudible watermark.

    `chatterbox:<reference.wav>` clones the voice of a short reference clip instead.
    """
    name = "chatterbox"
    python_key = "chatterbox_python"
    setup_hint = "run `make setup-chatterbox`"

    def options(self):
        prompt = self.v.get("chatterbox_prompt")
        return {"exaggeration": float(self.v.get("exaggeration", 0.5)), "cfg_weight": float(self.v.get("cfg_weight", 0.5)),
                "seed": int(self.v.get("seed", 7)), "prompt": str(_repo_path(prompt)) if prompt else None}


class ParlerEngine(TorchWorkerEngine):
    """Parler-TTS mini v1.1 (Apache-2.0): named speakers steered by a text description."""
    name = "parler"
    python_key = "parler_python"
    setup_hint = "run `make setup-parler`"

    def options(self):
        speaker = self.v.get("parler_speaker", "Jon")
        desc = str(self.v.get("parler_description", "{speaker}'s voice is warm and clear.")).format(speaker=speaker)
        return {"model": self.v.get("parler_model", "parler-tts/parler-tts-mini-v1.1"), "speaker": speaker,
                "description": desc, "seed": int(self.v.get("seed", 3))}


ENGINES = {"elevenlabs": ElevenLabsEngine, "kokoro": KokoroEngine, "piper": PiperEngine, "chatterbox": ChatterboxEngine, "parler": ParlerEngine,
           "espeak": EspeakEngine, "openai": OpenAIEngine, "command": CommandEngine, "silence": SilenceEngine}
AUTO_ORDER = ("kokoro", "piper", "espeak")
VOICE_KEYS = {"elevenlabs": "elevenlabs_voice", "kokoro": "kokoro_voice", "piper": "piper_voice", "espeak": "espeak_voice", "openai": "openai_voice",
              "parler": "parler_speaker", "chatterbox": "chatterbox_prompt"}


def resolve_voice(cfg: dict, **overrides) -> dict:
    """voice config with `use` expanded: engine, the engine's voice key, and the preset's settings."""
    v = dict(cfg["voice"])
    if not str(v.get("use") or "").strip():
        raise SystemExit(narrator_required(cfg))
    spec = str(v.get("use"))
    if spec == "auto":
        engine = next((n for n in AUTO_ORDER if ENGINES[n].available(cfg)), None)
        if not engine:
            raise SystemExit("no TTS engine available: `pip install kokoro-onnx` (or piper-tts), or install espeak-ng")
        spec = engine
    engine, _, name = spec.partition(":")
    if engine not in ENGINES:
        raise SystemExit(f"unknown voice {spec!r}: use engine:voice with engine one of {list(ENGINES)}")
    if engine == "elevenlabs" and name:
        name = elevenlabs_name(cfg, name)
        spec = f"{engine}:{name}"
    v["engine"], v["spec"] = engine, spec
    if name and engine in VOICE_KEYS:
        v[VOICE_KEYS[engine]] = name
    presets = v.get("presets") or {}
    if spec != engine:
        v.update(presets.get(engine) or {})  # engine-wide settings, e.g. `elevenlabs`
    v.update(presets.get(spec) or {})
    v.update(overrides)
    v.pop("presets", None)
    return v


def narrator_required(cfg: dict) -> str:
    choices = cfg["voice"].get("choices") or []
    picks = " or ".join(f"--voice {c}" for c in choices) or "--voice engine:voice"
    return (f"no narrator chosen: pick one for this video with {picks} "
            "(voice.use is empty on purpose; set it or EXPLAINER_VOICE to make one the default)")


def elevenlabs_name(cfg: dict, name: str) -> str:
    """A mapped ElevenLabs name in its canonical (lower-case) form, so `elevenlabs:Jessica` finds the
    `elevenlabs:jessica` preset; voice ids pass through; an unmapped plain word is a typo, reported with the
    names instead of being sent to the API (and silently falling back to the fallback voice)."""
    voices = {str(k).lower() for k in ((cfg["voice"].get("elevenlabs") or {}).get("voices") or {})}
    if name.lower() in voices:
        return name.lower()
    if not re.fullmatch(r"[A-Za-z]+", name) or re.fullmatch(r"[A-Za-z0-9]{20}", name):
        return name  # looks like a voice id (ElevenLabs ids are 20 mixed-case letters and digits)
    raise SystemExit(f"unknown ElevenLabs voice {name!r}: use one of {sorted(voices)} "
                     "(names in voice.elevenlabs.voices) or a voice id")


def with_voice(cfg: dict, spec: str) -> dict:
    """Config copy selecting a voice (e.g. 'kokoro:am_michael', 'chatterbox', 'parler:Jon')."""
    if spec.partition(":")[0] not in ENGINES:
        raise SystemExit(f"unknown engine in {spec!r}; choose from {list(ENGINES)}")
    return dict(cfg, voice=dict(cfg["voice"], use=spec))


_warned: set[str] = set()


def warn_fallback(spec: str, fallback: str, reason: str) -> None:
    msg = f"WARNING: voice {spec!r} unavailable ({reason}); narrating with fallback voice {fallback!r}"
    if msg not in _warned:
        _warned.add(msg)
        log(f"    {msg}")


def effective_cfg(cfg: dict) -> tuple[dict, str | None]:
    """cfg itself, or a copy using voice.fallback when the chosen engine cannot run on this machine."""
    v = resolve_voice(cfg)
    fallback = str(v.get("fallback") or "")
    if ENGINES[v["engine"]].available(cfg) or not fallback or fallback == v["spec"]:
        return cfg, None
    reason = "no API key" if v["engine"] == "elevenlabs" else "not installed"
    warn_fallback(v["spec"], fallback, reason)
    return with_voice(cfg, fallback), reason


def get_engine(cfg: dict, **overrides) -> TTSEngine:
    cfg, _ = effective_cfg(cfg)
    v = resolve_voice(cfg, **overrides)
    cls = ENGINES[v["engine"]]
    if not cls.available(cfg):
        hint = getattr(cls, "setup_hint", "")
        raise SystemExit(f"voice {v['spec']!r} is not available on this machine" + (f": {hint}" if hint else ""))
    return cls(dict(cfg, voice=v))
