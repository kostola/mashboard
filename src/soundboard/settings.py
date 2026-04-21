from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import tomli_w


@dataclass(frozen=True, slots=True)
class Settings:
    output_device: str | None = None


class SettingsRepository(Protocol):
    def load(self) -> Settings: ...
    def save(self, settings: Settings) -> None: ...


class TomlSettingsRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Settings:
        if not self._path.exists():
            return Settings()
        data = tomllib.loads(self._path.read_text(encoding="utf-8"))
        return _settings_from_dict(data)

    def save(self, settings: Settings) -> None:
        payload = _settings_to_dict(settings)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(tomli_w.dumps(payload).encode("utf-8"))


class InMemorySettingsRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()

    def load(self) -> Settings:
        return self._settings

    def save(self, settings: Settings) -> None:
        self._settings = settings


def _settings_to_dict(settings: Settings) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if settings.output_device is not None:
        payload["output_device"] = settings.output_device
    return payload


def _settings_from_dict(data: dict[str, Any]) -> Settings:
    device = data.get("output_device")
    return Settings(output_device=str(device) if device else None)
