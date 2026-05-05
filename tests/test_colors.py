from __future__ import annotations

from pathlib import Path

import pytest

from soundboard.core.colors import (
    NAMED_COLORS,
    PALETTE,
    darken,
    derive_color,
    effective_color,
    lighten,
    parse_color,
    text_color_for,
)
from soundboard.core.models import Sound


def test_parse_color_accepts_hex_with_hash() -> None:
    assert parse_color("#FF5733") == "#ff5733"


def test_parse_color_accepts_hex_without_hash() -> None:
    assert parse_color("ff5733") == "#ff5733"


def test_parse_color_accepts_named() -> None:
    assert parse_color("red") == NAMED_COLORS["red"]
    assert parse_color("Red") == NAMED_COLORS["red"]


@pytest.mark.parametrize("bad", ["", "#xyz", "#fff", "taupe", "#1234567"])
def test_parse_color_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_color(bad)


def test_derive_color_is_deterministic() -> None:
    a = derive_color("abc123")
    b = derive_color("abc123")
    assert a == b
    assert a in PALETTE


def test_derive_color_distributes_across_palette() -> None:
    seen = {derive_color(f"id-{i}") for i in range(200)}
    assert len(seen) > 1


def test_effective_color_uses_explicit() -> None:
    sound = Sound(id="x", name="x", path=Path("/tmp/x"), color="#abcdef")
    assert effective_color(sound) == "#abcdef"


def test_effective_color_falls_back_to_derived() -> None:
    sound = Sound(id="x", name="x", path=Path("/tmp/x"))
    assert effective_color(sound) == derive_color("x")


def test_text_color_for_picks_black_on_light_caps() -> None:
    assert text_color_for("#ffffff") == "#000000"
    assert text_color_for("#f1c40f") == "#000000"


def test_text_color_for_picks_white_on_dark_caps() -> None:
    assert text_color_for("#000000") == "#ffffff"
    assert text_color_for("#34495e") == "#ffffff"


def test_lighten_clamps_at_white() -> None:
    assert lighten("#ffffff", 0.5) == "#ffffff"


def test_darken_clamps_at_black() -> None:
    assert darken("#000000", 0.5) == "#000000"


def test_lighten_then_darken_changes_value() -> None:
    base = "#3498db"
    assert lighten(base, 0.4) != base
    assert darken(base, 0.4) != base


def test_invalid_color_on_sound_raises() -> None:
    with pytest.raises(ValueError):
        Sound(id="x", name="x", path=Path("/tmp/x"), color="red")
    with pytest.raises(ValueError):
        Sound(id="x", name="x", path=Path("/tmp/x"), color="#FFF")
