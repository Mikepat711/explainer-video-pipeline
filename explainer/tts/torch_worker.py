"""Standalone synthesis worker for PyTorch TTS engines (Chatterbox, Parler).

Runs inside the engine's own virtualenv, so it imports nothing from the explainer package:

    .venv-chatterbox/bin/python explainer/tts/torch_worker.py job.json

job.json: {"engine": "chatterbox"|"parler", "device": "auto"|"cpu"|"mps"|"cuda",
           "options": {...}, "items": [{"text": "...", "out": "/path/sentence.wav"}, ...]}
"""
from __future__ import annotations

import json
import sys
import time
import zlib
from pathlib import Path


def say(msg: str) -> None:
    print(f"[worker] {msg}", file=sys.stderr, flush=True)


def pick_device(want: str) -> str:
    import torch
    if want and want != "auto":
        return want
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def seed_for(text: str, base: int) -> int:
    return (zlib.crc32(text.encode()) + base) % (2 ** 31)


def chatterbox(job: dict, device: str):
    from chatterbox.tts import ChatterboxTTS
    try:
        model = ChatterboxTTS.from_pretrained(device=device)
    except Exception as exc:  # some torch builds lack an MPS kernel the model needs
        if device == "cpu":
            raise
        say(f"{device} failed ({exc.__class__.__name__}: {exc}); falling back to cpu")
        device, model = "cpu", ChatterboxTTS.from_pretrained(device="cpu")
    o = job["options"]

    def synth(text: str):
        wav = model.generate(text, exaggeration=float(o.get("exaggeration", 0.5)),
                             cfg_weight=float(o.get("cfg_weight", 0.5)), audio_prompt_path=o.get("prompt") or None)
        return wav.squeeze(0).detach().cpu().numpy(), model.sr

    return synth, device


def parler(job: dict, device: str):
    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer
    o = job["options"]
    repo = o.get("model", "parler-tts/parler-tts-mini-v1.1")
    model = ParlerTTSForConditionalGeneration.from_pretrained(repo).to(device)
    tok = AutoTokenizer.from_pretrained(repo)
    dtok = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
    desc = dtok(o["description"], return_tensors="pt").to(device)

    def synth(text: str):
        prompt = tok(text, return_tensors="pt").to(device)
        gen = model.generate(input_ids=desc.input_ids, attention_mask=desc.attention_mask,
                             prompt_input_ids=prompt.input_ids, prompt_attention_mask=prompt.attention_mask)
        return gen.detach().cpu().float().numpy().squeeze(), model.config.sampling_rate

    return synth, device


def main(path: str) -> int:
    import soundfile as sf
    import torch
    job = json.loads(Path(path).read_text())
    loaders = {"chatterbox": chatterbox, "parler": parler}
    if job["engine"] not in loaders:
        say(f"unknown engine {job['engine']!r}")
        return 2
    t0 = time.time()
    synth, device = loaders[job["engine"]](job, pick_device(job.get("device", "auto")))
    say(f"{job['engine']} loaded on {device} in {time.time() - t0:.0f}s")
    base = int(job["options"].get("seed", 0))
    for i, item in enumerate(job["items"], 1):
        t1 = time.time()
        torch.manual_seed(seed_for(item["text"], base))
        audio, sr = synth(item["text"])
        out = Path(item["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out), audio, sr)
        say(f"{i}/{len(job['items'])} done in {time.time() - t1:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
