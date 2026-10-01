from __future__ import annotations

import argparse
import shutil
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
    ctx.cfg = load_config(args.config, args.set, args.aspect, topic=ctx.brief.config)
    if ctx.brief:
        log(f"brief: {len(ctx.brief.require)} required topics ({', '.join(ctx.brief.ids) or 'none'})"
            f"{' + notes' if ctx.brief.notes else ''} from {', '.join(ctx.brief.origins)}")
    if ctx.fresh:
        log("fresh: ignoring the topic pack's pinned research/script/plan; Claude writes new ones")
    return ctx


def _common(p: argparse.ArgumentParser):
    p.add_argument("topic", help='e.g. "how GPS works"')
    p.add_argument("--config", action="append", help="extra YAML merged over config.yaml (repeatable)")
    p.add_argument("--set", action="append", metavar="KEY=VALUE", help="override a config value, e.g. "
                   "voice.use=kokoro:bm_george")
    p.add_argument("--aspect", choices=["16:9", "9:16"], help="shortcut for --set video.aspect=...")
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
    sh = sub.add_parser("share", help="size-capped copy of a finished video for chat/email (2-pass fitted)")
    sh.add_argument("video", help="path to a finished MP4")
    sh.add_argument("--out", help="output path (default: <name>-share.mp4 next to the input)")
    sh.add_argument("--max-mb", type=float, default=15.0, help="size cap in MB (default 15)")
    sh.add_argument("--height", type=int, help="optional downscale, e.g. 720")
    args = ap.parse_args(argv)

    if args.cmd == "stages":
        for stg in ORDER:
            print(f"{stg.name:10s} [{stg.scope:7s}] {stg.description}")
        return 0
    if args.cmd == "share":
        from .share import share_copy
        src = Path(args.video)
        share_copy(src, Path(args.out) if args.out else src.with_name(f"{src.stem}-share.mp4"), args.max_mb,
                   height=args.height)
        return 0
    if args.cmd == "voices":
        from . import voices
        cfg = load_config(args.config, args.set)
        if args.list:
            voices.list_voices(cfg)
            return 0
        specs = [s.strip() for s in args.specs.split(",")] if args.specs else voices.presets(cfg)
        voices.audition(cfg, specs, args.text or voices.SAMPLE_TEXT, Path(args.out))
        return 0
    ctx = _ctx(args)
    if args.cmd == "clean":
        for d in (ctx.build_root / ctx.slug, ctx.out_root / ctx.slug):
            shutil.rmtree(d, ignore_errors=True)
        log(f"removed build/{ctx.slug} and out/{ctx.slug}")
        return 0
    if args.cmd == "status":
        from .pipeline import is_fresh
        for stg in ORDER:
            try:
                state = "cached" if is_fresh(ctx, stg, REGISTRY) else "stale"
            except SystemExit:
                state = "missing upstream"
            print(f"{stg.name:10s} {state}")
        return 0
    if args.cmd == "preview":
        return _preview(ctx, args.at)
    if args.cmd == "frames":
        return _frames(ctx, args)
    names = [s.name for s in ORDER]
    planned = [args.name] if args.cmd == "stage" else names[:names.index(args.until) + 1 if args.until else None]
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
        banner(", ".join(m["stage"] for m in fallbacks), fallbacks[0].get("reason") or "")
    last = args.name if args.cmd == "stage" else args.until
    where = f"build/{ctx.slug}/common/" if last in WRITER_STAGES else f"out/{ctx.slug}/{ctx.variant}/"
    log(f"finished in {time.time() - t0:.1f}s -> {where}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
