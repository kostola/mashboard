from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_HEX_COLOR_RE = re.compile(r"^#[0-9a-f]{6}$")


@dataclass(frozen=True, slots=True)
class Sound:
    id: str
    name: str
    path: Path
    hotkey: str | None = None
    tags: tuple[str, ...] = ()
    volume: float = 1.0
    color: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.volume <= 1.0:
            raise ValueError(f"volume must be in [0, 1], got {self.volume}")
        if not self.id:
            raise ValueError("id must be non-empty")
        if not self.name:
            raise ValueError("name must be non-empty")
        if self.color is not None and not _HEX_COLOR_RE.match(self.color):
            raise ValueError(f"color must be lowercase #rrggbb, got {self.color!r}")


@dataclass(slots=True)
class SoundAddResult:
    sound: Sound
    copied_to: Path | None = field(default=None)
