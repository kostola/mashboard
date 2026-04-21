from __future__ import annotations

from pathlib import Path

import pytest

from soundboard.audio.player import PlayHandle
from soundboard.core.library import SoundLibrary
from soundboard.core.models import Sound
from soundboard.storage.toml_repository import TomlLibraryRepository
from soundboard.tui.app import SoundboardApp, SoundButton


class FakeHandle:
    def is_playing(self) -> bool:
        return False

    def stop(self) -> None:
        pass

    def wait(self) -> None:
        pass


class FakePlayer:
    def __init__(self) -> None:
        self.played: list[Sound] = []
        self.stopped_all = False
        self.closed = False

    def play(self, sound: Sound) -> PlayHandle:
        self.played.append(sound)
        return FakeHandle()

    def stop_all(self) -> None:
        self.stopped_all = True

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def populated_repo(tmp_path: Path) -> TomlLibraryRepository:
    repo = TomlLibraryRepository(tmp_path / "library.toml")
    repo.save(
        SoundLibrary(
            [
                Sound(id="a", name="horn", path=tmp_path / "a.wav", tags=("funny",)),
                Sound(id="b", name="beep", path=tmp_path / "b.wav", hotkey="b"),
                Sound(id="c", name="whistle", path=tmp_path / "c.wav", tags=("loud",)),
            ]
        )
    )
    return repo


async def test_renders_buttons_for_each_sound(populated_repo: TomlLibraryRepository) -> None:
    app = SoundboardApp(populated_repo, FakePlayer())
    async with app.run_test() as pilot:
        await pilot.pause()
        names = {b.sound.name for b in app.query(SoundButton)}
        assert names == {"horn", "beep", "whistle"}


async def test_button_press_plays_sound(populated_repo: TomlLibraryRepository) -> None:
    player = FakePlayer()
    app = SoundboardApp(populated_repo, player)
    async with app.run_test() as pilot:
        await pilot.pause()
        button = next(b for b in app.query(SoundButton) if b.sound.name == "horn")
        await pilot.click(button)
        await pilot.pause()
        assert [s.name for s in player.played] == ["horn"]


async def test_search_filters_buttons(populated_repo: TomlLibraryRepository) -> None:
    app = SoundboardApp(populated_repo, FakePlayer())
    async with app.run_test() as pilot:
        await pilot.pause()
        app.filter_text = "loud"
        await pilot.pause()
        visible = {b.sound.name for b in app.query(SoundButton) if b.display}
        hidden = {b.sound.name for b in app.query(SoundButton) if not b.display}
        assert visible == {"whistle"}
        assert hidden == {"horn", "beep"}


async def test_escape_stops_all(populated_repo: TomlLibraryRepository) -> None:
    player = FakePlayer()
    app = SoundboardApp(populated_repo, player)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert player.stopped_all is True


async def test_hotkey_action_plays_bound_sound(populated_repo: TomlLibraryRepository) -> None:
    player = FakePlayer()
    app = SoundboardApp(populated_repo, player)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.run_action("play_id('b')")
        assert [s.name for s in player.played] == ["beep"]


