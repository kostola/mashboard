from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Sound:
    id: str
    name: str
    path: Path
    hotkey: str | None = None
    tags: tuple[str, ...] = ()
    volume: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.volume <= 1.0:
            raise ValueError(f"volume must be in [0, 1], got {self.volume}")
        if not self.id:
            raise ValueError("id must be non-empty")
        if not self.name:
            raise ValueError("name must be non-empty")


@dataclass(slots=True)
class SoundAddResult:
    sound: Sound
    copied_to: Path | None = field(default=None)
