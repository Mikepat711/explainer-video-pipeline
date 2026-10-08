"""Skia scene renderer: design 1920×1080, optional scale, parallel workers, libx264."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from ..draw.lib import H as DESIGN_H
from ..draw.lib import W as DESIGN_W
from ..draw.lib import caption, scene_chip, smooth, prog
from ..pipeline import Stage
from ..util import file_fingerprint, log, read_json, write_json

XF = 0.45  # crossfade from the previous scene's last frame, matching the toolkit


class Timing:
    def __init__(self, sid: str, timing: dict, words: dict):
        v = timing["scenes"] if isinstance(timing.get("scenes"), list) else None
        if v is not None:
            row = next(s for s in v if s["id"] == sid)
        else:
            row = timing[sid]
        self.s = [x["start"] for x in row["sentences"]]
        self.e = [x["end"] for x in row["sentences"]]
        self.dur = float(row["duration"])
        self.sents = row["sentences"]
        self.title = row.get("title") or sid
        self.words = words.get(sid, [])

    def w(self, word, default, n=0, after=0.0):
        k = 0
        for item in self.words:
            wd, a = item[0], item[1]
            if a >= after and (wd == word or str(wd).startswith(word)):
                if k == n:
                    return a
                k += 1
        return default


def _timing_map(timing: dict) -> dict:
    if isinstance(timing.get("scenes"), list):
        return {s["id"]: s for s in timing["scenes"]}
    return {k: v for k, v in timing.items() if isinstance(v, dict) and "sentences" in v}


def nframes(sid: str, timing: dict, fps: int) -> int:
    tm = _timing_map(timing)
    return int(math.ceil(tm[sid]["duration"] * fps))


def cap_alpha(sents, t):
    from ..draw.lib import smooth as sm, prog as pr
    for i, x in enumerate(sents):
        out = x["end"] + 0.3
        if i + 1 < len(sents):
            out = min(out, sents[i + 1]["start"] - 0.2)
        a = sm(pr(t, x["start"] - 0.1, 0.15)) * (1 - sm(pr(t, out, 0.15)))
        if a > 0:
            return x["text"], a
    return None, 0


def _order(timing: dict) -> list[str]:
    tm = _timing_map(timing)
    return [k for k, _ in sorted(tm.items(), key=lambda kv: kv[1].get("index", 0))]


def draw_frame(surface, sid, t, funcs, timing, words, prev_img=None, xf=XF):
    import skia
    c = surface.getCanvas()
    c.clear(skia.ColorBLACK)
    from ..draw.lib import background
    T = Timing(sid, timing, words)
    c.drawImage(background(), 0, 0)
    funcs[sid](c, t, T)
    if prev_img is not None and t < xf:
        a = 1 - smooth(t / xf)
        c.drawImage(prev_img, 0, 0, skia.SamplingOptions(), skia.Paint(Alphaf=a))
    tm = _timing_map(timing)
    idx = tm[sid].get("index", 0)
    chip_a = smooth(prog(t, 0.25, 0.5)) if idx > 0 else smooth(prog(t, 0.2, 0.6))
    scene_chip(c, T.title, chip_a)
    txt, a = cap_alpha(T.sents, t)
    caption(c, txt, a)
    return T


def last_frame_image(sid, funcs, timing, words, fps):
    import skia
    s = skia.Surface(DESIGN_W, DESIGN_H)
    n = nframes(sid, timing, fps)
    draw_frame(s, sid, (n - 1) / fps, funcs, timing, words)
    return s.makeImageSnapshot()


def _scale_bgra(img, out_w: int, out_h: int) -> bytes:
    import skia
    if img.width() == out_w and img.height() == out_h:
        return img.toarray().tobytes()
    surf = skia.Surface(out_w, out_h)
    c = surf.getCanvas()
    c.scale(out_w / DESIGN_W, out_h / DESIGN_H)
    c.drawImage(img, 0, 0)
    return surf.makeImageSnapshot().toarray().tobytes()


def render_scene_clip(sid, funcs, timing, words, out_mp4: Path, fps: int, out_w: int, out_h: int,
                      crf: int, preset: str, prev_sid: str | None, max_frames: int | None = None) -> int:
    import skia
    n = nframes(sid, timing, fps)
    if max_frames:
        n = min(n, max_frames)
    prev_img = last_frame_image(prev_sid, funcs, timing, words, fps) if prev_sid else None
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{out_w}x{out_h}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-r", str(fps), str(out_mp4),
    ]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    s = skia.Surface(DESIGN_W, DESIGN_H)
    try:
        for f in range(n):
            draw_frame(s, sid, f / fps, funcs, timing, words, prev_img)
            p.stdin.write(_scale_bgra(s.makeImageSnapshot(), out_w, out_h))
    finally:
        if p.stdin:
            p.stdin.close()
        rc = p.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed encoding scene {sid} (exit {rc})")
    return n


def render_still(sid, t, funcs, timing, words, dest: Path, fps: int, prev_sid: str | None = None) -> Path:
    import skia
    prev_img = None
    if prev_sid is not None and t < XF:
        prev_img = last_frame_image(prev_sid, funcs, timing, words, fps)
    s = skia.Surface(DESIGN_W, DESIGN_H)
    draw_frame(s, sid, t, funcs, timing, words, prev_img)
    dest.parent.mkdir(parents=True, exist_ok=True)
    s.makeImageSnapshot().save(str(dest), skia.kPNG)
    return dest


_WORKER = {}


def _worker_init(payload: dict):
    from ..bundle.load import load_bundle
    from ..draw.lib import reset_caches
    reset_caches()
    loaded = load_bundle(Path(payload["bundle"]))
    words = {}
    wp = Path(payload["words"])
    if wp.is_file():
        words = read_json(wp)
    _WORKER.update({
        "funcs": loaded.scene_funcs,
        "timing": read_json(Path(payload["timing"])),
        "words": words,
        "fps": payload["fps"],
        "out_w": payload["out_w"],
        "out_h": payload["out_h"],
        "crf": payload["crf"],
        "preset": payload["preset"],
        "clips": Path(payload["clips"]),
        "order": payload["order"],
        "max_frames": payload.get("max_frames"),
    })


def _worker_render(sid: str) -> tuple[str, int]:
    w = _WORKER
    order = w["order"]
    idx = order.index(sid)
    prev = order[idx - 1] if idx > 0 else None
    n = render_scene_clip(
        sid, w["funcs"], w["timing"], w["words"],
        w["clips"] / f"{idx:02d}_{sid}.mp4",
        w["fps"], w["out_w"], w["out_h"], w["crf"], w["preset"], prev,
        max_frames=w.get("max_frames"),
    )
    return sid, n


class Render(Stage):
    name = "render"
    scope = "variant"
    deps = ("voice",)
    extra_code = ("draw", "produce/render.py")
    owns = ("scenes/*.mp4",)
    description = "draw scenes with skia-python and encode libx264 (parallel workers)"

    def inputs(self, ctx):
        w, h = ctx.frame_size
        return {
            "size": [w, h],
            "fps": ctx.fps,
            "crf": ctx.cfg["video"]["crf"],
            "workers": ctx.workers or ctx.cfg["render"]["workers"],
            "scenes": [s.id for s in ctx.selected_scenes()],
            "bundle": {p.name: file_fingerprint(p) for p in (
                [ctx.bundle.root / ctx.bundle.manifest.scenes,
                 ctx.bundle.root / ctx.bundle.manifest.script]
                + [ctx.bundle.root / m for m in ctx.bundle.manifest.modules]
            ) if p.is_file()},
        }

    def outputs(self, ctx):
        clips = ctx.vdir / "scenes"
        timing = read_json(ctx.common / "voice" / "timing.json") if (ctx.common / "voice" / "timing.json").exists() else {}
        tm = _timing_map(timing)
        selected = ctx.selected_scenes()
        return [clips / f"{tm.get(s.id, {}).get('index', s.index):02d}_{s.id}.mp4" for s in selected] + [
            ctx.vdir / "poster.png"
        ]

    def run(self, ctx):
        import skia
        from ..bundle.load import load_bundle
        loaded = load_bundle(ctx.bundle.root)
        timing = read_json(ctx.common / "voice" / "timing.json")
        words_p = ctx.common / "voice" / "words.json"
        words = read_json(words_p) if words_p.exists() else {}
        if ctx.max_seconds:
            # shrink each selected scene's duration for smoke / review renders
            tm = _timing_map(timing)
            leftover = float(ctx.max_seconds)
            for s in ctx.selected_scenes():
                row = tm[s.id]
                row["duration"] = min(row["duration"], leftover)
                leftover = max(0.1, leftover - row["duration"])
        w, h = ctx.frame_size
        fps = ctx.fps
        clips = ctx.vdir / "scenes"
        clips.mkdir(parents=True, exist_ok=True)
        for old in clips.glob("*.mp4"):
            old.unlink()
        order = [s.id for s in ctx.bundle.scenes]
        todo = [s.id for s in ctx.selected_scenes()]
        workers = max(1, int(ctx.workers or ctx.cfg["render"]["workers"]))
        crf = int(ctx.cfg["video"]["crf"])
        preset = str(ctx.cfg["video"]["preset"])
        max_frames = None
        if ctx.max_seconds and len(todo) == 1:
            max_frames = int(math.ceil(ctx.max_seconds * fps))
        payload = {
            "bundle": str(ctx.bundle.root),
            "timing": str(ctx.common / "voice" / "timing.json"),
            "words": str(words_p),
            "fps": fps, "out_w": w, "out_h": h, "crf": crf, "preset": preset,
            "clips": str(clips), "order": order, "max_frames": max_frames,
        }
        if ctx.max_seconds:
            # write the truncated timing the workers will read
            write_json(ctx.vdir / "timing.truncated.json", timing)
            payload["timing"] = str(ctx.vdir / "timing.truncated.json")
        log(f"    rendering {len(todo)} scene(s) at {w}x{h} @{fps} with {workers} worker(s)")
        if workers == 1 or len(todo) == 1:
            _worker_init(payload)
            for sid in sorted(todo, key=lambda x: -_timing_map(timing)[x]["duration"]):
                sid, n = _worker_render(sid)
                log(f"    rendered {sid} ({n} frames)")
        else:
            import multiprocessing as mp
            ctx_ = mp.get_context("spawn")
            with ctx_.Pool(workers, initializer=_worker_init, initargs=(payload,)) as pool:
                for sid, n in pool.imap_unordered(_worker_render, todo):
                    log(f"    rendered {sid} ({n} frames)")
        # poster: first scene, mid-first-sentence or 1.0s
        first = ctx.selected_scenes()[0]
        tm = _timing_map(timing)
        t0 = tm[first.id]["sentences"][0]["start"] + 0.4
        render_still(first.id, t0, loaded.scene_funcs, timing, words, ctx.vdir / "poster.png", fps)
        # copy a readable still into out later; keep one in the variant dir
        write_json(ctx.vdir / "render.json", {
            "scenes": todo, "width": w, "height": h, "fps": fps, "encoder": "libx264",
        })
