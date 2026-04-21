from __future__ import annotations

from pathlib import Path

import pytest

from soundboard.core.library import (
    SoundAlreadyExistsError,
    SoundLibrary,
    SoundNotFoundError,
)
from soundboard.core.models import Sound


def make_sound(**overrides: object) -> Sound:
    defaults: dict[str, object] = {
        "id": "abc123",
        "name": "horn",
        "path": Path("/tmp/horn.wav"),
    }
    defaults.update(overrides)
    return Sound(**defaults)  # type: ignore[arg-type]


def test_add_and_find_by_name_and_id() -> None:
    lib = SoundLibrary()
    s = make_sound()
    lib.add(s)
    assert lib.find("horn") is s
    assert lib.find("abc123") is s
    assert "horn" in lib
    assert len(lib) == 1


def test_add_duplicate_name_raises() -> None:
    lib = SoundLibrary([make_sound()])
    with pytest.raises(SoundAlreadyExistsError):
        lib.add(make_sound(id="other"))


def test_remove_returns_and_deletes() -> None:
    lib = SoundLibrary([make_sound()])
    removed = lib.remove("horn")
    assert removed.name == "horn"
    assert len(lib) == 0
    with pytest.raises(SoundNotFoundError):
        lib.find("horn")


def test_search_by_tag() -> None:
    a = make_sound(id="a", name="horn", tags=("funny", "loud"))
    b = make_sound(id="b", name="beep", tags=("loud",))
    c = make_sound(id="c", name="quiet", tags=())
    lib = SoundLibrary([a, b, c])
    assert {s.name for s in lib.search("loud")} == {"horn", "beep"}
    assert lib.search("nope") == []


def test_get_returns_none_when_missing() -> None:
    assert SoundLibrary().get("missing") is None


def test_invalid_volume_rejected() -> None:
    with pytest.raises(ValueError):
        make_sound(volume=1.5)
