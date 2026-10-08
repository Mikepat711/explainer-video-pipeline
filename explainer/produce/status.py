"""Machine-readable build status for the assistant to poll."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from ..pipeline import is_fresh
from ..util import write_json


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_status(slug: str, stages: list[str]) -> dict:
    return {
        "slug": slug,
        "state": "pending",
        "pid": os.getpid(),
        "started": None,
        "finished": None,
        "error": None,
        "stages": {n: {"state": "pending"} for n in stages},
        "outputs": {},
    }


def read_status(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def write_status(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, data)


def mark(path: Path, **patch) -> dict:
    data = read_status(path) or empty_status(patch.get("slug") or "?", [])
    data.update(patch)
    write_status(path, data)
    return data


def mark_stage(path: Path, name: str, state: str, **extra) -> dict:
    data = read_status(path) or empty_status("?", [])
    row = dict(data.setdefault("stages", {}).get(name) or {})
    row["state"] = state
    if state == "running":
        row["started"] = _now()
    if state in ("ok", "cached", "error"):
        row["finished"] = _now()
    row.update(extra)
    data["stages"][name] = row
    write_status(path, data)
    return data


def output_paths(ctx) -> dict:
    name = Path(ctx.bundle.manifest.output_name).stem
    out = ctx.out_dir
    deliver = None
    rec = out / "delivered.json"
    if rec.is_file():
        try:
            deliver = json.loads(rec.read_text()).get("dest")
        except json.JSONDecodeError:
            pass
    paths = {
        "mp4": str(out / f"{name}.mp4") if (out / f"{name}.mp4").is_file() else None,
        "share": str(out / f"{name}-share.mp4") if (out / f"{name}-share.mp4").is_file() else None,
        "qa": str(out / "qa.json") if (out / "qa.json").is_file() else None,
        "qa_md": str(out / "qa.md") if (out / "qa.md").is_file() else None,
        "contact_sheet": str(out / "contact_sheet.jpg") if (out / "contact_sheet.jpg").is_file() else None,
        "poster": str(out / "poster.png") if (out / "poster.png").is_file() else None,
        "delivered": deliver,
        "build_dir": str(ctx.vdir),
        "out_dir": str(out),
        "status": str(ctx.status_path),
        "log": str(ctx.log_path),
    }
    return {k: v for k, v in paths.items() if v}


def snapshot(ctx, registry: dict, order: list) -> dict:
    """Fresh status from stamps + outputs (for `explainer status --json`)."""
    stages = {}
    for stg in order:
        try:
            fresh = is_fresh(ctx, stg, registry)
            stages[stg.name] = {"state": "cached" if fresh else "stale"}
        except SystemExit:
            stages[stg.name] = {"state": "missing upstream"}
        except Exception:
            stages[stg.name] = {"state": "unknown"}
        sp = ctx.stamp_path(stg)
        if sp.is_file():
            try:
                stamp = json.loads(sp.read_text())
                stages[stg.name]["seconds"] = stamp.get("seconds")
            except json.JSONDecodeError:
                pass
    existing = read_status(ctx.status_path) or {}
    if existing.get("state") == "running":
        # live file is the source of truth while a build is in progress
        stages = existing.get("stages") or stages
    else:
        for name, row in stages.items():
            if row.get("state") == "cached":
                row["state"] = "ok"
    state = existing.get("state") or ("ok" if all(s.get("state") == "ok" for s in stages.values()) else "stale")
    return {
        "slug": ctx.slug,
        "state": state,
        "pid": existing.get("pid"),
        "started": existing.get("started"),
        "finished": existing.get("finished"),
        "error": existing.get("error"),
        "stages": stages,
        "outputs": output_paths(ctx),
    }
