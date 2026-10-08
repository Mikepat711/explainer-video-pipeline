"""Load a validated bundle and make shared draw helpers importable as lib/art/art_pro."""
from __future__ import annotations

import importlib.util
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from .schema import BundleManifest, ValidationError, validate_bundle

BUNDLES_DIR_DEFAULT = "~/explainer-bundles"


@dataclass
class Scene:
    id: str
    title: str
    index: int
    sentences: list[tuple[str, str | None]]  # (caption, tts or None)

    @property
    def captions(self) -> list[str]:
        return [c for c, _ in self.sentences]

    @property
    def spoken(self) -> list[str]:
        return [t or c for c, t in self.sentences]


@dataclass
class LoadedBundle:
    root: Path
    manifest: BundleManifest
    scenes: list[Scene]
    script_mod: ModuleType
    scenes_mod: ModuleType
    modules: dict[str, ModuleType] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return self.manifest.slug

    @property
    def title(self) -> str:
        return self.manifest.title

    @property
    def scene_funcs(self) -> dict:
        return dict(self.scenes_mod.SCENE_FUNCS)

    def sfx_events(self, timing: dict, words=None):
        fn = getattr(self.scenes_mod, "sfx_events", None)
        if not fn:
            return []
        try:
            return list(fn(timing, words))
        except TypeError:
            return list(fn(timing))


def _inject_draw_aliases() -> None:
    import explainer.draw.art as art
    import explainer.draw.art_pro as art_pro
    import explainer.draw.lib as lib
    sys.modules.setdefault("lib", lib)
    sys.modules.setdefault("art", art)
    sys.modules.setdefault("art_pro", art_pro)


def _load_py(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValidationError([f"cannot load {path.name}"])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_bundle(root: Path) -> LoadedBundle:
    """Validate, inject shared helpers, import project modules. Requires skia for scenes."""
    root = Path(root).resolve()
    man = validate_bundle(root)
    _inject_draw_aliases()
    # Project modules share a namespace so `from art_gas import *` works.
    sys.path.insert(0, str(root))
    try:
        extras = {}
        for rel in man.modules:
            extras[Path(rel).stem] = _load_py(root / rel, Path(rel).stem)
        script_mod = _load_py(root / man.script, "bundle_script")
        scenes_mod = _load_py(root / man.scenes, "bundle_scenes")
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass
    raw = getattr(script_mod, "SCENES", None)
    if not raw:
        raise ValidationError(["script module has no SCENES"])
    if not getattr(scenes_mod, "SCENE_FUNCS", None):
        raise ValidationError(["scenes module has no SCENE_FUNCS"])
    scenes = []
    for i, row in enumerate(raw):
        sid, title, sents = row[0], row[1], row[2]
        pairs = [(str(c), None if t is None else str(t)) for c, t in sents]
        scenes.append(Scene(id=str(sid), title=str(title), index=i, sentences=pairs))
    missing = [s.id for s in scenes if s.id not in scenes_mod.SCENE_FUNCS]
    if missing:
        raise ValidationError([f"SCENE_FUNCS missing draw functions for: {', '.join(missing)}"])
    return LoadedBundle(root=root, manifest=man, scenes=scenes, script_mod=script_mod,
                        scenes_mod=scenes_mod, modules=extras)


def _extract_archive(archive: Path) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="explainer-bundle-"))
    with tarfile.open(archive, "r:*") as tf:
        tf.extractall(tmp, filter="data")
    # a tarball may wrap a single top-level directory
    kids = [p for p in tmp.iterdir() if p.name not in (".", "..") and not p.name.startswith("._")]
    if len(kids) == 1 and kids[0].is_dir() and (kids[0] / "manifest.yaml").is_file():
        return kids[0]
    if (tmp / "manifest.yaml").is_file():
        return tmp
    nested = list(tmp.rglob("manifest.yaml"))
    if len(nested) == 1:
        return nested[0].parent
    raise ValidationError([f"{archive.name}: no manifest.yaml in archive"])


def resolve_bundle(spec: str, extra_roots: list[Path] | None = None) -> Path:
    """Find a bundle directory from a path, tarball, slug, or landing-folder name."""
    p = Path(spec).expanduser()
    if p.is_file() and p.suffix in {".tgz", ".tar", ".gz"} or spec.endswith(".tar.gz"):
        if p.is_file():
            return _extract_archive(p)
    if p.is_dir() and (p / "manifest.yaml").is_file():
        return p.resolve()
    name = p.name if p.suffix in {".tgz", ".tar"} else spec.rstrip("/")
    name = Path(name).stem.replace(".tar", "")
    roots = list(extra_roots or [])
    from ..util import REPO_ROOT
    roots += [
        Path(BUNDLES_DIR_DEFAULT).expanduser(),
        REPO_ROOT / "examples",
        Path.cwd(),
        Path.cwd() / "examples",
    ]
    for root in roots:
        cand = root / name
        if cand.is_dir() and (cand / "manifest.yaml").is_file():
            return cand.resolve()
    raise ValidationError([
        f"cannot find a bundle at {spec!r}. Pass a directory with manifest.yaml, a .tgz, "
        f"or a slug under {BUNDLES_DIR_DEFAULT}/ or examples/."
    ])
