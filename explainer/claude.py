"""Coding-agent CLIs as the writer: Claude Code (default) or Grok Build (`llm.writer: grok`).

Claude runs `claude -p <prompt> --model <alias> --output-format json` headlessly (stdin closed,
empty working directory) and parses the envelope:

    {"type": "result", "subtype": "success", "is_error": false, "duration_ms": 3120, "result": "<text>"}

Grok runs `grok -p <prompt> -m <model> --permission-mode auto --output-format json` the same way;
its envelope is {"text": "<text>", "stopReason": "end_turn", "total_cost_usd": ...} or
{"type": "error", "message": "..."}. Both engines get the identical prompt.

`result` must hold one JSON document (code fences tolerated) that passes the task's schema
and semantic checks; otherwise the call is retried with the errors appended to the prompt.
Sign-in is each CLI's own; no API keys are read or stored here.
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

AUTH_HINTS = ("/login", "not logged in", "authenticat", "invalid api key", "oauth", "credit balance",
              "grok login", "sign in")


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


OFF = ("offline", "off", "none", "false")


class ClaudeWriter:
    name = "claude"

    def __init__(self, cfg: dict):
        c = cfg["llm"]
        if str(c.get("writer", "claude")).lower() in OFF:
            raise ClaudeUnavailable("disabled by config (llm.writer / EXPLAINER_WRITER)")
        self.timeout = float(c.get("timeout", 900))
        self.retries = int(c.get("retries", 2))
        self.web = bool(c.get("web_research", True))
        self.setup(c, cfg)

    def setup(self, c: dict, cfg: dict) -> None:
        self.bin = resolve_bin(cfg)
        if not self.bin:
            raise ClaudeUnavailable("Claude Code CLI not found: put `claude` on PATH or set EXPLAINER_CLAUDE_BIN "
                                    "in ~/.config/explainer/config")
        self.model = str(c.get("model") or "opus")
        self.extra = [str(a) for a in c.get("extra_args") or []]

    def identity(self) -> str:
        return f"{self.name}:{self.model}"

    def command(self, prompt: str, web: bool) -> list[str]:
        cmd = [self.bin, "-p", prompt, "--model", self.model, "--output-format", "json",
               "--disallowedTools", "Bash,Edit,Write,NotebookEdit"]
        if web:
            cmd += ["--allowedTools", "WebSearch,WebFetch"]
        return cmd + self.extra

    def call(self, prompt: str, web: bool = False) -> dict:
        t0 = time.time()
        with tempfile.TemporaryDirectory(prefix=f"explainer-{self.name}-") as td:
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
        return self.parse(out, err, proc.returncode, time.time() - t0)

    def parse(self, out: str, err: str, returncode: int, seconds: float) -> dict:
        """The CLI's output as a Claude-style envelope with the reply text under `result`."""
        if not out.strip():
            msg = (err or "").strip().splitlines()[-1:] or ["no output"]
            if any(h in (err or "").lower() for h in AUTH_HINTS):
                raise ClaudeUnavailable(f"Claude Code is not signed in: {msg[0]}")
            raise ClaudeError(f"exit code {returncode}: {msg[0]}")
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
        attempts, current, last, spent = [], prompt, "no attempt", None
        for n in range(1, self.retries + 2):
            t0 = time.time()
            try:
                env = self.call(current, web=web and self.web)
                if env.get("total_cost_usd") is not None:
                    spent = (spent or 0.0) + float(env["total_cost_usd"])
                payload = extract_json(str(env.get("result", "")))
                errors = validate(payload, schema)
                if not errors and check:
                    errors = check(payload)
                if errors:
                    raise InvalidReply(errors, str(env.get("result", "")))
                attempts.append({"attempt": n, "ok": True, "seconds": round(time.time() - t0, 1)})
                log(f"    {self.name} {task}: valid reply on attempt {n} ({time.time() - t0:.0f}s)")
                return payload, {"writer": self.identity(), "task": task, "attempts": attempts,
                                 "duration_ms": env.get("duration_ms"),
                                 "cost_usd": round(spent, 4) if spent is not None else None}
            except ClaudeUnavailable:
                raise
            except InvalidReply as exc:
                last = f"invalid reply: {exc}"
                current = prompt + repair_note(exc)
            except ClaudeError as exc:
                last = str(exc)
                current = prompt
            attempts.append({"attempt": n, "ok": False, "error": last[:300], "seconds": round(time.time() - t0, 1)})
            log(f"    {self.name} {task}: attempt {n} failed: {last[:200]}")
            if n <= self.retries:
                time.sleep(min(2.0 * n, 10.0))
        err = ClaudeError(f"{task}: no valid reply after {len(attempts)} attempts; last error: {last}")
        err.cost_usd, err.attempts = spent, attempts  # what the failed attempts still cost
        raise err


