"""Deterministic last-resort generators, used only when the Claude writer is unavailable.

They are extractive (Wikipedia or local sources), so the result is watchable but weak; the
pipeline flags it loudly. Hand-authored topic packs in `topics/<slug>/` override them.
"""
from __future__ import annotations

import re
from collections import Counter

from .util import slugify, split_sentences

STOP = set("""a an the and or but if then than that this these those is are was were be been being of to in on
for with as by at from into about over after before under between through it its it's they them their there
which who whom whose what when where why how can could would should will may might must also such not no so
very more most many much some any each other one two three first second new used use using uses known called
has have had do does did he she his her we you your our i""".split())

ICON_WORDS = {
    "satellite": "satellite", "orbit": "satellite", "signal": "signal", "radio": "signal", "wave": "signal",
    "clock": "clock", "time": "clock", "heat": "flame", "warm": "flame", "hot": "flame", "cold": "snowflake",
    "cool": "snowflake", "ice": "snowflake", "electric": "bolt", "power": "bolt", "energy": "bolt",
    "battery": "bolt", "house": "house", "home": "house", "building": "house", "phone": "phone",
    "receiver": "phone", "device": "phone", "water": "drop", "fluid": "drop", "liquid": "drop",
    "gas": "cloud", "air": "fan", "fan": "fan", "light": "sun", "sun": "sun", "temperature": "thermometer",
    "pressure": "gauge", "motor": "gear", "engine": "gear", "machine": "gear", "data": "chip",
    "computer": "chip", "chip": "chip", "earth": "globe", "world": "globe", "position": "pin",
    "location": "pin", "map": "pin",
}


def keywords(text: str, n: int = 12) -> list[str]:
    words = re.findall(r"[a-z][a-z\-]{2,}", text.lower())
    c = Counter(w for w in words if w not in STOP)
    return [w for w, _ in c.most_common(n)]


def pick_icon(text: str, default: str = "spark") -> str:
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in ICON_WORDS:
            return ICON_WORDS[w]
        if w.endswith("s") and w[:-1] in ICON_WORDS:
            return ICON_WORDS[w[:-1]]
    return default


def extract_facts(topic: str, docs: list[dict], max_facts: int) -> list[dict]:
    topic_kw = set(keywords(topic, 6))
    all_text = " ".join(d["text"] for d in docs)
    freq = Counter(w for w in re.findall(r"[a-z][a-z\-]{2,}", all_text.lower()) if w not in STOP)
    cands = []
    for di, d in enumerate(docs):
        sents = split_sentences(re.sub(r"\n+", " ", re.sub(r"^#.*$", "", d["text"], flags=re.M)))
        for si, s in enumerate(sents):
            wc = len(s.split())
            if wc < 7 or wc > 40 or s.count("(") > 2 or re.search(r"[{}|=]{2,}", s):
                continue
            words = [w for w in re.findall(r"[a-z][a-z\-]{2,}", s.lower()) if w not in STOP]
            if not words:
                continue
            score = sum(freq[w] for w in set(words)) / (len(set(words)) ** 0.6)
            score += 6 * len(topic_kw & set(words))
            score += 4 if re.search(r"\d", s) else 0
            score *= 1.0 / (1 + 0.02 * si)
            cands.append({"doc": di, "idx": si, "text": s, "score": score})
    top = sorted(cands, key=lambda c: -c["score"])[:max_facts]
    return sorted(top, key=lambda c: (c["doc"], c["idx"]))


def research_markdown(topic: str, facts: list[dict], docs: list[dict]) -> str:
    kw = keywords(" ".join(f["text"] for f in facts), 10)
    out = [f"# Research notes: {topic}", "", "_Generated offline by extractive summarization._", "",
           "## Key terms", "", ", ".join(kw), "", "## Key facts", ""]
    out += [f"- {f['text']} [{docs[f['doc']]['name']}]" for f in facts]
    out += ["", "## Sources", ""] + [f"- {d['name']}: {d['origin']}" for d in docs]
    return "\n".join(out) + "\n"


SKIP_SECTION = re.compile(
    r"histor|etymolog|origin|background|timeline|cultur|societ|politic|regulat|econom|market|industr|legal|\blaws?\b|"
    r"countr|region|nation|europe|asia|africa|america|australia|oceania|china|india|japan|russia|britain|canada|"
    r"see also|reference|notes|further|external|gallery|trivia|record|notable|people|compan|future|research|"
    r"criticism|controvers|terminolog|popular|media|statistic|list of|awards|bibliograph", re.I)
MECH_SECTION = re.compile(
    r"how|operat|principle|work|design|component|structure|process|function|mechanism|generat|transmi|distribut|"
    r"type|control|stabil|frequen|safety|fail|outage|balanc|storage|applicat|overview|basic|theory|physic|cycle|"
    r"part|layout|system|method|step|stage|configur|technolog|measure", re.I)
