from __future__ import annotations

import multiprocessing as mp
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from ..config import frame_size
from ..gfx.render import make_renderer, render_png, render_video
from ..pipeline import Stage
from ..util import log, read_json, sha256_json, write_json

READABLE = {"text", "label", "meter", "badge"}

def _meta(sc: dict, tl: dict) -> dict:
    last = sc["index"] == len(tl["scenes"])
    return {"index": sc["index"], "title": tl["title"], "global_start": sc["start"], "total_duration": tl["total"],
            "last": last, "tail": 0.0 if last else tl["crossfade"]}


def _render_one(args):
    sc, tl, cfg, size, out = args
    render_video(sc["spec"], sc["duration"], _meta(sc, tl), cfg, size, Path(out))
    return sc["id"]


def _overlap(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy / max(1.0, min(aw * ah, bw * bh))


def probe_times(sc: dict) -> list[float]:
    """Mid-scene and just before the cut; plan scenes also right after each reveal, move and camera beat."""
    d = sc["duration"]
    ts = {round(d * 0.55, 2), round(max(0.0, d - 0.55), 2)}
    if sc["spec"].get("engine") == "plan":
        for b in sc["spec"]["scene"].get("beats", []):
            if b.get("do") in ("enter", "move", "camera"):
                end = float(b["at"]) + float(b.get("dur") or 1.2) + 0.3
                if end < d - 0.1:
                    ts.add(round(end, 2))
    return sorted(ts)


def layout_check(sc: dict, tl: dict, cfg: dict, size) -> dict:
    r = make_renderer(sc["spec"], sc["duration"], _meta(sc, tl), cfg, size)
    plan = sc["spec"].get("engine") == "plan"
    w, h = size
    issues = []
    seen, shown = set(), set()
    for t in probe_times(sc):
        res = r.probe(t)
        boxes = res["boxes"]
        if plan:
            # the camera may frame a detail or pan past things: text mostly outside the view is not on screen
            boxes = [b for b in boxes if _overlap(b[1], (0, 0, w, h)) > 0.5]
            seen |= {tag.partition(".")[0] for tag, _ in boxes}
            shown |= {a.id for a in r.model.actors.values() if a.kind in READABLE and a.presence(t).alpha > 0.5}
        for tag, (x, y, bw, bh) in boxes:
            if x < 4 or y < 4 or x + bw > w - 4 or y + bh > h - 4:
                issues.append(f"t={t}s '{tag}' extends outside the frame")
            elif y + bh > r.L.caption_top + 2 and cfg["captions"]["burn_in"]:
                issues.append(f"t={t}s '{tag}' intrudes into the caption area")
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if boxes[i][0] != boxes[j][0] and _overlap(boxes[i][1], boxes[j][1]) > 0.12:
                    issues.append(f"t={t}s text '{boxes[i][0]}' overlaps '{boxes[j][0]}'")
        issues += [f"t={t}s {wmsg}" for wmsg in res["warnings"]]
    issues += [f"'{i}' is visible but never on screen (outside the camera view)" for i in sorted(shown - seen)]
    return {"id": sc["id"], "template": sc["spec"].get("template", "plan"), "issues": sorted(set(issues))}


class Render(Stage):
    name = "render"
    deps = ("timeline",)
    description = "render animated scenes (cairo motion graphics -> H.264)"
    extra_code = ("gfx",)

    def inputs(self, ctx):
        return {"video": ctx.cfg["video"], "style": ctx.cfg["style"], "captions": ctx.cfg["captions"]["burn_in"]}

    def outputs(self, ctx):
        tl = read_json(ctx.vdir / "timeline.json")
        d = ctx.vdir / "scenes"
        return [d / f"{s['id']}.mp4" for s in tl["scenes"]] + [ctx.vdir / "poster.png",
                                                                 ctx.vdir / "layout_report.json"]

    def run(self, ctx):
        tl = read_json(ctx.vdir / "timeline.json")
        size = frame_size(ctx.cfg)
        d = ctx.vdir / "scenes"
        d.mkdir(parents=True, exist_ok=True)
        code = self.code_hash()
        jobs = []
        for sc in tl["scenes"]:
            key = sha256_json({"sc": sc, "meta": _meta(sc, tl), "cfg": self.inputs(ctx), "code": code})
            out, kf = d / f"{sc['id']}.mp4", d / f"{sc['id']}.key"
            if out.exists() and kf.exists() and kf.read_text() == key:
                log(f"    scene {sc['id']}: cached")
                continue
            jobs.append(((sc, tl, ctx.cfg, size, str(out)), kf, key))
        if jobs:
            workers = max(1, min(int(ctx.cfg["render"]["workers"]), len(jobs)))
            log(f"    rendering {len(jobs)} scene(s) with {workers} worker(s)")
            # macOS: cairo's Quartz font backend uses CoreFoundation, which crashes in fork()ed children.
            # The executor raises BrokenProcessPool if a worker dies, where Pool.imap would hang forever.
            mp_ctx = mp.get_context("spawn" if sys.platform == "darwin" else "fork")
            limit = float(ctx.cfg["render"].get("scene_timeout", 900)) * -(-len(jobs) // workers)
            pool = ProcessPoolExecutor(workers, mp_context=mp_ctx)
            try:
                for fut in as_completed([pool.submit(_render_one, j[0]) for j in jobs], timeout=limit):
                    log(f"    scene {fut.result()}: rendered")
            except BaseException as exc:
                # Leaving a `with` block would wait for hung workers, so kill them and fail fast.
                for proc in list((getattr(pool, "_processes", None) or {}).values()):
                    proc.terminate()
                pool.shutdown(wait=False, cancel_futures=True)
                if isinstance(exc, FuturesTimeout):
                    raise SystemExit(f"render timed out after {limit:.0f}s (render.scene_timeout="
                                     f"{ctx.cfg['render'].get('scene_timeout', 900)}s per scene); workers killed")
                if isinstance(exc, BrokenProcessPool):
                    raise SystemExit("a render worker crashed (see the error above); remaining workers killed")
                raise
            pool.shutdown()
            for _, kf, key in jobs:
                kf.write_text(key)
        report = [layout_check(sc, tl, ctx.cfg, size) for sc in tl["scenes"]]
        n_issues = sum(len(r["issues"]) for r in report)
        log(f"    layout check: {n_issues} issue(s)")
        for r in report:
            for msg in r["issues"]:
                log(f"      [{r['id']}] {msg}")
        write_json(ctx.vdir / "layout_report.json", report)
        first, poster_t = tl["scenes"][0], None
        if tl.get("poster"):
            first = next((s for s in tl["scenes"] if s["id"] == tl["poster"]["scene"]), first)
            poster_t = tl["poster"]["t"]
        if poster_t is None:
            poster_t = min(first["duration"] - 0.6, 3.2)
        render_png(first["spec"], first["duration"], dict(_meta(first, tl), progress_bar=False), ctx.cfg, size,
                   poster_t, ctx.vdir / "poster.png")
