from __future__ import annotations

from pathlib import Path

from ..util import file_fingerprint


def dir_fingerprint(path: Path, patterns=("*",)) -> dict:
    if not path.exists():
        return {}
    out = {}
    files = {f for pat in patterns for f in path.rglob(pat) if f.is_file()}
    for f in sorted(files):
        out[str(f.relative_to(path))] = file_fingerprint(f)
    return out


def optional_file(path: Path | None) -> str | None:
    return file_fingerprint(path) if path and path.exists() else None


def plan_engine(ctx) -> dict | None:
    """The visual plan to render, or None when the legacy shot templates should draw this topic
    (a topic pack with shots.yaml, a fallback plan in `auto` mode, or render.engine=templates)."""
    from ..util import read_json
    engine = ctx.cfg["render"].get("engine", "auto")
    if engine == "templates":
        return None
    path = ctx.common / "plan.json"
    plan = read_json(path) if path.exists() else {}
    if plan.get("legacy_shots") or not plan.get("scenes"):
        if engine == "plan":
            raise SystemExit("render.engine=plan but there is no visual plan for this topic; run the plan stage")
        return None
    if engine == "auto":
        meta = ctx.common / "plan.meta.json"
        if meta.exists() and read_json(meta).get("fallback"):
            return None
    return plan
