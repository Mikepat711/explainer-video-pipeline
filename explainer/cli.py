from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .brief import load_brief
from .config import load_config
from .pipeline import Context, execute
from .stages import ORDER, REGISTRY
from .util import LIBASS_HELP, ffmpeg_with_libass, log
from .writer import WRITER_STAGES, banner, read_metas


def _ctx(args) -> Context:
    scenes = [s.strip() for s in args.scenes.split(",")] if args.scenes else None
    ctx = Context(topic=args.topic, cfg={}, scenes_filter=scenes, source_urls=args.source or [],
                  tag=args.tag or "", fresh=args.fresh)
    ctx.brief = load_brief(ctx.topic_dir, args.brief, args.require)
    ctx.cfg = load_config(args.config, _sets(args), args.aspect, topic=ctx.brief.config)
    if ctx.brief:
        log(f"brief: {len(ctx.brief.require)} required topics ({', '.join(ctx.brief.ids) or 'none'})"
            f"{' + notes' if ctx.brief.notes else ''} from {', '.join(ctx.brief.origins)}")
    from .writer import writer_identity
    log(f"writer: {writer_identity(ctx.cfg)}" + (f" (build folders tagged -{ctx.writer_tag})" if ctx.writer_tag else "")
        + (f"; grind (layout fix): {writer_identity(ctx.cfg, 'layout')}" if ctx.grind_tag else ""))
    if ctx.fresh:
        log("fresh: ignoring the topic pack's pinned research/script/plan; the writer writes new ones")
    return ctx


def _sets(args) -> list[str]:
    """--set values, plus --voice / --writer (applied last, so they beat EXPLAINER_VOICE / EXPLAINER_WRITER)."""
    return ((args.set or []) + ([f"voice.use={args.voice}"] if getattr(args, "voice", None) else [])
            + ([f"llm.writer={args.writer}"] if getattr(args, "writer", None) else [])
            + ([f"llm.grind={args.grind}"] if getattr(args, "grind", None) else []))


def _common(p: argparse.ArgumentParser):
    p.add_argument("topic", help='e.g. "how GPS works"')
    p.add_argument("--config", action="append", help="extra YAML merged over config.yaml (repeatable)")
    p.add_argument("--set", action="append", metavar="KEY=VALUE", help="override a config value, e.g. "
                   "voice.use=kokoro:bm_george")
    p.add_argument("--aspect", choices=["16:9", "9:16"], help="shortcut for --set video.aspect=...")
    p.add_argument("--voice", metavar="ENGINE:VOICE", help="narrator for this run, e.g. elevenlabs:max, "
                   "elevenlabs:todd, elevenlabs:<voice id> or kokoro:af_heart (shortcut for --set voice.use=...); "
                   "required unless voice.use / EXPLAINER_VOICE sets a default")
    p.add_argument("--writer", choices=["claude", "grok", "off"], help="who writes the research, script and visual "
                   "plan (shortcut for --set llm.writer=...; default claude, or EXPLAINER_WRITER)")
    p.add_argument("--grind", choices=["grok", "claude", "off"], help="who does the mechanical follow-up work on "
                   "the plan (the layout-fix stage); shortcut for --set llm.grind=... (default off, or EXPLAINER_GRIND)")
    p.add_argument("--scenes", help="comma-separated scene ids to include (short/partial renders)")
    p.add_argument("--tag", help="variant name suffix for the output folder (e.g. 'short')")
    p.add_argument("--source", action="append", help="source document URL for research (repeatable)")
    p.add_argument("--brief", action="append", metavar="FILE", help="extra writer brief: required topics and "
                   "notes (topics/<slug>/brief.md is always read; see README > Briefs)")
    p.add_argument("--require", action="append", metavar='"ID: TOPIC"', help="a topic the research, script and "
                   'visual plan must cover, e.g. --require "wind: how a wind turbine makes power" (repeatable)')
    p.add_argument("--fresh", action="store_true", help="set aside the topic pack's pinned research.md, script.md "
                   "and plan.json so Claude writes new ones (no offline fallback)")
    p.add_argument("--force", action="store_true", help="re-run even if cached")


