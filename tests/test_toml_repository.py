from __future__ import annotations

from pathlib import Path

from soundboard.core.library import SoundLibrary
from soundboard.core.models import Sound
from soundboard.storage.toml_repository import TomlLibraryRepository


def test_load_missing_file_returns_empty_library(tmp_path: Path) -> None:
    repo = TomlLibraryRepository(tmp_path / "missing.toml")
    assert len(repo.load()) == 0


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    sounds = [
        Sound(id="a", name="horn", path=Path("/clips/horn.wav"), tags=("funny",)),
        Sound(id="b", name="beep", path=Path("/clips/beep.ogg"), hotkey="ctrl+b", volume=0.5),
    ]
    repo = TomlLibraryRepository(tmp_path / "library.toml")
    repo.save(SoundLibrary(sounds))

    loaded = repo.load()
    assert len(loaded) == 2
    horn = loaded.find("horn")
    assert horn.tags == ("funny",)
    beep = loaded.find("beep")
    assert beep.hotkey == "ctrl+b"
    assert beep.volume == 0.5


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    repo = TomlLibraryRepository(tmp_path / "nested" / "library.toml")
    repo.save(SoundLibrary())
    assert repo.path.exists()


def test_color_round_trips_when_set(tmp_path: Path) -> None:
    sounds = [
        Sound(id="a", name="horn", path=Path("/clips/horn.wav"), color="#ff5733"),
        Sound(id="b", name="beep", path=Path("/clips/beep.ogg")),
    ]
    repo = TomlLibraryRepository(tmp_path / "library.toml")
    repo.save(SoundLibrary(sounds))

    loaded = repo.load()
    assert loaded.find("horn").color == "#ff5733"
    assert loaded.find("beep").color is None


def test_legacy_toml_without_color_loads_with_none(tmp_path: Path) -> None:
    legacy = tmp_path / "library.toml"
    legacy.write_text(
        '[[sounds]]\nid = "a"\nname = "horn"\npath = "/clips/horn.wav"\nvolume = 1.0\ntags = []\n',
        encoding="utf-8",
    )
    loaded = TomlLibraryRepository(legacy).load()
    assert loaded.find("horn").color is None
