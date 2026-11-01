"""User interface settings: defaults, palettes and validation."""

from __future__ import annotations

import json
from typing import Any

from .util import validate_image_data_uri

ACCENTS: dict[str, str] = {
    "indigo": "#6366f1",
    "violet": "#8b5cf6",
    "purple": "#a855f7",
    "fuchsia": "#d946ef",
    "pink": "#ec4899",
    "rose": "#f43f5e",
    "red": "#ef4444",
    "orange": "#f97316",
    "amber": "#f59e0b",
    "lime": "#84cc16",
    "green": "#22c55e",
    "emerald": "#10b981",
    "teal": "#14b8a6",
    "cyan": "#06b6d4",
    "sky": "#0ea5e9",
    "blue": "#3b82f6",
    "slate": "#64748b",
    "graphite": "#475569",
    "charcoal": "#334155",
    "onyx": "#1e293b",
    "zinc": "#52525b",
    "silver": "#94a3b8",
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "github",
    "colorScheme": "system",
    "fontSize": 16,
    "radius": 18,
    "glow": True,
    "lang": "ru",
    "hover": True,
    "hover_scale": 1.05,
    "animations": True,
    "layout": "grid",
    "sort": "created",
    "sort_dir": "desc",
    "show_favicons": True,
    "quicklinks": [],
}

THEME_NAMES = frozenset(
    {
        "aura",
        "ayu",
        "carbonfox",
        "cobalt2",
        "cursor",
        "dracula",
        "everforest",
        "flexoki",
        "catppuccin",
        "catppuccin-frappe",
        "catppuccin-macchiato",
        "github",
        "gruvbox",
        "kanagawa",
        "material",
        "matrix",
        "mercury",
        "monokai",
        "nightowl",
        "nord",
        "one-dark",
        "opencode",
        "orng",
        "lucent-orng",
        "osaka-jade",
        "palenight",
        "rosepine",
        "solarized",
        "synthwave84",
        "tokyonight",
        "vercel",
        "vesper",
        "zenburn",
    }
)
COLOR_SCHEMES = frozenset({"light", "dark", "system"})
LANGS = {"ru", "en"}
LAYOUTS = {"rows", "wide", "tiles", "grid"}
SORTS = {"created", "title", "visits", "updated"}
DIRECTIONS = {"asc", "desc"}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


QUICK_LINKS_MAX = 5
QUICK_LINK_ICON_MAX = 512 * 1024


def _normalize_quicklinks(value: Any) -> list[dict[str, Any]]:
    """Keep up to *QUICK_LINKS_MAX* {url, title, icon} entries, drop the rest."""
    items: list[dict[str, Any]] = []
    if not isinstance(value, (list, tuple)):
        return items
    for entry in value:
        if len(items) >= QUICK_LINKS_MAX:
            break
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").strip()
        title = str(entry.get("title") or "").strip()[:200]
        icon = validate_image_data_uri(entry.get("icon"), max_bytes=QUICK_LINK_ICON_MAX) or None
        if not url or len(url) > 2000:
            continue
        items.append({"url": url, "title": title, "icon": icon})
    return items


def _as_number(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return max(low, min(high, number))


def normalize_settings(raw: Any, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge *raw* over the defaults and clamp every value."""
    settings = dict(DEFAULT_SETTINGS if base is None else base)
    if not isinstance(raw, dict):
        raw = {}

    # Migrate pre-1.0.2 values: the old "theme" key doubled as the color
    # scheme, and "scale" (0.8–1.3) corresponds to the font size.
    legacy_theme = raw.get("theme")
    if legacy_theme in COLOR_SCHEMES:
        settings["colorScheme"] = legacy_theme
    elif legacy_theme == "flexoki":
        settings["theme"] = "flexoki"
        settings["colorScheme"] = "dark"
    if settings.get("theme") not in THEME_NAMES:
        settings["theme"] = DEFAULT_SETTINGS["theme"]
    if settings.get("colorScheme") not in COLOR_SCHEMES:
        settings["colorScheme"] = "system"
    if raw.get("scale"):
        try:
            settings["fontSize"] = int(max(13, min(19, round(16 * float(raw["scale"])))))
        except (TypeError, ValueError):
            pass

    if raw.get("theme") in THEME_NAMES:
        settings["theme"] = raw["theme"]
    if raw.get("colorScheme") in COLOR_SCHEMES:
        settings["colorScheme"] = raw["colorScheme"]
    if raw.get("fontSize") is not None:
        settings["fontSize"] = int(max(13, min(19, _as_number(raw["fontSize"], 16, 13, 19))))
    if raw.get("lang") in LANGS:
        settings["lang"] = raw["lang"]
    if raw.get("layout") in LAYOUTS:
        settings["layout"] = raw["layout"]
    if raw.get("sort") in SORTS:
        settings["sort"] = raw["sort"]
    if raw.get("sort_dir") in DIRECTIONS:
        settings["sort_dir"] = raw["sort_dir"]

    settings["radius"] = int(round(_as_number(raw.get("radius", settings.get("radius", 18)), 18, 0, 30)))
    settings["hover_scale"] = round(_as_number(raw.get("hover_scale", settings.get("hover_scale", 1.05)), 1.05, 1.0, 1.5), 2)
    settings["glow"] = _as_bool(raw.get("glow", settings.get("glow", True)), True)
    settings["hover"] = _as_bool(raw.get("hover", settings.get("hover", True)), True)
    settings["animations"] = _as_bool(raw.get("animations", settings.get("animations", True)), True)
    settings["show_favicons"] = _as_bool(raw.get("show_favicons", settings.get("show_favicons", True)), True)
    settings["quicklinks"] = _normalize_quicklinks(raw.get("quicklinks", settings.get("quicklinks", [])))

    # Legacy keys are no longer used by the front-end.
    settings.pop("accent", None)
    settings.pop("scale", None)
    return settings


def load_settings(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        parsed = {}
    return normalize_settings(parsed)