DANGLING = re.compile(
    r"^(it|this|these|those|they|them|he|she|his|her|its|their|such|both|however|also|additionally|in addition|"
    r"furthermore|moreover|therefore|thus|then|later|another|other|the latter|the former|as a result|"
    r"for this reason|because of this|similarly|likewise|meanwhile|here|there|so|but|and|or|in contrast)\b", re.I)
YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)s?\b")
_WIKI_HEAD = re.compile(r"^\s*(={2,6})\s*(.*?)\s*\1\s*$")
_MD_HEAD = re.compile(r"^\s*#{1,6}\s+(.*)$")


def doc_sections(text: str) -> list[tuple[str, int, str]]:
    """Split a document into (title, depth, body); the lead before any heading has title ''."""
    out, title, depth, buf = [], "", 0, []
    for line in text.splitlines():
        m = _WIKI_HEAD.match(line)
        md = None if m else _MD_HEAD.match(line)
        if m or md:
            out.append((title, depth, " ".join(buf)))
            title = (m.group(2) if m else md.group(1)).strip()
            depth = len(m.group(1)) - 1 if m else len(line) - len(line.lstrip("#"))
            buf = []
        elif line.strip():
            buf.append(line.strip())
    out.append((title, depth, " ".join(buf)))
    return [(t, d, b) for t, d, b in out if b.strip()]


def teaching_sentences(body: str, limit: int) -> list[str]:
    picked = []
    for s in split_sentences(re.sub(r"\s*\([^)]{0,120}\)", "", body)):
        wc = len(s.split())
        if not 8 <= wc <= 32 or DANGLING.match(s) or len(YEAR.findall(s)) > 0:
            continue
        if re.search(r"[{}|=\[\]]|\bcitation\b|\bsee below\b|\bfigure\b|\bshown\b", s, re.I):
            continue
        if not s.endswith((".", "!", "?")):
            continue
        picked.append(s)
        if len(picked) >= limit:
            break
    return picked


def teaching_sections(docs: list[dict], max_sections: int = 6) -> list[dict]:
    """Mechanism-focused sections with clean, self-contained sentences, in document order."""
    cands = []
    skip_depth = None
    for di, d in enumerate(docs):
        for si, (title, depth, body) in enumerate(doc_sections(d["text"])):
            if skip_depth is not None and depth > skip_depth:
                continue
            skip_depth = None
            if title and SKIP_SECTION.search(title):
                skip_depth = depth
                continue
            sents = teaching_sentences(body, 4 if title else 3)
            if len(sents) < (1 if not title else 2):
                continue
            score = (5 if not title else 0) + (4 if MECH_SECTION.search(title) else 0) + min(len(sents), 4)
            cands.append({"doc": di, "idx": si, "title": title, "sentences": sents, "score": score})
    lead = [c for c in cands if not c["title"]][:1]
    body = sorted([c for c in cands if c["title"]], key=lambda c: -c["score"])[:max_sections]
    return [{"title": c["title"], "sentences": c["sentences"]}
            for c in lead + sorted(body, key=lambda c: (c["doc"], c["idx"]))]


def teaching_script(topic: str, sections: list[dict], target_words: int) -> dict:
    """A structured last-resort script: opening, one scene per mechanism section, a closing that ties them."""
    subject = _subject(topic)
    lead = next((s for s in sections if not s["title"]), None)
    parts = [s for s in sections if s["title"]]
    opening = [f"What is really going on when we talk about {subject}?"]
    opening += (lead["sentences"][:2] if lead else [])
    opening.append("Let's take it one piece at a time.")
    scenes = [{"id": "opening", "heading": _title_case(topic), "sentences": opening,
               "concept": f"What {subject} is", "visual_idea": ""}]
    budget = target_words - sum(len(s.split()) for s in opening) - 30
    used, seen = 0, {"opening", "closing"}
    for sec in parts:
        sents = []
        for s in sec["sentences"]:
            if used + len(s.split()) > budget:
                break
            sents.append(s)
            used += len(s.split())
        if not sents:
            continue
        heading = " ".join(re.sub(r"[^\w\s-]", "", sec["title"]).split()[:5]).strip() or f"Part {len(scenes)}"
        sid = slugify(heading)[:40] or f"part-{len(scenes)}"
        while sid in seen:
            sid = f"{sid[:36]}-{len(scenes)}"
        seen.add(sid)
        scenes.append({"id": sid, "heading": _title_case(heading), "sentences": sents, "concept": heading,
                       "visual_idea": ""})
    names = [sc["heading"].lower() for sc in scenes[1:]][:4]
    if len(names) >= 2:
        close = [f"So {subject} comes down to {', '.join(names[:-1])} and {names[-1]}, each one depending on the last."]
    else:
        close = [f"And that is the core of how {subject} works."]
    scenes.append({"id": "closing", "heading": "Putting It Together", "sentences": close,
                   "concept": "How the pieces connect", "visual_idea": ""})
    return {"title": _title_case(topic), "subtitle": "", "logline": f"How {subject} works", "scenes": scenes}


