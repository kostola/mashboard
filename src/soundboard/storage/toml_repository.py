from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from soundboard.core.library import SoundLibrary
from soundboard.core.models import Sound


class TomlLibraryRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> SoundLibrary:
        if not self._path.exists():
            return SoundLibrary()
        data = tomllib.loads(self._path.read_text(encoding="utf-8"))
        sounds = [_sound_from_dict(entry) for entry in data.get("sounds", [])]
        return SoundLibrary(sounds)

    def save(self, library: SoundLibrary) -> None:
        payload: dict[str, Any] = {"sounds": [_sound_to_dict(s) for s in library]}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(tomli_w.dumps(payload).encode("utf-8"))


def _sound_to_dict(sound: Sound) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": sound.id,
        "name": sound.name,
        "path": str(sound.path),
        "volume": sound.volume,
        "tags": list(sound.tags),
    }
    if sound.hotkey is not None:
        entry["hotkey"] = sound.hotkey
    return entry


def _sound_from_dict(entry: dict[str, Any]) -> Sound:
    return Sound(
        id=str(entry["id"]),
        name=str(entry["name"]),
        path=Path(entry["path"]),
        hotkey=entry.get("hotkey"),
        tags=tuple(entry.get("tags", [])),
        volume=float(entry.get("volume", 1.0)),
    )
