"""Explainer project-bundle schema (explainer-bundle/v1).

A bundle is a small directory (or a tarball of one) that the authoring side
produces. Media never travels with it — only script data, scene/art code,
optional assets, and a manifest.

Required layout
---------------
    <dir>/
      manifest.yaml          # this schema
      script.py              # SCENES = [(id, title, [(caption, tts_or_None), ...]), ...]
      scenes.py              # SCENE_FUNCS = {id: draw(canvas, t, T)}; optional sfx_events(TM, words=None)
      art_*.py               # optional project-specific art (listed in manifest.modules)
      assets/                # optional extra files (images, etc.)
      script.md              # optional human-readable script (ignored by the builder)

Shared helpers (`lib`, `art`, `art_pro`) live in the pipeline package. Bundle
code may `from lib import *` / `from art import ...` — the loader injects those
aliases. Do not copy the shared helpers into the bundle.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SCHEMA_ID = "explainer-bundle/v1"
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{0,80}$")
ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
VOICES = (
    "kokoro:af_heart",
    "elevenlabs:max",
    "elevenlabs:todd",
)


class ValidationError(ValueError):
    """One or more bundle problems; `.errors` is a list of messages."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("bundle is invalid:\n  - " + "\n  - ".join(self.errors))


@dataclass
class BundleManifest:
    schema: str
    title: str
    slug: str
    voice: str = "kokoro:af_heart"
    output: str = ""
    aspect: str = "16:9"
    fps: int = 30
    width: int = 1920
    height: int = 1080
    script: str = "script.py"
    scenes: str = "scenes.py"
    modules: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)
    timing: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def output_name(self) -> str:
        name = self.output or f"{self.slug}.mp4"
        return name if name.endswith(".mp4") else f"{name}.mp4"

    @property
    def size(self) -> tuple[int, int]:
        return int(self.width), int(self.height)


def _as_str(val, field: str, errors: list[str]) -> str:
    if not isinstance(val, str) or not val.strip():
        errors.append(f"{field} must be a non-empty string")
        return ""
    return val.strip()


def validate_manifest(data: dict) -> BundleManifest:
    """Validate a parsed manifest dict. Raises ValidationError."""
    errors: list[str] = []
    if not isinstance(data, dict):
        raise ValidationError(["manifest must be a mapping"])
    schema = _as_str(data.get("schema"), "schema", errors)
    if schema and schema != SCHEMA_ID:
        errors.append(f"schema must be {SCHEMA_ID!r} (got {schema!r})")
    title = _as_str(data.get("title"), "title", errors)
    slug = _as_str(data.get("slug"), "slug", errors)
    if slug and not SLUG_RE.match(slug):
        errors.append("slug must be kebab-case ([a-z][a-z0-9-]*)")
    voice = data.get("voice") or "kokoro:af_heart"
    if not isinstance(voice, str) or not voice.strip() or "/" in voice:
        errors.append("voice must be an engine name or engine:name (e.g. kokoro:af_heart, elevenlabs:max, silence)")
        voice = "kokoro:af_heart"
    aspect = data.get("aspect") or "16:9"
    if aspect not in ASPECTS:
        errors.append(f"aspect must be one of {sorted(ASPECTS)}")
        aspect = "16:9"
    def_w, def_h = ASPECTS[aspect]
    try:
        fps = int(data.get("fps") or 30)
        if fps < 1 or fps > 120:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("fps must be an integer 1–120")
        fps = 30
    try:
        width = int(data.get("width") or def_w)
        height = int(data.get("height") or def_h)
        if width < 16 or height < 16:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("width/height must be integers ≥ 16")
        width, height = def_w, def_h
    script = data.get("script") or "script.py"
    scenes = data.get("scenes") or "scenes.py"
    if not isinstance(script, str) or not script.endswith(".py"):
        errors.append("script must be a .py filename")
    if not isinstance(scenes, str) or not scenes.endswith(".py"):
        errors.append("scenes must be a .py filename")
    modules = data.get("modules") or []
    assets = data.get("assets") or []
    if not isinstance(modules, list) or not all(isinstance(x, str) for x in modules):
        errors.append("modules must be a list of filenames")
        modules = []
    if not isinstance(assets, list) or not all(isinstance(x, str) for x in assets):
        errors.append("assets must be a list of paths")
        assets = []
    timing = data.get("timing") or {}
    if not isinstance(timing, dict):
        errors.append("timing must be a mapping")
        timing = {}
    output = data.get("output") or ""
    if output and not isinstance(output, str):
        errors.append("output must be a filename")
        output = ""
    if errors:
        raise ValidationError(errors)
    return BundleManifest(
        schema=schema, title=title, slug=slug, voice=voice, output=output or "",
        aspect=aspect, fps=fps, width=width, height=height,
        script=script, scenes=scenes, modules=list(modules), assets=list(assets),
        timing=dict(timing), raw=dict(data),
    )


