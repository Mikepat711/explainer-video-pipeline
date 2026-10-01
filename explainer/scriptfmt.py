"""Parse/serialize the narration script markdown format.

    ---
    title: How GPS Works
    subtitle: Turning time into position
    ---

    ## [hook] Clocks in space
    Narration sentences for this scene...
    > director notes (optional, ignored by TTS)
"""
from __future__ import annotations

import re

import yaml

from .util import split_sentences

_HEAD = re.compile(r"^##\s*\[([a-z0-9_-]+)\]\s*(.*)$", re.I)


def parse_script(text: str) -> dict:
    meta = {}
    body = text
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    scenes = []
    cur = None
    for line in body.splitlines():
        m = _HEAD.match(line.strip())
        if m:
            cur = {"id": m.group(1).lower(), "heading": m.group(2).strip(), "lines": [], "notes": []}
            scenes.append(cur)
        elif cur is not None:
            s = line.strip()
            if s.startswith(">"):
                cur["notes"].append(s.lstrip("> ").strip())
            elif s and not s.startswith("#"):
                cur["lines"].append(s)
    for sc in scenes:
        sc["narration"] = " ".join(sc.pop("lines"))
        sc["sentences"] = split_sentences(sc["narration"])
    if not scenes:
        raise ValueError("script has no '## [id] Heading' scenes")
    return {"title": meta.get("title", ""), "subtitle": meta.get("subtitle", ""), "scenes": scenes}


def render_script(title: str, subtitle: str, scenes: list[dict]) -> str:
    out = ["---", yaml.safe_dump({"title": title, "subtitle": subtitle}, sort_keys=False).strip(), "---", ""]
    for sc in scenes:
        out.append(f"## [{sc['id']}] {sc['heading']}")
        out.append(sc["narration"].strip())
        for n in sc.get("notes", []):
            out.append(f"> {n}")
        out.append("")
    return "\n".join(out)


def word_count(script: dict) -> int:
    return sum(len(sc["narration"].split()) for sc in script["scenes"])
