"""Prompts for the Claude writer. Each starts with a `TASK:` line and embeds its JSON schema."""
from __future__ import annotations

import json

from .schemas import PLAN, RESEARCH, SCRIPT
from .vocab import CAPTION_TOP, DESIGN_H, DESIGN_W, describe


def _schema(s: dict) -> str:
    return json.dumps(s, separators=(",", ":"))


RULES_OUTPUT = ("Reply with ONE JSON document and nothing else: no prose before or after it, no markdown "
                "fences. It must validate against the JSON Schema given below.")

REQUIRE_RESEARCH = ("REQUIRED TOPICS. The producer requires the lesson to cover every topic below. Research each one "
                    "as carefully as the core mechanism (what physically happens and in what order, what moves or "
                    "changes on screen, one or two numbers with sources) and report it in \"required_topics\" under "
                    "the same id; weave the facts into key_concepts, process and numbers too:")
REQUIRE_SCRIPT = ("REQUIRED TOPICS (non-negotiable; the validator rejects a script that skips one). Teach each topic "
                  "below in a scene of its own or a clearly separate part of a scene, list its id in that scene's "
                  "\"covers\", and give it a visual_idea of its own that shows its mechanism (two topics never share "
                  "one picture). Fit them into the story so each builds on what came before:")
REQUIRE_PLAN = ("REQUIRED TOPICS (the validator rejects the plan unless each one has its own dedicated visual). For "
                "every id below, at least one actor that is not text (not text, label, meter, badge, dimension or "
                "compare) must carry \"covers\": \"<id>\" and be the target of a set, move or trace beat that shows "
                "its mechanism. \"covers\" holds a single id, so every topic gets a distinct visual of its own:")


def brief_block(brief, intro: str) -> str:
    if not brief:
        return ""
    out = []
    if brief.require:
        out += [intro] + [f"- {r['id']}: {r['text']}" for r in brief.require]
    if brief.notes:
        out += ["", "Producer's notes (follow them):", brief.notes]
    return "\n\n" + "\n".join(out)


def research_prompt(topic: str, local_sources: list[dict], brief=None) -> str:
    extra = ""
    if local_sources:
        docs = "\n\n".join(f"### {d['name']} ({d['origin']})\n{d['text'][:8000]}" for d in local_sources)
        extra = f"\n\nReference material supplied with the topic (treat as reliable, cite it by name):\n{docs}"
    extra = brief_block(brief, REQUIRE_RESEARCH) + extra
    return f"""TASK: research
You are the researcher for a short animated lesson in a series of visual explainers for curious adults.

Topic: {topic}

Research how it actually works. Use web search if it is available to check facts and current numbers;
prefer engineering references, standards bodies, government agencies, universities, operators and textbooks.
Focus on mechanism and causality: what physically happens, in what order, and why. Skip history, trivia,
company names and regional politics unless they are essential to understanding the mechanism.
For every key concept say what moves or changes (that becomes an animation) and suggest a visual metaphor.
Include the handful of numbers that make it concrete (with units and a source) and the misconceptions a
learner is likely to hold.{extra}

{RULES_OUTPUT}
JSON Schema:
{_schema(RESEARCH)}
"""


