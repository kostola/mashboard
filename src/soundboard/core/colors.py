from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from soundboard.core.models import Sound

NAMED_COLORS: dict[str, str] = {
    "red": "#e74c3c",
    "blue": "#3498db",
    "green": "#27ae60",
    "yellow": "#f1c40f",
    "orange": "#e67e22",
    "purple": "#9b59b6",
    "pink": "#ff6fb5",
    "cyan": "#1abc9c",
    "white": "#ecf0f1",
    "black": "#2c3e50",
}

PALETTE: tuple[str, ...] = (
    "#e74c3c",
    "#3498db",
    "#27ae60",
    "#f1c40f",
    "#e67e22",
    "#9b59b6",
    "#ff6fb5",
    "#1abc9c",
    "#34495e",
    "#16a085",
    "#d35400",
    "#2980b9",
)

_HEX6_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def parse_color(value: str) -> str:
    """Accept hex (with or without ``#``) or a named colour, return ``#rrggbb`` lowercase."""
    if not value:
        raise ValueError("color must be non-empty")
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered in NAMED_COLORS:
        return NAMED_COLORS[lowered]
    if not _HEX6_RE.match(stripped):
        raise ValueError(f"invalid color: {value!r}")
    return ("#" + stripped.lstrip("#")).lower()


def derive_color(sound_id: str) -> str:
    digest = hashlib.sha256(sound_id.encode("utf-8")).digest()
    return PALETTE[digest[0] % len(PALETTE)]


def effective_color(sound: Sound) -> str:
    return sound.color or derive_color(sound.id)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    h = value.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, c)) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def lighten(value: str, amount: float) -> str:
    r, g, b = _hex_to_rgb(value)
    return _rgb_to_hex(
        (
            round(r + (255 - r) * amount),
            round(g + (255 - g) * amount),
            round(b + (255 - b) * amount),
        )
    )


def darken(value: str, amount: float) -> str:
    r, g, b = _hex_to_rgb(value)
    return _rgb_to_hex(
        (round(r * (1 - amount)), round(g * (1 - amount)), round(b * (1 - amount)))
    )


def text_color_for(cap_hex: str) -> str:
    r, g, b = _hex_to_rgb(cap_hex)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.55 else "#ffffff"
