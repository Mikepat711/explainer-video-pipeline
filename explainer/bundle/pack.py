"""Tar a project bundle so it can be copied to another machine (code only, no media)."""
from __future__ import annotations

import tarfile
from pathlib import Path

from .schema import validate_bundle

SKIP_NAMES = {".git", "__pycache__", ".DS_Store", ".venv", "clips", "audio", "qa", "out", "build"}
SKIP_SUFFIXES = {".mp4", ".wav", ".png", ".jpg", ".jpeg", ".pyc", ".mov"}


def _keep(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in SKIP_NAMES or part.startswith("._") for part in rel.parts):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return True


def pack_bundle(src: Path, dest: Path | None = None) -> Path:
    """Validate `src` and write `<slug>.tgz` next to it (or to `dest`)."""
    src = Path(src).resolve()
    man = validate_bundle(src)
    dest = Path(dest).expanduser() if dest else src.parent / f"{man.slug}.tgz"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as tf:
        for path in sorted(src.rglob("*")):
            if path.is_file() and _keep(path, src):
                tf.add(path, arcname=str(Path(man.slug) / path.relative_to(src)))
    return dest