def _preview(ctx: Context, at: str) -> int:
    from .config import frame_size
    from .gfx.render import render_png
    from .util import read_json
    for stg in ORDER[:ORDER.index(REGISTRY["timeline"]) + 1]:
        execute(ctx, stg, REGISTRY)
    tl = read_json(ctx.vdir / "timeline.json")
    out = ctx.vdir / "preview"
    out.mkdir(exist_ok=True)
    for sc in tl["scenes"]:
        meta = {"index": sc["index"], "title": tl["title"], "global_start": sc["start"],
                "total_duration": tl["total"]}
        for tok in at.split(","):
            t = sc["duration"] - 0.6 if tok.strip() == "end" else float(tok) * sc["duration"]
            p = out / f"{sc['index']:02d}_{sc['id']}_{t:05.1f}.png"
            render_png(sc["spec"], sc["duration"], meta, ctx.cfg, frame_size(ctx.cfg), t, p)
            print(p.relative_to(ctx.build_root.parent))
    return 0


def _frames(ctx: Context, args) -> int:
    from .config import frame_size
    from .frames import contact_sheet, render_frames
    from .util import read_json
    from .scriptfmt import parse_script
    plan = read_json(Path(args.plan) if args.plan else ctx.common / "plan.json")
    script_path = Path(args.script) if args.script else ctx.common / "script.json"
    script = parse_script(script_path.read_text()) if script_path.suffix == ".md" else read_json(script_path)
    if plan.get("legacy_shots") or not plan.get("scenes"):
        raise SystemExit("this topic has no visual plan (legacy shots.yaml); use `preview` instead")
    timing = None
    tp = ctx.common / "voice" / "timing.json"
    if tp.exists() and not args.script:
        timing = {s["id"]: s for s in read_json(tp)["scenes"]}
        if any(len(timing.get(sc["id"], {}).get("sentences", [])) != len(sc["sentences"]) for sc in script["scenes"]):
            timing = None
    log(f"timing: {'narration (voice/timing.json)' if timing else 'estimated from word counts'}")
    out = Path(args.out) if args.out else ctx.vdir / "frames"
    shots = render_frames(plan, script, ctx.cfg, out, frame_size(ctx.cfg), args.per_scene, timing, ctx.scenes_filter)
    sheet = contact_sheet(shots, out / "contact_sheet.jpg", title=script.get("title", ""))
    log(f"{len(shots)} frames + {sheet.name} -> {out}")
    return 0


def _looks_like_bundle(spec: str) -> bool:
    p = Path(spec).expanduser()
    if p.is_file() and (str(spec).endswith(".tgz") or str(spec).endswith(".tar.gz") or p.suffix == ".tar"):
        return True
    if p.is_dir() and (p / "manifest.yaml").is_file():
        return True
    from .bundle.load import BUNDLES_DIR_DEFAULT
    from .util import REPO_ROOT
    name = p.name
    for root in (Path(BUNDLES_DIR_DEFAULT).expanduser(), REPO_ROOT / "examples", Path.cwd(), Path.cwd() / "examples"):
        if (root / name / "manifest.yaml").is_file():
            return True
    return False


def _pack(args) -> int:
    from .bundle.pack import pack_bundle
    dest = pack_bundle(Path(args.bundle), Path(args.out) if args.out else None)
    print(dest)
    log(f"packed {dest} ({dest.stat().st_size} bytes). Copy it to ~/explainer-bundles/<slug>/ "
        f"(or drop the unpacked directory there) and run `explainer build <slug>`.")
    return 0


def _build_ctx(args):
    from .produce.pipeline import make_context
    scenes = None
    if getattr(args, "scenes", None):
        scenes = [s.strip() for s in args.scenes.split(",") if s.strip()]
    if getattr(args, "scene", None):
        scenes = [args.scene.strip()]
    cfg = load_config(args.config, _sets(args))
    produce = cfg.get("produce") or {}
    return make_context(
        args.bundle, cfg,
        scenes_filter=scenes,
        tag=getattr(args, "tag", "") or "",
        scale=float(getattr(args, "scale", 1.0) or 1.0),
        max_seconds=getattr(args, "max_seconds", None),
        workers=args.workers if getattr(args, "workers", None) else (produce.get("workers") or None) or None,
        asr=getattr(args, "asr", None) or produce.get("asr") or "auto",
        deliver=not getattr(args, "no_deliver", False),
        share_max_mb=getattr(args, "share_max_mb", None) or float(produce.get("share_max_mb") or 25),
        out_width=getattr(args, "width", None),
        out_height=getattr(args, "height", None),
    )