def _safe_rel(root: Path, rel: str, errors: list[str], field: str) -> Path | None:
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        errors.append(f"{field}: path {rel!r} must be relative and stay inside the bundle")
        return None
    p = (root / rel).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError:
        errors.append(f"{field}: path {rel!r} escapes the bundle")
        return None
    return p


def _check_script_module(path: Path, errors: list[str]) -> list[str]:
    """Return scene ids from SCENES without importing (no skia needed)."""
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as e:
        errors.append(f"{path.name}: syntax error: {e}")
        return []
    scenes = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "SCENES" in names and isinstance(node.value, (ast.List, ast.Tuple)):
                scenes = node.value
                break
    if scenes is None:
        errors.append(f"{path.name}: must assign SCENES = [(id, title, sentences), ...]")
        return []
    ids: list[str] = []
    for i, elt in enumerate(scenes.elts):
        if not (isinstance(elt, (ast.Tuple, ast.List)) and len(elt.elts) >= 3):
            errors.append(f"{path.name}: SCENES[{i}] must be (id, title, [(caption, tts), ...])")
            continue
        sid_n = elt.elts[0]
        if not isinstance(sid_n, ast.Constant) or not isinstance(sid_n.value, str) or not sid_n.value:
            errors.append(f"{path.name}: SCENES[{i}] id must be a non-empty string")
            continue
        sents = elt.elts[2]
        if not isinstance(sents, (ast.List, ast.Tuple)) or not sents.elts:
            errors.append(f"{path.name}: SCENES[{i}] ({sid_n.value}) needs at least one sentence")
            continue
        for j, sent in enumerate(sents.elts):
            if not (isinstance(sent, (ast.Tuple, ast.List)) and len(sent.elts) >= 1):
                errors.append(f"{path.name}: SCENES[{i}] sentence {j} must be (caption, tts_or_None)")
                continue
            cap = sent.elts[0]
            if not isinstance(cap, ast.Constant) or not isinstance(cap.value, str) or not cap.value.strip():
                errors.append(f"{path.name}: SCENES[{i}] sentence {j} caption must be a non-empty string")
        ids.append(sid_n.value)
    if len(ids) != len(set(ids)):
        errors.append(f"{path.name}: duplicate scene ids")
    return ids


def _check_scenes_module(path: Path, scene_ids: list[str], errors: list[str]) -> None:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as e:
        errors.append(f"{path.name}: syntax error: {e}")
        return
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assigns = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assigns.extend(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assigns.append(node.target.id)
    if "SCENE_FUNCS" not in assigns and "SCENE_FUNCS" not in names:
        errors.append(f"{path.name}: must define SCENE_FUNCS")
    for sid in scene_ids:
        # A draw function named after the scene, or a SCENE_FUNCS literal that mentions it.
        if sid not in names:
            errors.append(f"{path.name}: no reference to scene {sid!r} (expected a draw function or SCENE_FUNCS entry)")


def validate_bundle(root: Path) -> BundleManifest:
    """Validate a bundle directory (manifest + files). Does not import scene code."""
    root = Path(root)
    errors: list[str] = []
    if not root.is_dir():
        raise ValidationError([f"{root} is not a directory"])
    man_path = root / "manifest.yaml"
    if not man_path.is_file():
        raise ValidationError(["missing manifest.yaml"])
    try:
        data = yaml.safe_load(man_path.read_text()) or {}
    except yaml.YAMLError as e:
        raise ValidationError([f"manifest.yaml: {e}"]) from e
    try:
        man = validate_manifest(data)
    except ValidationError as e:
        errors.extend(e.errors)
        man = None
    if man is None:
        raise ValidationError(errors)
    script = _safe_rel(root, man.script, errors, "script")
    scenes = _safe_rel(root, man.scenes, errors, "scenes")
    if script and not script.is_file():
        errors.append(f"script file missing: {man.script}")
        script = None
    if scenes and not scenes.is_file():
        errors.append(f"scenes file missing: {man.scenes}")
        scenes = None
    for rel in man.modules:
        p = _safe_rel(root, rel, errors, "modules")
        if p and not p.is_file():
            errors.append(f"module missing: {rel}")
    for rel in man.assets:
        p = _safe_rel(root, rel, errors, "assets")
        if p and not p.exists():
            errors.append(f"asset missing: {rel}")
    ids: list[str] = []
    if script:
        ids = _check_script_module(script, errors)
    if scenes and ids:
        _check_scenes_module(scenes, ids, errors)
    if errors:
        raise ValidationError(errors)
    return man
