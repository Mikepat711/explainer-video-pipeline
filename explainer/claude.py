"""Claude Code CLI as the built-in writer.

Runs `claude -p <prompt> --model <alias> --output-format json` headlessly (stdin closed,
empty working directory) and parses the envelope:

    {"type": "result", "subtype": "success", "is_error": false, "duration_ms": 3120, "result": "<text>"}

`result` must hold one JSON document (code fences tolerated) that passes the task's schema
and semantic checks; otherwise the call is retried with the errors appended to the prompt.
Sign-in is Claude Code's own; no API keys are read or stored here.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from .schema import validate
from .util import log

AUTH_HINTS = ("/login", "not logged in", "authenticat", "invalid api key", "oauth", "credit balance")


class ClaudeError(RuntimeError):
    """A call failed (timeout, crash, is_error, invalid reply)."""


class ClaudeUnavailable(ClaudeError):
    """The CLI cannot be used at all here (missing binary, signed out, disabled)."""


class InvalidReply(ClaudeError):
    def __init__(self, errors: list[str], raw: str):
        super().__init__("; ".join(errors[:3]))
        self.errors, self.raw = errors, raw


def resolve_bin(cfg: dict) -> str | None:
    explicit = cfg["llm"].get("claude_bin")
    if explicit:
        p = Path(explicit).expanduser()
        return str(p) if p.is_file() and os.access(p, os.X_OK) else None
    found = shutil.which("claude")
    if found:
        return found
    default_install = Path.home() / ".local" / "bin" / "claude"
    return str(default_install) if default_install.is_file() and os.access(default_install, os.X_OK) else None


def extract_json(text: str):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0] if "```" in t else t
    t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b <= a:
        raise InvalidReply(["the reply contained no JSON object"], text)
    try:
        return json.loads(t[a:b + 1])
    except json.JSONDecodeError as exc:
        raise InvalidReply([f"the reply is not valid JSON ({exc})"], text) from None


def parse_envelope(stdout: str) -> dict:
    out = stdout.strip()
    try:
        env = json.loads(out)
        if isinstance(env, dict):
            return env
    except json.JSONDecodeError:
        pass
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                env = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(env, dict) and ("result" in env or env.get("type") == "result"):
                return env
    raise ClaudeError(f"unreadable CLI output: {out[:300]!r}")


class ClaudeWriter:
    def __init__(self, cfg: dict):
        c = cfg["llm"]
        if str(c.get("writer", "claude")).lower() in ("offline", "off", "none", "false"):
            raise ClaudeUnavailable("disabled by config (llm.writer / EXPLAINER_LLM)")
        self.bin = resolve_bin(cfg)
        if not self.bin:
            raise ClaudeUnavailable("Claude Code CLI not found: put `claude` on PATH or set EXPLAINER_CLAUDE_BIN "
                                    "in ~/.config/explainer/config")
        self.model = str(c.get("model") or "opus")
        self.timeout = float(c.get("timeout", 900))
        self.retries = int(c.get("retries", 2))
        self.web = bool(c.get("web_research", True))
        self.extra = [str(a) for a in c.get("extra_args") or []]

    def identity(self) -> str:
        return f"claude:{self.model}"

    def command(self, prompt: str, web: bool) -> list[str]:
        cmd = [self.bin, "-p", prompt, "--model", self.model, "--output-format", "json",
               "--disallowedTools", "Bash,Edit,Write,NotebookEdit"]
        if web:
            cmd += ["--allowedTools", "WebSearch,WebFetch"]
        return cmd + self.extra

    def call(self, prompt: str, web: bool = False) -> dict:
        with tempfile.TemporaryDirectory(prefix="explainer-claude-") as td:
            proc = subprocess.Popen(self.command(prompt, web), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, cwd=td, start_new_session=True)
            try:
                out, err = proc.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.communicate()
                raise ClaudeError(f"no reply within {self.timeout:.0f}s (llm.timeout); process killed") from None
        if not out.strip():
            msg = (err or "").strip().splitlines()[-1:] or ["no output"]
            if any(h in (err or "").lower() for h in AUTH_HINTS):
                raise ClaudeUnavailable(f"Claude Code is not signed in: {msg[0]}")
            raise ClaudeError(f"exit code {proc.returncode}: {msg[0]}")
        env = parse_envelope(out)
        if env.get("is_error") or env.get("subtype") not in (None, "success"):
            text = str(env.get("result") or env.get("error") or env.get("subtype"))
            if any(h in text.lower() for h in AUTH_HINTS):
                raise ClaudeUnavailable(f"Claude Code is not signed in: {text[:200]}")
            raise ClaudeError(f"is_error ({env.get('subtype')}): {text[:300]}")
        return env

    def generate(self, task: str, prompt: str, schema: dict,
                 check: Callable[[dict], list[str]] | None = None, web: bool = False) -> tuple[dict, dict]:
        """Returns (payload, meta). Raises ClaudeUnavailable or ClaudeError after the last attempt."""
        attempts, current, last = [], prompt, "no attempt"
        for n in range(1, self.retries + 2):
            t0 = time.time()
            try:
                env = self.call(current, web=web and self.web)
                payload = extract_json(str(env.get("result", "")))
                errors = validate(payload, schema)
                if not errors and check:
                    errors = check(payload)
                if errors:
                    raise InvalidReply(errors, str(env.get("result", "")))
                attempts.append({"attempt": n, "ok": True, "seconds": round(time.time() - t0, 1)})
                log(f"    claude {task}: valid reply on attempt {n} ({time.time() - t0:.0f}s)")
                return payload, {"writer": self.identity(), "task": task, "attempts": attempts,
                                 "duration_ms": env.get("duration_ms"), "cost_usd": env.get("total_cost_usd")}
            except ClaudeUnavailable:
                raise
            except InvalidReply as exc:
                last = f"invalid reply: {exc}"
                current = prompt + repair_note(exc)
            except ClaudeError as exc:
                last = str(exc)
                current = prompt
            attempts.append({"attempt": n, "ok": False, "error": last[:300], "seconds": round(time.time() - t0, 1)})
            log(f"    claude {task}: attempt {n} failed: {last[:200]}")
            if n <= self.retries:
                time.sleep(min(2.0 * n, 10.0))
        raise ClaudeError(f"{task}: no valid reply after {len(attempts)} attempts; last error: {last}")


def repair_note(exc: InvalidReply) -> str:
    listed = "\n".join(f"- {e}" for e in exc.errors[:25])
    prev = exc.raw.strip()
    if len(prev) > 24000:
        prev = prev[:24000] + "\n…(truncated)"
    return ("\n\n## Your previous reply was rejected\nFix every problem below and return the complete corrected "
            f"JSON document only.\n{listed}\n\nPrevious reply:\n{prev}\n")
