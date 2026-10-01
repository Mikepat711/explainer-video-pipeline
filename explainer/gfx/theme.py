from __future__ import annotations

import functools
import subprocess


def hex_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


PALETTES = {
    "midnight": {
        "bg0": "#070B18", "bg1": "#101a36", "grid": "#1d2a4d", "panel": "#131d3b", "panel_hi": "#1b2850",
        "stroke": "#2b3a66", "text": "#F1F5FF", "muted": "#93A1C4", "dim": "#5b6a91",
    },
    "paper": {
        "bg0": "#F7F5F0", "bg1": "#ECE8DF", "grid": "#d9d3c5", "panel": "#FFFFFF", "panel_hi": "#F2EFE8",
        "stroke": "#cfc8b8", "text": "#15171C", "muted": "#5a5f6b", "dim": "#9aa0ab",
    },
}

ACCENTS = {
    "cyan": "#38BDF8", "violet": "#A78BFA", "amber": "#FBBF24", "mint": "#34D399", "coral": "#FB7185",
}

SEMANTIC = {
    "hot": "#FB7185", "warm": "#FB923C", "cold": "#38BDF8", "cool": "#7DD3FC", "good": "#34D399",
    "warn": "#FBBF24", "violet": "#A78BFA", "amber": "#FBBF24", "mint": "#34D399", "cyan": "#38BDF8",
    "coral": "#FB7185", "white": "#F1F5FF",
}


@functools.lru_cache(maxsize=None)
def _families() -> str:
    try:
        return subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return ""


class Theme:
    def __init__(self, style: dict):
        self.name = style.get("theme", "midnight")
        pal = PALETTES.get(self.name, PALETTES["midnight"])
        self.c = {k: hex_rgb(v) for k, v in pal.items()}
        self.accent = hex_rgb(ACCENTS.get(style.get("accent", "cyan"), style.get("accent", "#38BDF8"))
                              if not str(style.get("accent", "")).startswith("#") else style["accent"])
        self.grid = bool(style.get("grid", True))
        self.progress_bar = bool(style.get("progress_bar", True))
        want = style.get("font", "Inter")
        fams = _families()
        self.family = want if want in fams else "DejaVu Sans"
        self.has_weights = self.family == "Inter" and "Inter SemiBold" in fams

    def color(self, name) -> tuple[float, float, float]:
        if name is None:
            return self.accent
        if isinstance(name, (list, tuple)):
            return tuple(name)
        if name == "accent":
            return self.accent
        if name in self.c:
            return self.c[name]
        if name in SEMANTIC:
            return hex_rgb(SEMANTIC[name])
        if str(name).startswith("#"):
            return hex_rgb(name)
        return self.accent

    def face(self, weight: str) -> tuple[str, bool]:
        """Returns (family, bold) for the cairo toy font API."""
        if self.has_weights:
            return {"regular": ("Inter", False), "medium": ("Inter Medium", False),
                    "semibold": ("Inter SemiBold", False), "bold": ("Inter", True)}.get(weight, ("Inter", False))
        return self.family, weight in ("semibold", "bold")
