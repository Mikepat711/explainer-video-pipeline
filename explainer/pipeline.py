"""Stage runner with content-addressed caching.

Each stage declares its upstream stages, the config sections / files it
depends on, and the outputs it produces. A stage is skipped when its
fingerprint (own source code + declared inputs + upstream result hashes)
matches the stamp written by its last successful run and all outputs exist.
"""
from __future__ import annotations

import inspect
import time
from dataclasses import dataclass, field
from pathlib import Path

from .brief import Brief
from .config import aspect_tag
from .util import REPO_ROOT, file_fingerprint, log, read_json, sha256_bytes, sha256_json, slugify, write_json


@dataclass
class Context:
    topic: str
    cfg: dict
    scenes_filter: list[str] | None = None
    source_urls: list[str] = field(default_factory=list)
    tag: str = ""
    build_root: Path = REPO_ROOT / "build"
    out_root: Path = REPO_ROOT / "out"
    topics_root: Path = REPO_ROOT / "topics"
    brief: Brief = field(default_factory=Brief)
    fresh: bool = False  # ignore the topic pack's pinned research/script/plan and let the writer start over

    @property
    def slug(self) -> str:
        return slugify(self.topic)

    @property
    def topic_dir(self) -> Path:
        return self.topics_root / self.slug

    def pack_file(self, name: str) -> Path | None:
        """A hand-authored or pinned writer output in the topic pack, unless --fresh set it aside."""
        p = self.topic_dir / name
        return p if p.exists() and not self.fresh else None

    @property
    def writer_tag(self) -> str:
        """'' for Claude (the default) and the offline fallback; e.g. 'grok' otherwise, so each writer keeps
        its own research/script/plan and finished video and switching writers never overwrites the other's."""
        w = str((self.cfg.get("llm") or {}).get("writer") or "claude").lower()
        return "" if w in ("claude", "off", "offline", "none", "false") else slugify(w)

    @property
    def grind_tag(self) -> str:
        """e.g. 'grokfix' when a grind writer (llm.grind) fixes the plan's layout, so its video sits apart."""
        from .writer import stage_writer_name
        g = stage_writer_name(self.cfg, "layout")
        return "" if g in ("off", "offline", "none", "false", "") else f"{slugify(g)}fix"

    @property
    def common(self) -> Path:
        return self.build_root / self.slug / ("common" + (f"-{self.writer_tag}" if self.writer_tag else ""))

    @property
    def variant(self) -> str:
        v = aspect_tag(self.cfg)
        if self.tag:
            v += f"-{slugify(self.tag)}"
        if self.writer_tag:
            v += f"-{self.writer_tag}"
        if self.grind_tag:
            v += f"-{self.grind_tag}"
        return v

    @property
    def vdir(self) -> Path:
        return self.build_root / self.slug / self.variant

    @property
    def out_dir(self) -> Path:
        return self.out_root / self.slug / self.variant

    def stamp_path(self, stage: "Stage") -> Path:
        base = self.common if stage.scope == "common" else self.vdir
        return base / ".stamps" / f"{stage.name}.json"

    def dir_for(self, stage: "Stage") -> Path:
        return self.common if stage.scope == "common" else self.vdir


class Stage:
    name = ""
    scope = "variant"  # "common" = aspect-independent, shared by all variants
    deps: tuple[str, ...] = ()
    extra_code: tuple[str, ...] = ()  # module paths (relative to package) that affect output
    owns: tuple[str, ...] = ()  # globs (relative to the stage dir) of files only this stage writes
    description = ""

    def inputs(self, ctx: Context) -> dict:
        return {}

    def outputs(self, ctx: Context) -> list[Path]:
        raise NotImplementedError

    def run(self, ctx: Context) -> None:
        raise NotImplementedError

    def still_fresh(self, ctx: Context) -> bool:
        return True

    def code_hash(self) -> str:
        pkg = Path(__file__).resolve().parent
        blobs = [Path(inspect.getfile(type(self))).read_bytes()]
        for rel in self.extra_code:
            p = pkg / rel
            files = sorted(p.rglob("*.py")) if p.is_dir() else [p]
            blobs += [f.read_bytes() for f in files]
        return sha256_bytes(b"\0".join(blobs))


