from __future__ import annotations

import copy
from pathlib import Path

import yaml

from . import localconf
from .util import REPO_ROOT, log

ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _coerce(value: str):
    try:
        return yaml.safe_load(value)
    except yaml.YAMLError:
        return value


LOCAL_KEYS = {  # ~/.config/explainer/config key -> (config path, type)
    "EXPLAINER_VOICE": ("voice.use", str),
    "EXPLAINER_LLM": ("llm.writer", str),
    "EXPLAINER_LLM_MODEL": ("llm.model", str),
    "EXPLAINER_LLM_TIMEOUT": ("llm.timeout", float),
    "EXPLAINER_LLM_RETRIES": ("llm.retries", int),
    "EXPLAINER_CLAUDE_BIN": ("llm.claude_bin", str),
}


def apply_local(cfg: dict, local: dict[str, str]) -> list[str]:
    applied = []
    for key, (path, typ) in LOCAL_KEYS.items():
        if not local.get(key):
            continue
        try:
            value = typ(local[key])
        except ValueError:
            raise SystemExit(f"{key}={local[key]!r} in {localconf.config_path()} is not a valid {typ.__name__}")
        section, _, leaf = path.partition(".")
        cfg.setdefault(section, {})[leaf] = value
        applied.append(f"{path}={value}")
    return applied


def load_config(extra: list[str] | None = None, sets: list[str] | None = None,
                aspect: str | None = None, local: bool = True, topic: dict | None = None) -> dict:
    """config.yaml, then the topic brief's `config:`, then --config files, then machine-local settings, then --set."""
    cfg = deep_merge(yaml.safe_load((REPO_ROOT / "config.yaml").read_text()), topic or {})
    for path in extra or []:
        cfg = deep_merge(cfg, yaml.safe_load(Path(path).read_text()) or {})
    if local:
        applied = apply_local(cfg, localconf.load())
        if applied:
            log(f"local settings: {', '.join(applied)}")
    for item in sets or []:
        key, _, val = item.partition("=")
        node = cfg
        parts = key.strip().split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = _coerce(val)
    if aspect:
        cfg["video"]["aspect"] = aspect
    if cfg["video"]["aspect"] not in ASPECTS:
        raise SystemExit(f"unsupported aspect {cfg['video']['aspect']!r}; use one of {list(ASPECTS)}")
    return cfg


def frame_size(cfg: dict) -> tuple[int, int]:
    return ASPECTS[cfg["video"]["aspect"]]


def aspect_tag(cfg: dict) -> str:
    return cfg["video"]["aspect"].replace(":", "x")
