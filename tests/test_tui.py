from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Input, Select

from soundboard.audio.player import PlayHandle
from soundboard.core.library import SoundLibrary
from soundboard.core.models import Sound
from soundboard.settings import InMemorySettingsRepository, Settings
from soundboard.storage.toml_repository import TomlLibraryRepository
from soundboard.tui.app import (
    DEFAULT_SIZE_INDEX,
    NO_DEVICE_VALUE,
    SIZE_PRESETS,
    DeviceSettingsScreen,
    EditSoundScreen,
    SoundboardApp,
    SoundButton,
)


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


async def test_button_uses_explicit_color(tmp_path: Path) -> None:
    repo = TomlLibraryRepository(tmp_path / "library.toml")
    repo.save(
        SoundLibrary(
            [Sound(id="a", name="horn", path=tmp_path / "a.wav", color="#22aa55")]
        )
    )
    app = SoundboardApp(repo, FakePlayer())
    async with app.run_test() as pilot:
        await pilot.pause()
        button = next(iter(app.query(SoundButton)))
        assert button.cap_color == "#22aa55"


async def test_resize_actions_change_size_and_persist(
    populated_repo: TomlLibraryRepository,
) -> None:
    settings_repo = InMemorySettingsRepository()
    app = SoundboardApp(
        populated_repo,
        FakePlayer(),
        settings_repository=settings_repo,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._size_idx == DEFAULT_SIZE_INDEX

        await app.run_action("resize_up")
        await pilot.pause()
        assert app._size_idx == DEFAULT_SIZE_INDEX + 1
        assert settings_repo.load().tui_button_size == DEFAULT_SIZE_INDEX + 1

        await app.run_action("resize_down")
        await app.run_action("resize_down")
        await pilot.pause()
        assert app._size_idx == DEFAULT_SIZE_INDEX - 1
        assert settings_repo.load().tui_button_size == DEFAULT_SIZE_INDEX - 1


async def test_resize_clamps_to_range(
    populated_repo: TomlLibraryRepository,
) -> None:
    app = SoundboardApp(populated_repo, FakePlayer())
    async with app.run_test() as pilot:
        await pilot.pause()
        for _ in range(len(SIZE_PRESETS) + 2):
            await app.run_action("resize_up")
        await pilot.pause()
        assert app._size_idx == len(SIZE_PRESETS) - 1

        for _ in range(len(SIZE_PRESETS) + 2):
            await app.run_action("resize_down")
        await pilot.pause()
        assert app._size_idx == 0


async def test_initial_size_loaded_from_settings(
    populated_repo: TomlLibraryRepository,
) -> None:
    app = SoundboardApp(
        populated_repo,
        FakePlayer(),
        settings=Settings(tui_button_size=2),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._size_idx == 2


async def test_edit_action_without_focus_shows_status(
    populated_repo: TomlLibraryRepository,
) -> None:
    app = SoundboardApp(populated_repo, FakePlayer())
    async with app.run_test() as pilot:
        await pilot.pause()
        # Take focus away from any sound button.
        app.query_one("#search", Input).focus()
        await pilot.pause()
        await app.run_action("edit_focused")
        await pilot.pause()
        assert not isinstance(app.screen, EditSoundScreen)


async def test_edit_action_opens_screen_for_focused_button(
    populated_repo: TomlLibraryRepository,
) -> None:
    app = SoundboardApp(populated_repo, FakePlayer())
    async with app.run_test() as pilot:
        await pilot.pause()
        button = next(b for b in app.query(SoundButton) if b.sound.name == "horn")
        button.focus()
        await pilot.pause()
        await app.run_action("edit_focused")
        await pilot.pause()
        assert isinstance(app.screen, EditSoundScreen)


async def test_edit_screen_round_trips_unchanged(tmp_path: Path) -> None:
    sound = Sound(
        id="a",
        name="horn",
        path=tmp_path / "a.wav",
        hotkey="ctrl+h",
        tags=("funny",),
        volume=0.5,
        color="#22aa55",
    )
    screen = EditSoundScreen(sound)
    app = SoundboardApp(
        TomlLibraryRepository(tmp_path / "unused.toml"), FakePlayer()
    )
    async with app.run_test() as pilot:
        await app.push_screen(screen)
        await pilot.pause()
        assert screen._build_sound() == sound


async def test_edit_screen_applies_changes_via_action(tmp_path: Path) -> None:
    repo = TomlLibraryRepository(tmp_path / "library.toml")
    repo.save(SoundLibrary([Sound(id="a", name="horn", path=tmp_path / "a.wav")]))
    app = SoundboardApp(repo, FakePlayer())
    async with app.run_test() as pilot:
        await pilot.pause()
        button = next(b for b in app.query(SoundButton) if b.sound.name == "horn")
        button.focus()
        await pilot.pause()
        await app.run_action("edit_focused")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EditSoundScreen)
        screen.query_one("#edit-name", Input).value = "HORN!"
        screen.query_one("#edit-volume", Input).value = "0.25"
        screen.query_one("#edit-color", Input).value = "blue"
        screen._submit()  # type: ignore[attr-defined]
        await pilot.pause()
    library = repo.load()
    horn = library.find("HORN!")
    assert horn.volume == 0.25
    assert horn.color == "#3498db"


async def test_devices_action_opens_screen(
    populated_repo: TomlLibraryRepository,
) -> None:
    app = SoundboardApp(
        populated_repo,
        FakePlayer(),
        device_lister=lambda: ["Speakers (Test)", "Headphones (Test)"],
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.run_action("devices")
        await pilot.pause()
        assert isinstance(app.screen, DeviceSettingsScreen)


async def test_device_screen_persists_selection_and_rebuilds(
    populated_repo: TomlLibraryRepository,
) -> None:
    settings_repo = InMemorySettingsRepository()
    rebuilt: list[list[str | None]] = []

    def factory(devices: list[str | None] | None = None) -> FakePlayer:
        rebuilt.append(list(devices) if devices is not None else [None])
        return FakePlayer()

    app = SoundboardApp(
        populated_repo,
        FakePlayer(),
        settings_repository=settings_repo,
        device_lister=lambda: ["Speakers (Test)", "Headphones (Test)"],
        player_factory=factory,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.run_action("devices")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, DeviceSettingsScreen)
        screen.query_one("#primary-select", Select).value = "Speakers (Test)"
        screen.query_one("#monitor-select", Select).value = "Headphones (Test)"
        await pilot.click("#device-ok")
        await pilot.pause()
    saved = settings_repo.load()
    assert saved.output_device == "Speakers (Test)"
    assert saved.monitor_device == "Headphones (Test)"
    assert rebuilt == [["Speakers (Test)", "Headphones (Test)"]]


async def test_device_screen_cancel_does_not_persist(
    populated_repo: TomlLibraryRepository,
) -> None:
    settings_repo = InMemorySettingsRepository(Settings(output_device="Speakers (Test)"))
    app = SoundboardApp(
        populated_repo,
        FakePlayer(),
        settings_repository=settings_repo,
        device_lister=lambda: ["Speakers (Test)", "Headphones (Test)"],
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.run_action("devices")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, DeviceSettingsScreen)
        screen.query_one("#primary-select", Select).value = "Headphones (Test)"
        await pilot.click("#device-cancel")
        await pilot.pause()
    assert settings_repo.load().output_device == "Speakers (Test)"


async def test_device_screen_default_sentinel_clears_to_none(
    populated_repo: TomlLibraryRepository,
) -> None:
    settings_repo = InMemorySettingsRepository(
        Settings(output_device="Speakers (Test)", monitor_device="Headphones (Test)")
    )
    app = SoundboardApp(
        populated_repo,
        FakePlayer(),
        settings_repository=settings_repo,
        device_lister=lambda: ["Speakers (Test)", "Headphones (Test)"],
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.run_action("devices")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, DeviceSettingsScreen)
        screen.query_one("#primary-select", Select).value = NO_DEVICE_VALUE
        screen.query_one("#monitor-select", Select).value = NO_DEVICE_VALUE
        await pilot.click("#device-ok")
        await pilot.pause()
    saved = settings_repo.load()
    assert saved.output_device is None
    assert saved.monitor_device is None