def script_prompt(topic: str, research: dict, words: tuple[int, int, int], seconds: int, brief=None) -> str:
    target, lo, hi = words
    return f"""TASK: script
You are the writer and teacher for an animated explainer lesson. Write the narration and, for every
scene, the idea for a purpose-built teaching animation.

Topic: {topic}
Length: about {target} words of narration (acceptable {lo}-{hi}), roughly {seconds} seconds when spoken at a
calm, relaxed conversational pace (~150 words per minute, with a short pause after every sentence).

Structure is yours to design for THIS topic. Choose the number of scenes (each scene teaches one idea),
how the lesson opens (a concrete moment, a question, a surprising number; never a generic welcome or a
title card) and how it ends (an insight or consequence, not a list of the scene headings). Build understanding
step by step: each scene should depend on the one before.

Narration rules (it is read aloud by a TTS narrator; write for the ear, not the page):
- Audience: curious viewers with NO prior knowledge. Warm, calm, conversational; contractions are welcome.
- Short sentences, ONE idea per sentence: most 5-15 words, none over 22. A pause follows every sentence, so
  each sentence break is a breath. Split anything with stacked clauses into separate sentences.
- No crammed lists. Never stack three or more items, names or numbers in one breath; give each its own
  sentence or a gentle "first ... then ..." rhythm. No colons, semicolons, dashes or parentheses in narration.
- Explain with plain everyday analogies (an auction, a referee, traffic) before any technical detail.
- Define each piece of jargon in plain words the first time it appears, or drop it. Spell out an acronym
  before using it ("independent system operators, or ISOs").
- Fewer numbers: keep only the ones that teach something; the animation and labels can show the rest.
- Write money, units and symbols as spoken words in narration: "sixty dollars", "five hundred megawatts",
  "ten percent", "sixty hertz", "about thirty", "April first, nineteen ninety-seven". On-screen labels
  (key_terms, visual_idea) keep the compact symbols ("$60", "500 MW", "60 Hz").
- If the lesson is part of a series, announce the part as its own short sentence ("This is Part 3.") and
  start the hook in the next sentence.
- Every item in "sentences" is exactly ONE sentence (they are the sync points for the animation).
- No "in this video", no calls to subscribe, no headings or lists read aloud, no rhetorical filler.
- Teach the mechanism. When you name a part, say what it does and why it matters.
- Keep magnitudes honest. If one small cause stands in for a big effect (one kettle and the grid's frequency),
  say how small the real effect is, or use a cause big enough to produce it (a whole city switching on).

For each scene:
- "concept": the one idea the viewer should walk away with.
- "visual_idea": the animation that teaches it, in 1-3 sentences: what is on screen, what moves or changes,
  and how that motion shows the mechanism (e.g. "the frequency needle sags from 60.00 toward 59.95 Hz as the
  city's demand bar jumps, then recovers as the gas plant's output rises"). Text on screen is not a visual idea.
- "key_terms": the few words worth labelling on screen.
- "covers": the ids of the required topics this scene teaches (omit it when there are none).{brief_block(brief, REQUIRE_SCRIPT)}

Research brief:
{json.dumps(research, ensure_ascii=False, indent=1)}

{RULES_OUTPUT}
JSON Schema:
{_schema(SCRIPT)}
"""


