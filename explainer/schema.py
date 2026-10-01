"""Minimal JSON-Schema subset validator (no third-party dependency).

Supports: type, enum, const, required, properties, additionalProperties, items,
minItems, maxItems, minLength, maxLength, minimum, maximum, pattern, anyOf.
Returns human-readable errors with JSON paths, suitable for feeding back to a model.
"""
from __future__ import annotations

import re

_TYPES = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
    "null": lambda v: v is None,
}


def validate(value, schema: dict, path: str = "$", limit: int = 40) -> list[str]:
    errors: list[str] = []
    _check(value, schema, path, errors)
    return errors[:limit]


def _check(v, s: dict, path: str, errors: list[str]) -> None:
    if "anyOf" in s:
        branches = [validate(v, sub, path) for sub in s["anyOf"]]
        if all(branches):
            best = min(branches, key=len)
            errors.append(f"{path}: matches none of the allowed forms; closest: {best[0]}")
        return
    t = s.get("type")
    if t:
        allowed = t if isinstance(t, list) else [t]
        if not any(_TYPES[x](v) for x in allowed):
            errors.append(f"{path}: expected {' or '.join(allowed)}, got {type(v).__name__}")
            return
    if "const" in s and v != s["const"]:
        errors.append(f"{path}: must be {s['const']!r}")
    if "enum" in s and v not in s["enum"]:
        errors.append(f"{path}: {v!r} is not one of {s['enum']}")
    if isinstance(v, str):
        if len(v) < s.get("minLength", 0):
            errors.append(f"{path}: shorter than {s['minLength']} characters")
        if "maxLength" in s and len(v) > s["maxLength"]:
            errors.append(f"{path}: longer than {s['maxLength']} characters ({len(v)})")
        if "pattern" in s and not re.search(s["pattern"], v):
            errors.append(f"{path}: {v!r} does not match {s['pattern']}")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if "minimum" in s and v < s["minimum"]:
            errors.append(f"{path}: {v} is below the minimum {s['minimum']}")
        if "maximum" in s and v > s["maximum"]:
            errors.append(f"{path}: {v} is above the maximum {s['maximum']}")
    if isinstance(v, list):
        if len(v) < s.get("minItems", 0):
            errors.append(f"{path}: needs at least {s['minItems']} items (has {len(v)})")
        if "maxItems" in s and len(v) > s["maxItems"]:
            errors.append(f"{path}: allows at most {s['maxItems']} items (has {len(v)})")
        if "items" in s:
            for i, item in enumerate(v):
                _check(item, s["items"], f"{path}[{i}]", errors)
    if isinstance(v, dict):
        for k in s.get("required", []):
            if k not in v:
                errors.append(f"{path}: missing required key '{k}'")
        props = s.get("properties", {})
        extra = s.get("additionalProperties", True)
        for k, item in v.items():
            if k in props:
                _check(item, props[k], f"{path}.{k}", errors)
            elif extra is False:
                errors.append(f"{path}: unexpected key '{k}'")
            elif isinstance(extra, dict):
                _check(item, extra, f"{path}.{k}", errors)