def _title_case(topic: str) -> str:
    small = {"a", "an", "the", "of", "and", "or", "in", "on", "to", "for"}
    words = topic.strip().rstrip("?").split()
    return " ".join(w if w.isupper() else (w.capitalize() if i == 0 or w.lower() not in small else w.lower())
                    for i, w in enumerate(words))


def _subject(topic: str) -> str:
    s = re.sub(r"^(how|what|why)\s+(does|do|is|are)?\s*", "", topic.strip().rstrip("?"), flags=re.I)
    return re.sub(r"\s+(works?)$", "", s, flags=re.I) or topic


FALLBACK_STYLE = {"palette": {"bg": "#10131C", "surface": "#1A2030", "ink": "#E8ECF4", "muted": "#8A93A8",
                              "accent": "#5CC8FF", "accent2": "#FFB454", "warn": "#FF6B6B", "good": "#5BD69A"},
                  "background": "dots", "typeface": "geometric", "line": "regular", "motion": "calm",
                  "mood": "neutral fallback style"}


def plan_from_script(script: dict) -> dict:
    """A minimal valid plan (key phrases revealed per sentence, slow push-in) for the fallback path."""
    scenes = []
    for sc in script["scenes"]:
        actors = [{"id": "heading", "kind": "text", "at": [800, 140],
                   "params": {"text": " ".join(sc["heading"].split()[:8]), "size": "xl", "weight": "bold"}}]
        beats = [{"at": "start", "do": "enter", "target": "heading", "anim": "fade"}]
        for i, s in enumerate(sc["sentences"][:4], 1):
            actors.append({"id": f"point{i}", "kind": "text", "at": [800, 230 + 120 * i],
                           "params": {"text": _short_phrase(s, 7), "size": "m"}})
            beats.append({"at": f"s{i}", "do": "enter", "target": f"point{i}", "anim": "slide_up"})
        beats.append({"at": "start", "do": "camera", "region": [80, 45, 1440, 810], "dur": 8, "ease": "smooth"})
        scenes.append({"id": sc["id"], "concept": sc.get("concept") or sc["heading"],
                       "mechanism": "none (fallback plan)", "visual_cue": "key phrases", "actors": actors,
                       "beats": beats, "transition": "fade"})
    return {"style": FALLBACK_STYLE, "scenes": scenes}


def _short_phrase(sentence: str, max_words: int = 7) -> str:
    s = re.split(r"[,;:—–(]| which | because | so that ", sentence)[0].strip().rstrip(".")
    words = s.split()
    if len(words) > max_words:
        words = words[:max_words]
        while words and words[-1].lower() in STOP:
            words.pop()
    return " ".join(words)


_NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(%|percent|km|kilometers|meters|miles|degrees|°C|°F|"
                  r"kW|watts|volts|times|years|seconds|milliseconds|microseconds|hours|days)?", re.I)


def shots_from_script(script: dict) -> dict:
    scenes = []
    n = len(script["scenes"])
    for i, sc in enumerate(script["scenes"]):
        sents = sc["sentences"]
        text = sc["narration"]
        if i == 0:
            scenes.append({"id": sc["id"], "template": "title", "title": script["title"],
                           "subtitle": script.get("subtitle", ""), "icon": pick_icon(script["title"], "spark")})
            continue
        if i == n - 1:
            chips = [k.capitalize() for k in keywords(" ".join(s["narration"] for s in script["scenes"]), 4)]
            scenes.append({"id": sc["id"], "template": "recap", "heading": sc["heading"], "items": chips})
            continue
        m = _NUM.search(text)
        if m and m.group(2) and i % 2 == 0:
            si = next((k for k, s in enumerate(sents) if m.group(0) in s), 0)
            scenes.append({"id": sc["id"], "template": "stat", "heading": sc["heading"], "value": m.group(1),
                           "unit": m.group(2), "label": _short_phrase(sents[si], 9), "at": f"s{si + 1}",
                           "icon": pick_icon(text)})
        elif len(sents) >= 3 and i % 3 == 1:
            steps = [{"title": _short_phrase(s, 4), "icon": pick_icon(s), "at": f"s{k + 1}"}
                     for k, s in enumerate(sents[:4])]
            scenes.append({"id": sc["id"], "template": "steps", "heading": sc["heading"], "steps": steps})
        else:
            items = [{"text": _short_phrase(s), "at": f"s{k + 1}", "icon": pick_icon(s)}
                     for k, s in enumerate(sents[:4])]
            scenes.append({"id": sc["id"], "template": "bullets", "heading": sc["heading"], "items": items,
                           "icon": pick_icon(text)})
    return {"scenes": scenes}
