"""Who wrote what: Claude, a hand-authored topic pack, or the last-resort offline fallback."""
from __future__ import annotations

import sys
from pathlib import Path

from .claude import ClaudeUnavailable, ClaudeWriter
from .util import read_json, write_json

WRITER_STAGES = ("research", "script", "plan")


def get_writer(cfg: dict) -> tuple[ClaudeWriter | None, str]:
    try:
        return ClaudeWriter(cfg), ""
    except ClaudeUnavailable as exc:
        return None, str(exc)


def writer_identity(cfg: dict) -> str:
    w, _ = get_writer(cfg)
    return w.identity() if w else "offline"


def banner(stage: str, reason: str) -> None:
    lines = [
        f"CLAUDE WRITER UNAVAILABLE: '{stage}' IS USING THE LAST-RESORT FALLBACK",
        f"reason: {reason}",
        "The research/script/plan will be extractive (Wikipedia or local sources) and weak.",
        "Fix the Claude Code CLI (see README > Script writer), then re-run: the pipeline retries automatically.",
    ]
    width = min(110, max(len(x) for x in lines) + 6)
    bar = "!" * width
    out = [bar] + [f"!! {x.ljust(width - 6)} !!" for x in lines] + [bar]
    print("\n" + "\n".join(out) + "\n", file=sys.stderr, flush=True)


def require_claude(ctx, stage: str, reason: str) -> None:
    """--fresh and briefs with required topics ask for Claude's writing; the offline fallback honours neither."""
    why = "--fresh" if ctx.fresh else "the brief has required topics" if ctx.brief.require else ""
    if why:
        raise SystemExit(f"{stage} needs the Claude writer ({why}), and it failed: {reason}\nFix the Claude Code CLI "
                         "(README > Script writer) and re-run; finished stages stay cached.")


def meta_path(common: Path, stage: str) -> Path:
    return common / f"{stage}.meta.json"


def write_meta(common: Path, stage: str, writer: str, fallback: bool = False, reason: str = "", **extra) -> None:
    write_json(meta_path(common, stage), {"stage": stage, "writer": writer, "fallback": fallback,
                                          "reason": reason, **extra})


def read_metas(common: Path) -> list[dict]:
    return [read_json(meta_path(common, s)) for s in WRITER_STAGES if meta_path(common, s).exists()]


def fallback_is_stale(common: Path, stage: str, cfg: dict) -> bool:
    """A fallback written while Claude was present (e.g. after repeated failures) is retried next run."""
    p = meta_path(common, stage)
    if not p.exists():
        return False
    return bool(read_json(p).get("fallback")) and writer_identity(cfg) != "offline"