def plan_prompt(topic: str, script: dict, research: dict, captions: bool, aspect: str, brief=None) -> str:
    listing = []
    for sc in script["scenes"]:
        covers = f" | covers: {', '.join(sc['covers'])}" if sc.get("covers") else ""
        listing.append(f"[{sc['id']}] {sc['heading']}{covers} | concept: {sc['concept']}\n"
                       f"  visual idea: {sc['visual_idea']}")
        listing += [f"  s{i}: {s}" for i, s in enumerate(sc["sentences"], 1)]
    caption_rule = (f"Burned-in captions occupy y > {CAPTION_TOP}: keep text and important parts above that line."
                    if captions else "There are no burned-in captions; the full height is available.")
    covers_rule = ('An actor\'s optional "covers" names one required topic id from the list below and nothing else.'
                   if brief and brief.require else 'Leave out "covers": this lesson has no required topics.')
    return f"""TASK: plan
You are the motion designer and teacher. Turn the script below into a visual plan that the animation
engine renders directly. Every key idea gets a purpose-built animated visual that explains the mechanism
(current flowing, coils stepping voltage, a needle dipping as load rises), never decorative motion or
paragraphs of on-screen text.

Topic: {topic}

How the engine works:
- Each scene is a stage in a {DESIGN_W}x{DESIGN_H} design space (origin top-left, y down). Final video: {aspect}
  (for 9:16 the engine crops to `portrait_focus` or the camera region, so keep a scene's key action compact).
- "actors" are drawn from the vocabulary below; each has an id, a kind, a position "at" [x, y] (its center),
  optional scale/rotate/opacity/z, and kind-specific "params". Actors are visible from the start of the scene
  unless an "enter" beat reveals them later.
- "beats" are timed actions. "at" is a sync point: s2 = when sentence 2 starts, e2 = when it ends, s2+0.6 =
  0.6 s after it starts, start, end-1.0, or seconds from the scene start. Sync every reveal and every change
  to the sentence that talks about it.
- Actions: enter, exit, set (animate a parameter: numbers tween smoothly over "dur", enums/text switch),
  move (to [x, y]), pulse (emphasis), trace (one bright pulse along a path/powerline/edge), camera (glide to a
  region [x, y, w, h] or frame a target: zoom into a detail, pan along a journey).
- References ("target", "from", "to", "along", "around") use an actor id, "id.anchor", or [x, y]. A network's
  parts are "net.nodeid" and edges "net.a-b".
- "inherit": "<earlier scene id>" starts a scene from that scene's final actors, so a diagram can build up
  across scenes, and "transition": "continue" makes it one continuous shot (great for following energy along a
  journey with camera moves). Otherwise pick a transition that suits the cut.
- "hold" adds seconds after the narration when an animation needs time to finish or sink in.
- "poster": pick the single most telling frame (scene id and time) for the thumbnail.

Design rules:
- Each scene needs at least one mechanism beat (set, move, trace or camera) that shows HOW something works.
  Prefer instruments the viewer can read (gauges, meters, live charts, balance) over adjectives.
- Composition, layout and visual language are yours: vary them scene to scene (cutaway, schematic map,
  close-up, side-by-side comparison, chart, step-by-step build) as the ideas demand. No fixed title card, no
  template layouts, no recurring header bar unless it serves this lesson.
- Pick a style that fits this topic (palette with good contrast, background, typeface, line weight, motion).
- On-screen text is for labels, values and the occasional key phrase: at most ~6 words per label and about
  30 words per scene in total. Numbers and units belong in meters, gauges and dimensions.
- {caption_rule}
- Honest scale: whenever a visual magnifies an effect so it can be seen (one appliance visibly moving the grid's
  frequency or a plant's output, an atom drawn huge, a slow process sped up), put a short on-screen label on it
  such as "exaggerated for illustration" or "not to scale", or show a cause large enough to produce the effect.
  Set such notes as legibly as any other label: text size "s" or larger (never "xs"), clear of other parts.
- Use only the kinds, params, anchors and actions listed. Animate only the params marked animatable (plus
  opacity, scale and rotate on any actor).

Hard limits (the validator rejects the whole plan for any of these, and a retry costs minutes):
- Enum values are exhaustive: use exactly one of the listed words (e.g. network node kind is one of
  generic|plant|substation|city|house|factory|battery|hub|switch|load). No other params or fields exist.
- "str≤Nch" is a character cap (a badge holds at most 6 characters); "text≤Nw" is a word cap.
- Numbers stay inside the listed ranges; "int" means a whole number.
- Actor ids match ^[a-z][a-z0-9_]{{0,31}}$ (lower case, digits, underscore); scene ids are copied from the script.
- At most 48 actors and 80 beats per scene; text-bearing actors (text, label, meter, badge, dimension,
  compare) keep y < {CAPTION_TOP} when captions are on; a "set" names one animatable param and a "to" value.
- {covers_rule}{brief_block(brief, REQUIRE_PLAN)}

Vocabulary:
{describe()}

Script (scene ids and numbered sentences are fixed; the plan must have exactly these scenes in this order):
{chr(10).join(listing)}

Key numbers from the research (use them for meters, gauges and labels):
{json.dumps(research.get("numbers", [])[:20], ensure_ascii=False)}

{RULES_OUTPUT}
JSON Schema:
{_schema(PLAN)}
"""
