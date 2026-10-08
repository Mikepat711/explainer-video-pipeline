"""Run the bundle production stages with the existing fingerprint cache."""
from __future__ import annotations

import time
from pathlib import Path

from ..bundle.load import LoadedBundle, load_bundle, resolve_bundle
from ..bundle.schema import validate_bundle
from ..config import load_config
from ..pipeline import execute
from ..util import log
from .assemble import Assemble, Deliver, Share
from .context import BundleContext
from .music import Music
from .qa import QA
from .render import Render, render_still, XF
from .status import empty_status, mark, mark_stage, output_paths, write_status
from .voice import Voice, bundle_voice_spec

PRODUCE_ORDER = [Voice(), Render(), Music(), Assemble(), Share(), QA(), Deliver()]
PRODUCE_REGISTRY = {s.name: s for s in PRODUCE_ORDER}


def make_context(bundle_spec: str, cfg: dict | None = None, **kwargs) -> BundleContext:
    root = resolve_bundle(bundle_spec)
    validate_bundle(root)
    loaded = load_bundle(root)
    cfg = cfg if cfg is not None else load_config()
    # Bundle path defaults the narrator when the LLM-path config leaves voice.use empty.
    if not str((cfg.get("voice") or {}).get("use") or "").strip():
        cfg = dict(cfg, voice=dict(cfg.get("voice") or {}, use=loaded.manifest.voice or "kokoro:af_heart"))
    cfg = dict(cfg)
    cfg["video"] = dict(cfg.get("video") or {}, aspect=loaded.manifest.aspect)
    return BundleContext(topic=loaded.title, cfg=cfg, bundle=loaded, **kwargs)


def still_frame(ctx: BundleContext, sid: str, t: float, dest: Path | None = None) -> Path:
    from ..util import read_json
    timing = read_json(ctx.common / "voice" / "timing.json")
    words_p = ctx.common / "voice" / "words.json"
    words = read_json(words_p) if words_p.exists() else {}
    ids = [s.id for s in ctx.bundle.scenes]
    if sid not in ids:
        raise SystemExit(f"unknown scene {sid!r}; choose from {ids}")
    idx = ids.index(sid)
    prev = ids[idx - 1] if idx and t < XF else None
    dest = dest or ctx.vdir / "stills" / f"{sid}_{t:05.2f}.png"
    return render_still(sid, t, ctx.bundle.scene_funcs, timing, words, dest, ctx.fps, prev)


def build(ctx: BundleContext, force: bool = False, from_stage: str | None = None,
          until: str | None = None) -> dict:
    names = [s.name for s in PRODUCE_ORDER]
    if from_stage and from_stage not in names:
        raise SystemExit(f"unknown stage {from_stage!r}")
    if until and until not in names:
        raise SystemExit(f"unknown stage {until!r}")
    status = empty_status(ctx.slug, names)
    status["state"] = "running"
    status["started"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_status(ctx.status_path, status)
    log(f"bundle: {ctx.bundle.title!r} ({ctx.slug}) voice={bundle_voice_spec(ctx)} "
        f"-> build/{ctx.slug}/{ctx.variant}")
    t0 = time.time()
    forcing = force
    try:
        for stg in PRODUCE_ORDER:
            if from_stage == stg.name:
                forcing = True
            mark_stage(ctx.status_path, stg.name, "running")
            ran = execute(ctx, stg, PRODUCE_REGISTRY, force=forcing)
            mark_stage(ctx.status_path, stg.name, "ok" if ran else "cached")
            if until == stg.name:
                break
        outs = output_paths(ctx)
        mark(ctx.status_path, state="ok", finished=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             outputs=outs, slug=ctx.slug)
        log(f"finished in {time.time() - t0:.1f}s -> {ctx.out_dir}")
        return {**empty_status(ctx.slug, names), "state": "ok", "outputs": outs,
                "seconds": round(time.time() - t0, 2)}
    except Exception as e:
        mark(ctx.status_path, state="error", error=str(e),
             finished=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), slug=ctx.slug)
        raise
