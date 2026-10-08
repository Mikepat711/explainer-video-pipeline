"""Stand-in for the Claude Code CLI (`claude -p <prompt> ... --output-format json`) and, when called
with `--permission-mode` (as the Grok writer does), for the Grok Build CLI and its envelope.

Replies with the fixture for the prompt's `TASK:` line, wrapped in the CLI's JSON envelope.
Behaviour is set by environment variables:

    FAKE_CLAUDE_MODE   ok | fenced | error-once | error-always | invalid-once | timeout | auth | auth-stderr
    FAKE_CLAUDE_TASKS  comma list of tasks the mode applies to (default: all; others reply ok)
    FAKE_CLAUDE_STATE  directory for per-task call counters and the call log (calls.jsonl)
    FAKE_CLAUDE_FIXTURES  directory with <task>.json replies (default: tests/fixtures/claude)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

FIXTURES = Path(os.environ.get("FAKE_CLAUDE_FIXTURES") or Path(__file__).resolve().parent / "fixtures" / "claude")


GROK = "--permission-mode" in sys.argv


def envelope(result: str, is_error: bool = False, subtype: str = "success") -> str:
    if GROK:
        if is_error:
            return json.dumps({"type": "error", "message": result})
        return json.dumps({"text": result, "stopReason": "end_turn", "sessionId": "fake", "total_cost_usd": 0.02},
                          indent=2)
    return json.dumps({"type": "result", "subtype": subtype, "is_error": is_error, "duration_ms": 1234,
                       "num_turns": 1, "result": result, "session_id": "fake", "total_cost_usd": 0.01})


def invalid(task: str) -> dict:
    doc = json.loads((FIXTURES / f"{task}.json").read_text())
    if task == "research":
        doc.pop("key_concepts")
    elif task == "script":
        doc["scenes"][0]["sentences"][0] = "Two sentences here. Not allowed."
    else:
        doc["scenes"][0]["beats"][0]["target"] = "ghost"
    return doc


def main() -> int:
    args = sys.argv[1:]
    prompt = args[args.index("-p") + 1] if "-p" in args else ""
    task = prompt.split("\n", 1)[0].removeprefix("TASK:").strip() or "unknown"
    state = Path(os.environ.get("FAKE_CLAUDE_STATE", "."))
    state.mkdir(parents=True, exist_ok=True)
    counter = state / f"{task}.count"
    n = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(n))
    stdin_closed = sys.stdin is None or sys.stdin.read() == ""
    with open(state / "calls.jsonl", "a") as log:
        log.write(json.dumps({"task": task, "n": n, "argv": args, "stdin_empty": stdin_closed, "cwd": os.getcwd(),
                              "repair": "previous reply was rejected" in prompt}) + "\n")

    tasks = [t for t in os.environ.get("FAKE_CLAUDE_TASKS", "").split(",") if t]
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok") if not tasks or task in tasks else "ok"
    fixture = FIXTURES / f"{task}.json"
    good = fixture.read_text() if fixture.exists() else "{}"
    if task == "layout":  # echo the scene back, optionally spread apart (FAKE_LAYOUT_SPREAD) or renamed
        scene = json.loads(prompt.split("Scene JSON:\n", 1)[1].split("\n", 1)[0])
        if os.environ.get("FAKE_LAYOUT_SPREAD"):
            for i, a in enumerate(scene.get("actors", [])):
                a.update(at=[300 + 450 * i, 200 + 150 * i], scale=0.6)
        if os.environ.get("FAKE_LAYOUT_RENAME"):
            scene["actors"][0]["id"] += "_renamed"
        good = json.dumps({"scene": scene, "changes": ["fake change"]})

    if mode == "timeout":
        time.sleep(60)
    elif mode == "auth":
        print(envelope("Invalid API key · Please run /login", is_error=True))
    elif mode == "auth-stderr":
        print("Error: not logged in. Please run /login", file=sys.stderr)
        return 1
    elif mode == "error-always" or (mode == "error-once" and n == 1):
        print(envelope("API Error: 529 overloaded", is_error=True, subtype="error_during_execution"))
    elif mode == "invalid-once" and n == 1:
        print(envelope("Here is the document:\n" + json.dumps(invalid(task))))
    elif mode == "fenced":
        print(envelope(f"```json\n{good}\n```"))
    else:
        print(envelope(good))
    return 0


if __name__ == "__main__":
    sys.exit(main())
