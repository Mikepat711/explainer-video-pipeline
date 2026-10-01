"""Machine-local settings: `~/.config/explainer/config`, shell-style KEY=VALUE lines.

    # ~/.config/explainer/config
    EXPLAINER_VOICE=kokoro:bm_fable      # overrides voice.use from config.yaml
    EXPLAINER_LLM_MODEL=opus             # model alias passed to `claude --model`
    EXPLAINER_CLAUDE_BIN=/path/to/claude # only if `claude` is not on PATH

Environment variables with the same names win over the file. `EXPLAINER_CONFIG` points at
a different file. Nothing secret belongs here: Claude Code keeps its own sign-in.
"""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

KEYS = {
    "EXPLAINER_VOICE": "voice preset or engine:voice, e.g. kokoro:af_heart (overrides voice.use)",
    "EXPLAINER_LLM_MODEL": "Claude model alias for the script/plan writer (default: opus)",
    "EXPLAINER_CLAUDE_BIN": "path to the Claude Code CLI if `claude` is not on PATH",
    "EXPLAINER_LLM_TIMEOUT": "seconds per Claude call before it is killed and retried",
    "EXPLAINER_LLM_RETRIES": "extra attempts after a failed or invalid Claude reply",
    "EXPLAINER_LLM": "claude | off (off forces the offline fallback writer)",
    "EXPLAINER_FFMPEG": "ffmpeg binary with libass, for burned-in captions",
}
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def config_path() -> Path:
    if os.environ.get("EXPLAINER_CONFIG"):
        return Path(os.environ["EXPLAINER_CONFIG"]).expanduser()
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "explainer" / "config"


def parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        raw = m.group(2).strip()
        try:
            parts = shlex.split(raw, comments=True)
        except ValueError:
            parts = [raw]
        val = " ".join(parts)
        out[m.group(1)] = os.path.expandvars(os.path.expanduser(val)) if val else ""
    return out


def load() -> dict[str, str]:
    p = config_path()
    vals = parse(p.read_text()) if p.is_file() else {}
    for k in list(vals) + [k for k in os.environ if k.startswith("EXPLAINER_")]:
        if os.environ.get(k):
            vals[k] = os.environ[k]
    return vals


def get(key: str, default: str | None = None) -> str | None:
    v = load().get(key)
    return v if v not in (None, "") else default
