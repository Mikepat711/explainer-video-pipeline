"""JSON schemas for the three writer tasks: research brief, script, visual plan."""
from __future__ import annotations

from .vocab import ACTIONS, COLOR_ROLES, EASES, ENTER_ANIMS, EXIT_ANIMS, KINDS, STYLE_BACKGROUNDS, TRANSITIONS, TYPEFACES

STR = {"type": "string", "minLength": 1}
ID = {"type": "string", "pattern": r"^[a-z0-9][a-z0-9-]{0,39}$"}
HEX = {"type": "string", "pattern": r"^#[0-9A-Fa-f]{6}$"}
TIME = {"type": ["string", "number"]}
POINT = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
REGION = {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}


def strs(min_items=0, max_items=40, **item):
    return {"type": "array", "items": dict(STR, **item), "minItems": min_items, "maxItems": max_items}


RESEARCH = {
    "type": "object",
    "required": ["topic", "audience", "core_question", "short_answer", "key_concepts", "process", "numbers",
                 "misconceptions", "sources"],
    "properties": {
        "topic": STR, "audience": STR, "core_question": STR, "short_answer": STR,
        "key_concepts": {"type": "array", "minItems": 3, "maxItems": 14, "items": {
            "type": "object", "required": ["name", "explanation", "mechanism"],
            "properties": {"name": STR, "explanation": STR, "mechanism": STR, "visual_metaphor": {"type": "string"}}}},
        "process": {"type": "array", "minItems": 2, "maxItems": 16, "items": {
            "type": "object", "required": ["step", "detail"], "properties": {"step": STR, "detail": STR}}},
        "numbers": {"type": "array", "maxItems": 30, "items": {
            "type": "object", "required": ["fact", "value"],
            "properties": {"fact": STR, "value": STR, "unit": {"type": "string"}, "context": {"type": "string"},
                           "source": {"type": "string"}}}},
        "misconceptions": {"type": "array", "maxItems": 10, "items": {
            "type": "object", "required": ["myth", "truth"], "properties": {"myth": STR, "truth": STR}}},
        "analogies": strs(max_items=10),
        "required_topics": {"type": "array", "maxItems": 12, "items": {
            "type": "object", "required": ["id", "explanation", "mechanism", "visual"],
            "properties": {"id": ID, "explanation": STR, "mechanism": STR, "visual": STR,
                           "numbers": strs(max_items=6)}}},
        "sources": {"type": "array", "minItems": 1, "maxItems": 20, "items": {
            "type": "object", "required": ["title"],
            "properties": {"title": STR, "publisher": {"type": "string"}, "url": {"type": "string"}}}},
    },
}

SCRIPT = {
    "type": "object",
    "required": ["title", "subtitle", "logline", "scenes"],
    "properties": {
        "title": dict(STR, maxLength=70), "subtitle": dict(STR, maxLength=90), "logline": STR,
        "scenes": {"type": "array", "minItems": 3, "maxItems": 18, "items": {
            "type": "object", "required": ["id", "heading", "concept", "sentences", "visual_idea"],
            "additionalProperties": False,
            "properties": {
                "id": ID, "heading": dict(STR, maxLength=48), "concept": STR,
                "sentences": strs(1, 12, maxLength=220),
                "visual_idea": STR, "key_terms": strs(max_items=8, maxLength=40),
                "covers": {"type": "array", "items": ID, "maxItems": 6}}}},
    },
}

ACTOR = {
    "type": "object", "required": ["id", "kind"], "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": r"^[a-z][a-z0-9_]{0,31}$"},
        "kind": {"type": "string", "enum": sorted(KINDS)},
        "at": POINT, "scale": {"type": "number", "minimum": 0.05, "maximum": 8},
        "rotate": {"type": "number", "minimum": -360, "maximum": 360},
        "opacity": {"type": "number", "minimum": 0, "maximum": 1},
        "z": {"type": "integer", "minimum": -10, "maximum": 10},
        "visible": {"type": "boolean"},
        "params": {"type": "object"},
        "note": {"type": "string"},
        "covers": ID,
    },
}

BEAT = {
    "type": "object", "required": ["at", "do"], "additionalProperties": False,
    "properties": {
        "at": TIME, "do": {"type": "string", "enum": sorted(ACTIONS)},
        "target": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}, "minItems": 1}]},
        "param": {"type": "string"}, "to": {}, "dur": {"type": "number", "minimum": 0, "maximum": 30},
        "ease": {"type": "string", "enum": list(EASES)},
        "anim": {"type": "string", "enum": sorted(set(ENTER_ANIMS) | set(EXIT_ANIMS))},
        "region": REGION, "repeat": {"type": "integer", "minimum": 1, "maximum": 8},
        "curve": {"type": "number", "minimum": -1, "maximum": 1}, "color": {"type": "string"},
        "why": {"type": "string"},
    },
}

PLAN = {
    "type": "object",
    "required": ["style", "scenes"],
    "properties": {
        "style": {
            "type": "object", "required": ["palette", "background", "typeface", "mood"], "additionalProperties": False,
            "properties": {
                "palette": {"type": "object", "required": ["bg", "ink", "accent"],
                            "properties": {r: HEX for r in COLOR_ROLES}, "additionalProperties": False},
                "background": {"type": "string", "enum": list(STYLE_BACKGROUNDS)},
                "typeface": {"type": "string", "enum": list(TYPEFACES)},
                "line": {"type": "string", "enum": ["thin", "regular", "bold"]},
                "corners": {"type": "string", "enum": ["sharp", "soft", "round"]},
                "motion": {"type": "string", "enum": ["calm", "measured", "lively"]},
                "mood": STR}},
        "poster": {"type": "object", "required": ["scene", "at"], "properties": {"scene": ID, "at": TIME}},
        "scenes": {"type": "array", "minItems": 1, "maxItems": 18, "items": {
            "type": "object", "required": ["id", "concept", "mechanism", "visual_cue", "actors", "beats"],
            "additionalProperties": False,
            "properties": {
                "id": ID, "concept": STR, "mechanism": STR, "visual_cue": STR,
                "composition": {"type": "string", "maxLength": 160},
                "inherit": ID, "transition": {"type": "string", "enum": list(TRANSITIONS)},
                "camera": REGION, "portrait_focus": REGION,
                "background": {"type": "string", "enum": list(STYLE_BACKGROUNDS) + ["none"]},
                "hold": {"type": "number", "minimum": 0, "maximum": 6},
                "actors": {"type": "array", "maxItems": 48, "items": ACTOR},
                "beats": {"type": "array", "minItems": 1, "maxItems": 80, "items": BEAT}}}},
    },
}