def resolve_grok_bin(cfg: dict) -> str | None:
    explicit = cfg["llm"].get("grok_bin")
    candidates = [Path(explicit).expanduser()] if explicit else \
        [Path(p) for p in (shutil.which("grok"),) if p] + [Path.home() / ".grok" / "bin" / "grok"]
    return next((str(p) for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)


class GrokWriter(ClaudeWriter):
    """Grok Build CLI (`grok -p`), headless with the same prompts, schemas and retries as Claude.

    Only reading and (for research) web tools are left on: shell, file edits, subagents, MCP
    connectors and media generation are switched off, and the call runs in an empty temp folder.
    """
    name = "grok"
    OFF_TOOLS = ("run_terminal_command,search_replace,write,spawn_subagent,kill_command_or_subagent,"
                 "get_command_or_subagent_output,scheduler_create,scheduler_delete,scheduler_list,monitor,workflow,"
                 "image_gen,image_edit,image_to_video,reference_to_video,search_tool,use_tool,ask_user_question,"
                 "send_feedback")
    # Appended to Grok's system prompt (the task prompt itself stays identical to Claude's). Without it Grok
    # Build tends to write its JSON to a file and validate it with a shell script, which is denied here and
    # cost a 900 s timeout in testing.
    RULES = ("You are running headless as a writer inside a video pipeline. Return the requested document as your "
             "final reply text. Do not run shell commands, create or edit files, or write validation scripts; the "
             "pipeline validates the reply itself. Use web tools only when the task asks for research.")
    WEB_TOOLS = "web_search,web_fetch,open_page,open_page_with_find,x_user_search,x_semantic_search," \
                "x_keyword_search,x_thread_fetch"

    def setup(self, c: dict, cfg: dict) -> None:
        self.bin = resolve_grok_bin(cfg)
        if not self.bin:
            raise ClaudeUnavailable("Grok Build CLI not found: install it (~/.grok/bin/grok) or set EXPLAINER_GROK_BIN "
                                    "in ~/.config/explainer/config")
        self.model = str(c.get("grok_model") or "grok-4.7")
        self.extra = [str(a) for a in c.get("grok_extra_args") or []]
        self.effort = str(c.get("grok_effort") or "")  # --reasoning-effort (low | medium | high); "" = Grok's default
        if c.get("grok_timeout"):
            self.timeout = float(c["grok_timeout"])  # Grok reasons long: a plan took ~30 min in testing
        if c.get("grok_retries") is not None:
            self.retries = int(c["grok_retries"])

    def identity(self) -> str:
        return f"grok:{self.model}" + (f"@{self.effort}" if self.effort else "")

    def command(self, prompt: str, web: bool) -> list[str]:
        off = self.OFF_TOOLS if web else f"{self.OFF_TOOLS},{self.WEB_TOOLS}"
        cmd = [self.bin, "-p", prompt, "-m", self.model, "--permission-mode", "auto", "--output-format", "json",
               "--no-subagents", "--disallowed-tools", off, "--deny", "Bash", "--deny", "Edit", "--deny", "Write",
               "--rules", self.RULES]
        if not web:
            cmd.append("--disable-web-search")
        if self.effort:
            cmd += ["--reasoning-effort", self.effort]
        return cmd + self.extra

    def parse(self, out: str, err: str, returncode: int, seconds: float) -> dict:
        text = out.strip()
        if not text:
            msg = (err or "").strip().splitlines()[-1:] or ["no output"]
            if any(h in (err or "").lower() for h in AUTH_HINTS):
                raise ClaudeUnavailable(f"Grok Build is not signed in: {msg[0]}")
            raise ClaudeError(f"exit code {returncode}: {msg[0]}")
        env = None
        for chunk in [text] + list(reversed(text.splitlines())):
            try:
                env = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(env, dict):
                break
            env = None
        if env is None:
            raise ClaudeError(f"unreadable CLI output: {text[:300]!r}")
        if env.get("type") == "error" or "text" not in env:
            msg = str(env.get("message") or env.get("error") or env)[:300]
            if any(h in msg.lower() for h in AUTH_HINTS):
                raise ClaudeUnavailable(f"Grok Build is not signed in: {msg}")
            raise ClaudeError(f"grok error (exit {returncode}): {msg}")
        if env.get("stopReason") not in (None, "end_turn", "stop"):
            log(f"    grok: reply ended with stopReason={env.get('stopReason')}")
        return {"result": env.get("text") or "", "duration_ms": round(seconds * 1000),
                "total_cost_usd": env.get("total_cost_usd"), "session_id": env.get("sessionId")}


WRITERS = {"claude": ClaudeWriter, "grok": GrokWriter}


def make_writer(cfg: dict) -> ClaudeWriter:
    """The writer named by llm.writer (claude | grok | off). Raises ClaudeUnavailable when it cannot run."""
    name = str(cfg["llm"].get("writer") or "claude").lower()
    if name in OFF:
        raise ClaudeUnavailable("disabled by config (llm.writer / EXPLAINER_WRITER)")
    if name not in WRITERS:
        raise SystemExit(f"unknown writer {name!r}: use one of {', '.join(WRITERS)} or off")
    return WRITERS[name](cfg)


def repair_note(exc: InvalidReply) -> str:
    listed = "\n".join(f"- {e}" for e in exc.errors[:25])
    prev = exc.raw.strip()
    if len(prev) > 24000:
        prev = prev[:24000] + "\n…(truncated)"
    return ("\n\n## Your previous reply was rejected\nFix every problem below and return the complete corrected "
            f"JSON document only.\n{listed}\n\nPrevious reply:\n{prev}\n")
