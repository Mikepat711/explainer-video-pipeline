"""Producer briefs for the Claude writer: required topics the lesson must cover, plus free-form notes.

Read from `topics/<slug>/brief.md` (automatically), `--brief FILE` and `--require "id: description"`:

    ---
    config:                      # optional config overrides for this topic
      length: {target_seconds: 240}
    ---
    # Brief: how the electrical grid works
    ## Required topics
    - wind: how a wind turbine turns moving air into power
    ## Notes
    Anything else here is passed to the writer as notes (HTML comments and the title are not).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import deep_merge

ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_REQ_HEADING = re.compile(r"^#{1,6}\s*required topics?\s*:?\s*$", re.I)
_HEADING = re.compile(r"^#{1,6}\s")
_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_COMMENT = re.compile(r"<!--.*?-->", re.S)


@dataclass
class Brief:
    require: list[dict] = field(default_factory=list)
    notes: str = ""
    config: dict = field(default_factory=dict)
    origins: list[str] = field(default_factory=list)

    @property
    def ids(self) -> list[str]:
        return [r["id"] for r in self.require]

    def inputs(self) -> dict:
        return {"require": self.require, "notes": self.notes}

    def __bool__(self) -> bool:
        return bool(self.require or self.notes)


def parse_requirement(spec: str, origin: str) -> dict:
    rid, sep, text = spec.partition(":")
    rid, text = rid.strip(), text.strip()
    if not sep or not ID.match(rid) or not text:
        raise SystemExit(f"{origin}: required topic {spec.strip()!r} must look like 'id: what the lesson must "
                         "cover' with a lower-case id (letters, digits, dashes), e.g. 'wind: how a wind turbine works'")
    return {"id": rid, "text": text}


def parse_brief(text: str, origin: str = "brief") -> Brief:
    config: dict = {}
    if text.startswith("---\n"):
        head, sep, rest = text[4:].partition("\n---")
        if sep:
            meta = yaml.safe_load(head) or {}
            if not isinstance(meta, dict) or not isinstance(meta.get("config", {}), dict):
                raise SystemExit(f"{origin}: the front matter may only hold a `config:` mapping")
            config, text = meta.get("config") or {}, rest.partition("\n")[2]
    text = _COMMENT.sub("", text)
    require, notes, in_req, current = [], [], False, None
    for line in text.splitlines():
        if _HEADING.match(line):
            in_req, current = bool(_REQ_HEADING.match(line)), None
            if not in_req and not line.startswith("# "):
                notes.append(line)
            continue
        if in_req:
            m = _BULLET.match(line)
            if m:
                current = parse_requirement(m.group(1), origin)
                require.append(current)
                continue
            if current and line.strip() and line[:1].isspace():
                current["text"] += " " + line.strip()
                continue
            current = None
        notes.append(line)
    return Brief(require, "\n".join(notes).strip(), config, [origin])


def merge(briefs: list[Brief]) -> Brief:
    """Later briefs replace a required topic with the same id and add their notes and config."""
    out = Brief()
    for b in briefs:
        by_id = {r["id"]: i for i, r in enumerate(out.require)}
        for r in b.require:
            if r["id"] in by_id:
                out.require[by_id[r["id"]]] = r
            else:
                by_id[r["id"]] = len(out.require)
                out.require.append(r)
        out.notes = "\n\n".join(x for x in (out.notes, b.notes) if x)
        out.config = deep_merge(out.config, b.config)
        out.origins += b.origins
    return out


def load_brief(topic_dir: Path, files: list[str] | None = None, requires: list[str] | None = None) -> Brief:
    briefs = []
    pinned = topic_dir / "brief.md"
    if pinned.exists():
        briefs.append(parse_brief(pinned.read_text(), f"topics/{topic_dir.name}/brief.md"))
    for f in files or []:
        p = Path(f)
        if not p.exists():
            raise SystemExit(f"--brief {f}: no such file")
        briefs.append(parse_brief(p.read_text(), f))
    if requires:
        briefs.append(Brief([parse_requirement(r, "--require") for r in requires], origins=["--require"]))
    return merge(briefs)
