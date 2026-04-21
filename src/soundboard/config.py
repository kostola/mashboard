from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "soundboard"


@dataclass(frozen=True, slots=True)
class Paths:
    config_dir: Path
    data_dir: Path

    @property
    def library_file(self) -> Path:
        return self.config_dir / "library.toml"

    @property
    def sounds_dir(self) -> Path:
        return self.data_dir / "sounds"

    def ensure(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.sounds_dir.mkdir(parents=True, exist_ok=True)


def default_paths() -> Paths:
    return Paths(
        config_dir=Path(user_config_dir(APP_NAME, appauthor=False)),
        data_dir=Path(user_data_dir(APP_NAME, appauthor=False)),
    )
