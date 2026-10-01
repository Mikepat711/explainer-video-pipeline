"""Spoken-form text normalization for TTS: numbers, units, symbols and acronyms.

TTS models read digits and symbols inconsistently ("60 Hz" as "sixty H Z", "400,000" digit by digit,
"Δt" not at all), which is a large part of what makes narration sound odd. Everything a narrator would
say differently from how it is written is expanded here, before any engine sees the text.
"""
from __future__ import annotations

import re

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
         "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_SCALES = [(10 ** 12, "trillion"), (10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")]
_ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
        "twelve": "twelfth"}


def int_words(n: int) -> str:
    if n < 0:
        return "minus " + int_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")
    if n < 1000:
        rest = n % 100
        return _ONES[n // 100] + " hundred" + (" " + int_words(rest) if rest else "")
    for value, name in _SCALES:
        if n >= value:
            head, rest = divmod(n, value)
            return int_words(head) + " " + name + (" " + int_words(rest) if rest else "")
    return str(n)


def year_words(n: int) -> str:
    if 2000 <= n <= 2009:
        return int_words(n)
    hi, lo = divmod(n, 100)
    return int_words(hi) + (" hundred" if lo == 0 else (" oh " + _ONES[lo] if lo < 10 else " " + int_words(lo)))


def number_words(tok: str) -> str:
    """'400,000' -> 'four hundred thousand', '0.067' -> 'zero point zero six seven', '1.5' -> 'one point five'."""
    neg = tok.startswith(("-", "−"))
    tok = tok.lstrip("-−").replace(",", "")
    if "." in tok:
        whole, frac = tok.split(".", 1)
        out = int_words(int(whole or 0)) + " point " + " ".join(_ONES[int(d)] for d in frac)
    else:
        out = int_words(int(tok))
    return ("minus " if neg else "") + out


def ordinal_words(n: int) -> str:
    w = int_words(n)
    last = re.split(r"[ -]", w)[-1]
    if last in _ORD:
        return w[: -len(last)] + _ORD[last]
    if last.endswith("y"):
        return w[:-1] + "ieth"
    return w + "th"


UNITS = {
    "Hz": ("hertz", "hertz"), "kHz": ("kilohertz", "kilohertz"), "MHz": ("megahertz", "megahertz"),
    "GHz": ("gigahertz", "gigahertz"), "V": ("volt", "volts"), "kV": ("kilovolt", "kilovolts"),
    "MV": ("megavolt", "megavolts"), "A": ("amp", "amps"), "mA": ("milliamp", "milliamps"),
    "kA": ("kiloamp", "kiloamps"), "W": ("watt", "watts"), "kW": ("kilowatt", "kilowatts"),
    "MW": ("megawatt", "megawatts"), "GW": ("gigawatt", "gigawatts"), "TW": ("terawatt", "terawatts"),
    "Wh": ("watt-hour", "watt-hours"), "kWh": ("kilowatt-hour", "kilowatt-hours"),
    "MWh": ("megawatt-hour", "megawatt-hours"), "GWh": ("gigawatt-hour", "gigawatt-hours"),
    "TWh": ("terawatt-hour", "terawatt-hours"), "km": ("kilometer", "kilometers"), "m": ("meter", "meters"),
    "cm": ("centimeter", "centimeters"), "mm": ("millimeter", "millimeters"), "kg": ("kilogram", "kilograms"),
    "g": ("gram", "grams"), "s": ("second", "seconds"), "ms": ("millisecond", "milliseconds"),
    "µs": ("microsecond", "microseconds"), "us": ("microsecond", "microseconds"), "ns": ("nanosecond", "nanoseconds"),
    "rpm": ("r p m", "r p m"), "mph": ("mile per hour", "miles per hour"), "km/h": ("kilometer per hour",
                                                                                "kilometers per hour"),
    "°C": ("degree Celsius", "degrees Celsius"), "°F": ("degree Fahrenheit", "degrees Fahrenheit"),
    "%": ("percent", "percent"), "Ω": ("ohm", "ohms"), "N·m": ("newton meter", "newton meters"),
    "Nm": ("newton meter", "newton meters"),
}
_UNIT_RE = "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
_NUM = r"[-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
# After these words a unit is a quantity ("400 kV of power"); before any other word it is an adjective
# ("a 765 kV line" -> "seven hundred sixty-five kilovolt line").
_PLURAL_NEXT = {"of", "and", "or", "to", "in", "at", "per", "is", "are", "was", "were", "for", "from", "on", "into",
                "through", "with", "by", "the", "a", "an", "that", "which", "each", "every", "means", "away",
                "above", "below", "up", "down", "higher", "lower", "more", "less", "than", "apart", "long", "wide",
                "tall", "high", "deep", "later", "earlier", "ago", "before", "after", "it", "its", "as"}

SYMBOLS = [
    (r"\s*≈\s*", " about "), (r"~(?=\s*\d)", "about "), (r"\s*±\s*", " plus or minus "), (r"\s*×\s*", " times "),
    (r"\s*→\s*", " to "), (r"\s*&\s*", " and "), (r"Δ\s?t\b", "delta t"), (r"Δ", "change in "),
    (r"\s*=\s*", " equals "), (r"\s*\+\s*(?=\w)", " plus "), (r"°(?![CF])", " degrees"),
]


def _unit(m: re.Match) -> str:
    num, unit, nxt = m.group(1), m.group(2), (m.group(3) or "").lower()
    singular = num in ("1", "1.0") or (nxt.isalpha() and nxt not in _PLURAL_NEXT and unit != "%")
    return f"{num} {UNITS[unit][0 if singular else 1]}"
DEFAULT_ACRONYMS = {"GPS": "G.P.S.", "COP": "C.O.P.", "AC": "A.C.", "DC": "D.C.", "HVDC": "H.V.D.C.",
                    "LED": "L.E.D.", "CPU": "C.P.U.", "USB": "U.S.B.", "EV": "E.V."}


def normalize(text: str, acronyms: dict[str, str] | None = None) -> str:
    acr = dict(DEFAULT_ACRONYMS, **(acronyms or {}))
    t = re.sub(r"\s*—\s*", ", ", text).replace("…", "...")
    t = re.sub(r"\b(1[5-9]\d0|20\d0)s\b", lambda m: re.sub(r"y$", "ie", year_words(int(m.group(1)))) + "s", t)
    t = re.sub(r"\b(in|since|by|from|until|of) (1[5-9]\d\d|20\d\d)\b",
               lambda m: m.group(1) + " " + year_words(int(m.group(2))), t, flags=re.I)
    t = re.sub(r"(\d)\s?[–-]\s?(\d)", r"\1 to \2", t)
    t = re.sub(rf"({_NUM})[\s-]?({_UNIT_RE})(?![\w/])(?:\s+([A-Za-z]+))?",
               lambda m: _unit(m) + (" " + m.group(3) if m.group(3) else ""), t)
    for pat, rep in SYMBOLS:
        t = re.sub(pat, rep, t)
    t = re.sub(r"\b(\d+)(st|nd|rd|th)\b", lambda m: ordinal_words(int(m.group(1))), t)
    t = re.sub(_NUM, lambda m: number_words(m.group(0)), t)
    for k, v in acr.items():
        t = re.sub(rf"\b{re.escape(k)}\b", v, t)
    return re.sub(r"\s{2,}", " ", t).strip()
