"""Human-readable renderings of writer output (research.md, script.md, plan.md)."""
from __future__ import annotations

import json

from ..scriptfmt import render_script


def research_markdown(brief: dict) -> str:
    out = [f"# Research brief: {brief['topic']}", "", f"**Audience:** {brief['audience']}", "",
           f"**Core question:** {brief['core_question']}", "", f"**Short answer:** {brief['short_answer']}", "",
           "## Key concepts", ""]
    for c in brief["key_concepts"]:
        out.append(f"- **{c['name']}**: {c['explanation']} _Mechanism:_ {c['mechanism']}"
                   + (f" _Visual:_ {c['visual_metaphor']}" if c.get("visual_metaphor") else ""))
    if brief.get("required_topics"):
        out += ["", "## Required topics", ""]
        for t in brief["required_topics"]:
            out.append(f"- **{t['id']}**: {t['explanation']} _Mechanism:_ {t['mechanism']} _Visual:_ {t['visual']}"
                       + (f" _Numbers:_ {'; '.join(t['numbers'])}" if t.get("numbers") else ""))
    out += ["", "## Process", ""] + [f"{i}. **{s['step']}**: {s['detail']}" for i, s in enumerate(brief["process"], 1)]
    out += ["", "## Numbers", ""] + [
        f"- {n['fact']}: {n['value']} {n.get('unit', '')}".rstrip() + (f" [{n['source']}]" if n.get("source") else "")
        for n in brief["numbers"]]
    out += ["", "## Misconceptions", ""] + [f"- _{m['myth']}_ → {m['truth']}" for m in brief["misconceptions"]]
    if brief.get("analogies"):
        out += ["", "## Analogies", ""] + [f"- {a}" for a in brief["analogies"]]
    out += ["", "## Sources", ""] + [
        f"- {s['title']}" + (f" ({s['publisher']})" if s.get("publisher") else "") + (f": {s['url']}" if s.get("url") else "")
        for s in brief["sources"]]
    return "\n".join(out) + "\n"


def offline_research_markdown(topic: str, sections: list[dict], docs: list[dict]) -> str:
    out = [f"# Research notes: {topic}", "", "_Last-resort extractive notes (Claude writer unavailable)._", ""]
    for s in sections:
        out += [f"## {s['title'] or 'Overview'}", ""] + [f"- {x}" for x in s["sentences"]] + [""]
    out += ["## Sources", ""] + [f"- {d['name']}: {d['origin']}" for d in docs]
    return "\n".join(out) + "\n"


def script_markdown(script: dict) -> str:
    scenes = []
    for sc in script["scenes"]:
        notes = [f"concept: {sc['concept']}"] if sc.get("concept") else []
        if sc.get("visual_idea"):
            notes.append(f"visual: {sc['visual_idea']}")
        if sc.get("covers"):
            notes.append(f"covers: {', '.join(sc['covers'])}")
        scenes.append({"id": sc["id"], "heading": sc["heading"], "narration": " ".join(sc["sentences"]),
                       "notes": notes})
    return render_script(script["title"], script.get("subtitle", ""), scenes)


def _target(b: dict) -> str:
    t = b.get("target", "")
    return ", ".join(t) if isinstance(t, list) else str(t)


def beat_line(b: dict) -> str:
    do, at = b["do"], b["at"]
    dur = f" over {b['dur']}s" if b.get("dur") else ""
    if do == "set":
        s = f"set {_target(b)}.{b.get('param')} → {json.dumps(b.get('to'), ensure_ascii=False)}{dur}"
    elif do == "move":
        s = f"move {_target(b)} → {b.get('to')}{dur}"
    elif do == "camera":
        s = f"camera → {b.get('region') or _target(b)}{dur}"
    elif do in ("enter", "exit"):
        s = f"{do} {_target(b)}" + (f" ({b['anim']})" if b.get("anim") else "")
    else:
        s = f"{do} {_target(b)}{dur}"
    return f"`{at}` {s}" + (f" (why: {b['why']})" if b.get("why") else "")


def plan_markdown(plan: dict, script: dict) -> str:
    st = plan.get("style", {})
    heads = {sc["id"]: sc["heading"] for sc in script["scenes"]}
    out = [f"# Visual plan: {script.get('title', '')}", "",
           f"**Style:** {st.get('mood', '')}; background {st.get('background')}, {st.get('typeface')} type, "
           f"{st.get('line', 'regular')} lines, {st.get('motion', 'measured')} motion. Palette: "
           + ", ".join(f"{k} {v}" for k, v in st.get("palette", {}).items()), ""]
    if plan.get("poster"):
        out += [f"**Poster frame:** scene `{plan['poster']['scene']}` at `{plan['poster']['at']}`", ""]
    for i, sc in enumerate(plan["scenes"], 1):
        kinds = {}
        for a in sc["actors"]:
            kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
        out += [f"## {i}. {heads.get(sc['id'], sc['id'])} (`{sc['id']}`)", "",
                f"- **Concept:** {sc['concept']}", f"- **Mechanism shown:** {sc['mechanism']}",
                f"- **Key visual cue:** {sc['visual_cue']}"]
        if sc.get("composition"):
            out.append(f"- **Composition:** {sc['composition']}")
        extra = [f"inherits `{sc['inherit']}`"] if sc.get("inherit") else []
        if sc.get("transition"):
            extra.append(f"transition {sc['transition']}")
        if extra:
            out.append(f"- **Flow:** {', '.join(extra)}")
        out.append("- **Actors:** " + (", ".join(f"{k}×{n}" if n > 1 else k for k, n in kinds.items()) or "(inherited)"))
        covers = [f"{a['covers']} (`{a['id']}`, {a['kind']})" for a in sc["actors"] if a.get("covers")]
        if covers:
            out.append("- **Required topics shown:** " + ", ".join(covers))
        out += ["- **Beats:**"] + [f"  - {beat_line(b)}" for b in sc["beats"]] + [""]
    return "\n".join(out)