def _build(args) -> int:
    from .produce.pipeline import build, still_frame
    from .produce.status import snapshot
    from .produce import PRODUCE_ORDER, PRODUCE_REGISTRY
    if args.detached:
        ctx = _build_ctx(args)
        ctx.status_path.parent.mkdir(parents=True, exist_ok=True)
        argv = [a for a in (sys.argv[1:] if args is None else None) or []]
        # rebuild argv without --detached from this process's args
        child = [sys.executable, "-m", "explainer", "build", args.bundle]
        if args.config:
            for c in args.config:
                child += ["--config", c]
        if args.set:
            for s in args.set:
                child += ["--set", s]
        for flag, val in (
            ("--voice", args.voice), ("--scenes", args.scenes), ("--scene", args.scene),
            ("--still", args.still), ("--out-still", args.out_still),
            ("--scale", args.scale if args.scale != 1.0 else None),
            ("--width", args.width), ("--height", args.height),
            ("--max-seconds", args.max_seconds), ("--workers", args.workers),
            ("--asr", args.asr), ("--share-max-mb", args.share_max_mb),
            ("--from", args.from_stage), ("--until", args.until), ("--tag", args.tag or None),
        ):
            if val not in (None, "", False):
                child += [flag, str(val)]
        if args.force:
            child.append("--force")
        if args.no_deliver:
            child.append("--no-deliver")
        if args.json:
            child.append("--json")
        logf = open(ctx.log_path, "ab")
        proc = subprocess.Popen(child, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
        print(json.dumps({"pid": proc.pid, "log": str(ctx.log_path), "status": str(ctx.status_path),
                          "slug": ctx.slug}, indent=2))
        return 0
    ctx = _build_ctx(args)
    if args.still:
        sid, _, ts = args.still.partition(":")
        if not ts:
            raise SystemExit("--still needs SCENE:SECONDS (e.g. hook:2.5)")
        # voice must exist for timing
        from .pipeline import is_fresh
        from .produce.voice import Voice
        if not is_fresh(ctx, Voice(), PRODUCE_REGISTRY):
            execute(ctx, Voice(), PRODUCE_REGISTRY)
        dest = Path(args.out_still) if args.out_still else None
        path = still_frame(ctx, sid.strip(), float(ts), dest)
        print(path)
        return 0
    build(ctx, force=args.force, from_stage=args.from_stage, until=args.until)
    if args.json:
        print(json.dumps(snapshot(ctx, PRODUCE_REGISTRY, PRODUCE_ORDER), indent=2))
    return 0


def _bundle_status(spec: str, as_json: bool) -> int:
    from .produce import PRODUCE_ORDER, PRODUCE_REGISTRY
    from .produce.pipeline import make_context
    from .produce.status import snapshot
    ctx = make_context(spec, load_config())
    data = snapshot(ctx, PRODUCE_REGISTRY, PRODUCE_ORDER)
    if as_json:
        print(json.dumps(data, indent=2))
        return 0
    print(f"{data['slug']}  {data['state']}")
    for name, row in data["stages"].items():
        print(f"  {name:10s} {row.get('state')}")
    for k, v in (data.get("outputs") or {}).items():
        print(f"  {k}: {v}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="explainer", description="Turn a technical topic into a ~2 min explainer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the whole pipeline (cached stages are skipped)")
    _common(r)
    r.add_argument("--from", dest="from_stage", choices=list(REGISTRY), help="force re-run from this stage on")
    r.add_argument("--until", choices=list(REGISTRY), help="stop after this stage")
    s = sub.add_parser("stage", help="run a single stage (uses cached upstream outputs)")
    s.add_argument("name", choices=list(REGISTRY))
    _common(s)
    st = sub.add_parser("status", help="show which stages are cached/stale")
    _common(st)
    c = sub.add_parser("clean", help="delete build + output folders for a topic")
    _common(c)
    pv = sub.add_parser("preview", help="render still frames per scene (fast layout check; needs timeline)")
    _common(pv)
    pv.add_argument("--at", default="0.5,end", help="comma list of scene fractions or 'end' (= end-0.6s)")
    fr = sub.add_parser("frames", help="still frames + contact sheet from the visual plan (no narration needed)")
    _common(fr)
    fr.add_argument("--plan", help="plan.json to draw (default: build/<slug>/common/plan.json)")
    fr.add_argument("--script", help="script.json or script.md it belongs to (default: build/<slug>/common/script.json)")
    fr.add_argument("--per-scene", type=int, default=4, help="frames per scene (default 4)")
    fr.add_argument("--out", help="output folder (default: build/<slug>/<variant>/frames)")
    sub.add_parser("stages", help="list stages")
    vo = sub.add_parser("voices", help="list voices, or render the same paragraph with several for comparison")
    vo.add_argument("--list", action="store_true", help="list available voice ids")
    vo.add_argument("--try", dest="specs", help="comma list of engine:voice, e.g. kokoro:af_heart,piper:en_US-ryan-high")
    vo.add_argument("--text", help="paragraph to read (default: a sentence block from the GPS sample)")
    vo.add_argument("--out", default="out/voices", help="output folder for the comparison clips")
    vo.add_argument("--config", action="append", help="extra YAML merged over config.yaml")
    vo.add_argument("--set", action="append", metavar="KEY=VALUE", help="override a config value")
    vo.add_argument("--voice", metavar="ENGINE:VOICE", help="shortcut for --set voice.use=...")
    sh = sub.add_parser("share", help="size-capped copy of a finished video for chat/email (2-pass fitted)")
    sh.add_argument("video", help="path to a finished MP4")
    sh.add_argument("--out", help="output path (default: <name>-share.mp4 next to the input)")
    sh.add_argument("--max-mb", type=float, default=15.0, help="size cap in MB (default 15)")
    sh.add_argument("--height", type=int, help="optional downscale, e.g. 720")
    bld = sub.add_parser("build", help="produce a project bundle (no LLM writer)")
    bld.add_argument("bundle", help="bundle directory, .tgz, or slug under ~/explainer-bundles or examples/")
    bld.add_argument("--config", action="append", help="extra YAML merged over config.yaml")
    bld.add_argument("--set", action="append", metavar="KEY=VALUE")
    bld.add_argument("--voice", metavar="ENGINE:VOICE",
                     help="narrator (default: manifest voice, else kokoro:af_heart). "
                          "elevenlabs:max, elevenlabs:todd, kokoro:af_heart, silence")
    bld.add_argument("--scenes", help="comma-separated scene ids to render")
    bld.add_argument("--scene", help="render a single scene (shortcut for --scenes)")
    bld.add_argument("--still", metavar="SCENE:SECONDS", help="write a PNG at this scene timestamp and exit")
    bld.add_argument("--frame", dest="still", metavar="SCENE:SECONDS", help=argparse.SUPPRESS)
    bld.add_argument("--out-still", help="path for --still (default: build/<slug>/<variant>/stills/...)")
    bld.add_argument("--scale", type=float, default=1.0, help="output scale (1.0 = 1920x1080)")
    bld.add_argument("--width", type=int, help="output width (even); overrides --scale")
    bld.add_argument("--height", type=int, help="output height (even); overrides --scale")
    bld.add_argument("--max-seconds", type=float, help="cap rendered duration (smoke / review)")
    bld.add_argument("--workers", type=int, help="parallel scene render workers")
    bld.add_argument("--asr", choices=["auto", "on", "off"], default=None, help="ASR check of narration vs script")
    bld.add_argument("--no-deliver", action="store_true", help="do not copy the MP4 to EXPLAINER_DELIVER_DIR")
    bld.add_argument("--share-max-mb", type=float, default=None, help="share-copy size cap (default 25)")
    bld.add_argument("--from", dest="from_stage", help="force re-run from this stage on")
    bld.add_argument("--until", help="stop after this stage")
    bld.add_argument("--force", action="store_true")
    bld.add_argument("--tag", default="", help="variant name suffix")
    bld.add_argument("--detached", action="store_true",
                     help="start the build in the background, write a log, print JSON and return")
    bld.add_argument("--json", action="store_true", help="print status JSON when the build finishes")
    pk = sub.add_parser("pack", help="tar a project bundle (code only) so it can be copied elsewhere")
    pk.add_argument("bundle", help="bundle directory")
    pk.add_argument("--out", help="tarball path (default: <slug>.tgz next to the directory)")
    st.add_argument("--json", action="store_true", help="print machine-readable status (bundle or topic)")
    args = ap.parse_args(argv)

    if args.cmd == "stages":
        for stg in ORDER:
            print(f"{stg.name:10s} [{stg.scope:7s}] {stg.description}")
        print("\nbundle production:")
        from .produce import PRODUCE_ORDER
        for stg in PRODUCE_ORDER:
            print(f"{stg.name:10s} [{stg.scope:7s}] {stg.description}")
        return 0
    if args.cmd == "pack":
        return _pack(args)
    if args.cmd == "build":
        return _build(args)
    if args.cmd == "share":
        from .share import share_copy
        src = Path(args.video)
        share_copy(src, Path(args.out) if args.out else src.with_name(f"{src.stem}-share.mp4"), args.max_mb,
                   height=args.height)
        return 0
    if args.cmd == "voices":
        from . import voices
        cfg = load_config(args.config, _sets(args))
        if args.list:
            voices.list_voices(cfg)
            return 0
        specs = [s.strip() for s in args.specs.split(",")] if args.specs else voices.presets(cfg)
        voices.audition(cfg, specs, args.text or voices.SAMPLE_TEXT, Path(args.out))
        return 0
    if args.cmd in ("status", "clean") and _looks_like_bundle(args.topic):
        if args.cmd == "status":
            return _bundle_status(args.topic, getattr(args, "json", False))
        from .bundle.load import resolve_bundle
        from .bundle.schema import validate_bundle
        from .util import REPO_ROOT
        root = resolve_bundle(args.topic)
        slug = validate_bundle(root).slug
        for d in (REPO_ROOT / "build" / slug, REPO_ROOT / "out" / slug):
            shutil.rmtree(d, ignore_errors=True)
        log(f"removed build/{slug} and out/{slug}")
        return 0
    ctx = _ctx(args)
    if args.cmd == "clean":
        for d in (ctx.build_root / ctx.slug, ctx.out_root / ctx.slug):
            shutil.rmtree(d, ignore_errors=True)
        log(f"removed build/{ctx.slug} and out/{ctx.slug}")
        return 0
    if args.cmd == "status":
        if _looks_like_bundle(args.topic):
            return _bundle_status(args.topic, getattr(args, "json", False))
        from .pipeline import is_fresh
        rows = []
        for stg in ORDER:
            try:
                state = "cached" if is_fresh(ctx, stg, REGISTRY) else "stale"
            except SystemExit:
                state = "missing upstream"
            rows.append((stg.name, state))
            if not getattr(args, "json", False):
                print(f"{stg.name:10s} {state}")
        if getattr(args, "json", False):
            print(json.dumps({"topic": ctx.topic, "slug": ctx.slug, "variant": ctx.variant,
                              "stages": {n: {"state": s} for n, s in rows},
                              "outputs": {
                                  "mp4": str((ctx.out_dir / ctx.slug).with_suffix(".mp4")),
                                  "out_dir": str(ctx.out_dir),
                              }}, indent=2))
        return 0
    if args.cmd == "preview":
        return _preview(ctx, args.at)
    if args.cmd == "frames":
        return _frames(ctx, args)
    names = [s.name for s in ORDER]
    planned = [args.name] if args.cmd == "stage" else names[:names.index(args.until) + 1 if args.until else None]
    if any(names.index(n) >= names.index("voice") for n in planned):
        from .tts import resolve_voice
        log(f"narrator: {resolve_voice(ctx.cfg)['spec']}")  # stops here, before any writer call, if none was chosen
    if "assemble" in planned and ctx.cfg["captions"]["burn_in"] and not ffmpeg_with_libass():
        raise SystemExit(LIBASS_HELP)
    log(f"topic: {ctx.topic!r} -> build/{ctx.slug}/{ctx.variant}")
    t0 = time.time()
    if args.cmd == "stage":
        execute(ctx, REGISTRY[args.name], REGISTRY, force=args.force)
    else:
        forcing = args.force
        for stg in ORDER:
            if args.from_stage == stg.name:
                forcing = True
            execute(ctx, stg, REGISTRY, force=forcing)
            if args.until == stg.name:
                break
    fallbacks = [m for m in read_metas(ctx.common) if m.get("fallback")]
    if fallbacks:
        from .writer import writer_name
        banner(", ".join(m["stage"] for m in fallbacks), fallbacks[0].get("reason") or "", writer_name(ctx.cfg))
    last = args.name if args.cmd == "stage" else args.until
    where = f"build/{ctx.slug}/{ctx.common.name}/" if last in WRITER_STAGES else f"out/{ctx.slug}/{ctx.variant}/"
    log(f"finished in {time.time() - t0:.1f}s -> {where}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