def _upstream_results(ctx: Context, stage: Stage, registry: dict[str, Stage]) -> dict:
    res = {}
    for dep in stage.deps:
        sp = ctx.stamp_path(registry[dep])
        if not sp.exists():
            raise SystemExit(
                f"stage '{stage.name}' needs '{dep}' output; run `python -m explainer run \"{ctx.topic}\"` "
                f"or `python -m explainer stage {dep} \"{ctx.topic}\"` first")
        res[dep] = read_json(sp)["result_hash"]
    return res


def fingerprint(ctx: Context, stage: Stage, registry: dict[str, Stage]) -> str:
    return sha256_json({
        "code": stage.code_hash(),
        "inputs": stage.inputs(ctx),
        "upstream": _upstream_results(ctx, stage, registry),
    })


def is_fresh(ctx: Context, stage: Stage, registry: dict[str, Stage]) -> bool:
    sp = ctx.stamp_path(stage)
    if not sp.exists():
        return False
    stamp = read_json(sp)
    if stamp.get("fingerprint") != fingerprint(ctx, stage, registry):
        return False
    return all(p.exists() for p in stage.outputs(ctx)) and stage.still_fresh(ctx)


def dependents(stage: Stage, registry: dict[str, Stage]) -> list[Stage]:
    """Stages that read this stage's output, directly or through other stages."""
    found: list[Stage] = []
    frontier = {stage.name}
    while frontier:
        nxt = {s.name for s in registry.values() if s not in found and frontier & set(s.deps)}
        found += [registry[n] for n in sorted(nxt)]
        frontier = nxt
    return found


def clear_stale_dependents(ctx: Context, stage: Stage, registry: dict[str, Stage]) -> None:
    """A shared stage changed its result: delete what its shared dependents produced from the old one, so a
    partial run (e.g. `--until plan`) never leaves an older shot list or voice track next to the new outputs.
    Variant outputs (rendered scenes, finished videos) are left alone; their fingerprints already mark them stale."""
    for dep in dependents(stage, registry):
        if dep.scope != "common":
            continue
        try:
            outs = dep.outputs(ctx)
        except Exception:
            outs = []
        outs += [p for pat in dep.owns for p in ctx.dir_for(dep).glob(pat) if p.is_file()]
        gone = list(dict.fromkeys(p for p in outs if p.exists()))
        for p in gone:
            p.unlink()
        sp = ctx.stamp_path(dep)
        if gone or sp.exists():
            sp.unlink(missing_ok=True)
            log(f"           cleared stale {dep.name} output" + (f": {', '.join(p.name for p in gone)}" if gone else ""))


WRITER_LABELS = {"grok": "Grok", "claude": "Claude", "off": "off", "offline": "offline writer"}


def describe(ctx: Context, stage: Stage) -> str:
    """The stage description, naming the active writer instead of Claude when another one is selected.
    (Kept here, outside the stage modules, so the label never changes a stage's code fingerprint.)"""
    from .writer import stage_writer_name
    w = stage_writer_name(ctx.cfg, stage.name)
    if "(grind writer)" in stage.description:
        return stage.description.replace("grind writer", WRITER_LABELS.get(w, w.capitalize()))
    if w == "claude" or "Claude" not in stage.description:
        return stage.description
    return stage.description.replace("Claude", WRITER_LABELS.get(w, w))


def execute(ctx: Context, stage: Stage, registry: dict[str, Stage], force: bool = False) -> bool:
    """Run one stage if stale (or forced). Returns True if it actually ran."""
    if not force and is_fresh(ctx, stage, registry):
        log(f"  [cached] {stage.name}")
        return False
    sp = ctx.stamp_path(stage)
    previous = read_json(sp).get("result_hash") if sp.exists() else None
    fp = fingerprint(ctx, stage, registry)
    ctx.dir_for(stage).mkdir(parents=True, exist_ok=True)
    log(f"  [run]    {stage.name} — {describe(ctx, stage)}")
    t0 = time.time()
    stage.run(ctx)
    outs = stage.outputs(ctx)
    missing = [p for p in outs if not p.exists()]
    if missing:
        raise RuntimeError(f"stage {stage.name} did not produce: {[p.name for p in missing]}")
    result = sha256_json({p.name: file_fingerprint(p) for p in outs})
    write_json(ctx.stamp_path(stage), {
        "stage": stage.name,
        "fingerprint": fp,
        "result_hash": result,
        "outputs": [str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name for p in outs],
        "seconds": round(time.time() - t0, 2),
    })
    log(f"           done in {time.time() - t0:.1f}s")
    if stage.scope == "common" and result != previous:
        clear_stale_dependents(ctx, stage, registry)
    return True
