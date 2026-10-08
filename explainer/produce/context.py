"""Bundle-build context that plugs into the existing Stage fingerprint cache."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..bundle.load import LoadedBundle
from ..config import aspect_tag
from ..pipeline import Stage
from ..util import REPO_ROOT


@dataclass
class BundleContext:
    topic: str
    cfg: dict
    bundle: LoadedBundle
    scenes_filter: list[str] | None = None
    tag: str = ""
    build_root: Path = REPO_ROOT / "build"
    out_root: Path = REPO_ROOT / "out"
    scale: float = 1.0
    max_seconds: float | None = None
    workers: int | None = None
    asr: str = "auto"  # auto | on | off
    deliver: bool = True
    share_max_mb: float = 25.0
    out_width: int | None = None
    out_height: int | None = None
    extra: dict = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return self.bundle.slug

    @property
    def bundle_dir(self) -> Path:
        return self.bundle.root

    @property
    def common(self) -> Path:
        return self.build_root / self.slug / "bundle"

    @property
    def variant(self) -> str:
        v = aspect_tag(self.cfg)
        if self.tag:
            v += f"-{self.tag}"
        w, h = self.frame_size
        if (w, h) != (self.bundle.manifest.width, self.bundle.manifest.height):
            v += f"-{w}x{h}"
        return v

    @property
    def vdir(self) -> Path:
        return self.build_root / self.slug / self.variant

    @property
    def out_dir(self) -> Path:
        return self.out_root / self.slug / self.variant

    @property
    def frame_size(self) -> tuple[int, int]:
        w = self.out_width or int(round(self.bundle.manifest.width * self.scale))
        h = self.out_height or int(round(self.bundle.manifest.height * self.scale))
        return max(16, w - w % 2), max(16, h - h % 2)

    @property
    def fps(self) -> int:
        return int(self.bundle.manifest.fps or self.cfg["video"]["fps"])

    @property
    def status_path(self) -> Path:
        return self.build_root / self.slug / "status.json"

    @property
    def log_path(self) -> Path:
        return self.build_root / self.slug / "build.log"

    def stamp_path(self, stage: Stage) -> Path:
        base = self.common if stage.scope == "common" else self.vdir
        return base / ".stamps" / f"{stage.name}.json"

    def dir_for(self, stage: Stage) -> Path:
        return self.common if stage.scope == "common" else self.vdir

    def selected_scenes(self):
        scenes = self.bundle.scenes
        if self.scenes_filter:
            allow = set(self.scenes_filter)
            scenes = [s for s in scenes if s.id in allow]
        return scenes
