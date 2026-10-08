"""Who wrote what: the LLM writer (Claude or Grok), a hand-authored topic pack, or the offline fallback."""
from __future__ import annotations

import sys
from pathlib import Path

from .claude import ClaudeUnavailable, ClaudeWriter, make_writer
from .util import read_json, write_json

WRITER_STAGES = ("research", "script", "plan")
GRIND_STAGES = ("layout",)  # mechanical follow-up work on the writer's output (llm.grind, default off)


def stage_writer_name(cfg: dict | None, stage: str | None = None) -> str:
    """Who does `stage`: llm.stage_writers.<stage>, else llm.grind for grind stages, else llm.writer."""
    llm = (cfg or {}).get("llm") or {}
    per = llm.get("stage_writers") or {}
    if stage and per.get(stage):
        return str(per[stage]).lower()
    if stage in GRIND_STAGES:
        return str(llm.get("grind") or "off").lower()
    return str(llm.get("writer") or "claude").lower()


def stage_cfg(cfg: dict, stage: str | None) -> dict:
    """cfg with llm.writer set to the stage's writer; grind stages also get the grind_* call settings."""
    if not stage:
        return cfg
    llm = dict(cfg["llm"], writer=stage_writer_name(cfg, stage))
    if stage in GRIND_STAGES:
        for k in ("timeout", "retries"):
            if llm.get(f"grind_{k}") is not None:
                llm[k] = llm[f"grind_{k}"]
                llm.pop(f"grok_{k}", None)
        if llm.get("grind_effort"):
            llm["grok_effort"] = llm["grind_effort"]
    return dict(cfg, llm=llm)


def get_writer(cfg: dict, stage: str | None = None) -> tuple[ClaudeWriter | None, str]:
    try:
        return make_writer(stage_cfg(cfg, stage)), ""
    except ClaudeUnavailable as exc:
        return None, str(exc)


def writer_identity(cfg: dict, stage: str | None = None) -> str:
    w, _ = get_writer(cfg, stage)
    return w.identity() if w else "offline"


def writer_name(cfg: dict | None, stage: str | None = None) -> str:
    return stage_writer_name(cfg, stage)


def banner(stage: str, reason: str, writer: str = "claude") -> None:
    lines = [
        f"CLAUDE WRITER UNAVAILABLE: '{stage}' IS USING THE LAST-RESORT FALLBACK" if writer == "claude" else
        f"{writer.upper()} WRITER UNAVAILABLE: '{stage}' IS USING THE LAST-RESORT FALLBACK",
        f"reason: {reason}",
        "The research/script/plan will be extractive (Wikipedia or local sources) and weak.",
        f"Fix the {'Grok Build' if writer == 'grok' else 'Claude Code'} CLI (see README > Script writer), then re-run: "
        "the pipeline retries automatically.",
    ]
    width = min(110, max(len(x) for x in lines) + 6)
    bar = "!" * width
    out = [bar] + [f"!! {x.ljust(width - 6)} !!" for x in lines] + [bar]
    print("\n" + "\n".join(out) + "\n", file=sys.stderr, flush=True)


def require_claude(ctx, stage: str, reason: str) -> None:
    """--fresh and briefs with required topics ask for Claude's writing; the offline fallback honours neither."""
    why = "--fresh" if ctx.fresh else "the brief has required topics" if ctx.brief.require else ""
    if why:
        name = writer_name(ctx.cfg, stage)
        raise SystemExit(f"{stage} needs the {name.capitalize()} writer ({why}), and it failed: {reason}\nFix the "
                         f"{'Grok Build' if name == 'grok' else 'Claude Code'} CLI (README > Script writer) and re-run; "
                         "finished stages stay cached.")


def meta_path(common: Path, stage: str) -> Path:
    return common / f"{stage}.meta.json"


def write_meta(common: Path, stage: str, writer: str, fallback: bool = False, reason: str = "", **extra) -> None:
    write_json(meta_path(common, stage), {"stage": stage, "writer": writer, "fallback": fallback,
                                          "reason": reason, **extra})


def read_metas(common: Path) -> list[dict]:
    return [read_json(meta_path(common, s)) for s in WRITER_STAGES + GRIND_STAGES if meta_path(common, s).exists()]


def fallback_is_stale(common: Path, stage: str, cfg: dict) -> bool:
    """A fallback written while Claude was present (e.g. after repeated failures) is retried next run."""
    p = meta_path(common, stage)
    if not p.exists():
        return False
    return bool(read_json(p).get("fallback")) and writer_identity(cfg, stage) != "offline"
