from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mashboard.audio.player import PlayHandle
from mashboard.config import Paths
from mashboard.core.library import SoundLibrary
from mashboard.core.models import Sound
from mashboard.gui.app import EditSoundDialog, MainWindow
from mashboard.settings import InMemorySettingsRepository, Settings
from mashboard.storage.toml_repository import TomlLibraryRepository

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class FakeHandle:
    def is_playing(self) -> bool:
        return False

    def stop(self) -> None:
        pass

    def wait(self) -> None:
        pass


class FakePlayer:
    def __init__(self, devices: list[str | None] | None = None) -> None:
        self.played: list[Sound] = []
        self.stopped_all = False
        self.closed = False
        self.devices: list[str | None] = list(devices) if devices is not None else [None]

    def play(self, sound: Sound) -> PlayHandle:
        self.played.append(sound)
        return FakeHandle()

    def stop_all(self) -> None:
        self.stopped_all = True

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    p = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    p.ensure()
    return p


@pytest.fixture
def repo(paths: Paths) -> TomlLibraryRepository:
    return TomlLibraryRepository(paths.library_file)


@pytest.fixture
def populated_repo(paths: Paths, tmp_path: Path) -> TomlLibraryRepository:
    repo = TomlLibraryRepository(paths.library_file)
    repo.save(
        SoundLibrary(
            [
                Sound(id="a", name="horn", path=tmp_path / "a.wav", tags=("funny",)),
                Sound(id="b", name="beep", path=tmp_path / "b.wav"),
                Sound(id="c", name="whistle", path=tmp_path / "c.wav", tags=("loud",)),
            ]
        )
    )
    return repo


def test_buttons_render_for_each_sound(
    qtbot: QtBot, paths: Paths, populated_repo: TomlLibraryRepository
) -> None:
    window = MainWindow(paths, populated_repo, FakePlayer())
    qtbot.addWidget(window)
    names = {b.sound.name for b in window.buttons}
    assert names == {"horn", "beep", "whistle"}


def test_click_plays_sound(
    qtbot: QtBot, paths: Paths, populated_repo: TomlLibraryRepository
) -> None:
    player = FakePlayer()
    window = MainWindow(paths, populated_repo, player)
    qtbot.addWidget(window)
    horn = next(b for b in window.buttons if b.sound.name == "horn")
    qtbot.mouseClick(horn, Qt_LeftButton())
    assert [s.name for s in player.played] == ["horn"]


def test_search_hides_non_matching_buttons(
    qtbot: QtBot, paths: Paths, populated_repo: TomlLibraryRepository
) -> None:
    window = MainWindow(paths, populated_repo, FakePlayer())
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    window._search.setText("loud")  # type: ignore[attr-defined]

    visible = {b.sound.name for b in window.buttons if b.isVisible()}
    hidden = {b.sound.name for b in window.buttons if not b.isVisible()}
    assert visible == {"whistle"}
    assert hidden == {"horn", "beep"}


def test_stop_all_triggers_player(
    qtbot: QtBot, paths: Paths, populated_repo: TomlLibraryRepository
) -> None:
    player = FakePlayer()
    window = MainWindow(paths, populated_repo, player)
    qtbot.addWidget(window)
    window._stop_all()  # type: ignore[attr-defined]
    assert player.stopped_all is True


def test_primary_menu_lists_devices_and_marks_current(
    qtbot: QtBot, paths: Paths, populated_repo: TomlLibraryRepository
) -> None:
    settings_repo = InMemorySettingsRepository(Settings(output_device="VoiceMeeter Input (X)"))
    window = MainWindow(
        paths,
        populated_repo,
        FakePlayer(),
        settings_repository=settings_repo,
        device_lister=lambda: ["Speakers (X)", "VoiceMeeter Input (X)"],
    )
    qtbot.addWidget(window)
    window._rebuild_primary_menu()  # type: ignore[attr-defined]
    assert window._primary_menu is not None  # type: ignore[attr-defined]
    actions = window._primary_menu.actions()  # type: ignore[attr-defined]
    labels = {a.text() for a in actions if a.isEnabled()}
    assert "&Use system default" in labels
    assert "Speakers (X)" in labels
    assert "VoiceMeeter Input (X)" in labels
    checked = {a.text() for a in actions if a.isCheckable() and a.isChecked()}
    assert checked == {"VoiceMeeter Input (X)"}


def test_monitor_menu_lists_devices_and_marks_current(
    qtbot: QtBot, paths: Paths, populated_repo: TomlLibraryRepository
) -> None:
    settings_repo = InMemorySettingsRepository(
        Settings(output_device="Speakers (X)", monitor_device="Headphones (Y)")
    )
    window = MainWindow(
        paths,
        populated_repo,
        FakePlayer(),
        settings_repository=settings_repo,
        device_lister=lambda: ["Speakers (X)", "Headphones (Y)"],
    )
    qtbot.addWidget(window)
    window._rebuild_monitor_menu()  # type: ignore[attr-defined]
    assert window._monitor_menu is not None  # type: ignore[attr-defined]
    actions = window._monitor_menu.actions()  # type: ignore[attr-defined]
    labels = {a.text() for a in actions if a.isEnabled()}
    assert "&None (off)" in labels
    assert "Headphones (Y)" in labels
    checked = {a.text() for a in actions if a.isCheckable() and a.isChecked()}
    assert checked == {"Headphones (Y)"}


def test_selecting_primary_persists_and_rebuilds_player(
    qtbot: QtBot, paths: Paths, populated_repo: TomlLibraryRepository
) -> None:
    settings_repo = InMemorySettingsRepository()
    built: list[list[str | None]] = []

    def factory(devices: list[str | None] | None = None) -> FakePlayer:
        built.append(list(devices) if devices is not None else [None])
        return FakePlayer(devices)

    window = MainWindow(
        paths,
        populated_repo,
        FakePlayer(),
        settings_repository=settings_repo,
        player_factory=factory,
        device_lister=lambda: ["Speakers (X)", "VoiceMeeter Input (X)"],
    )
    qtbot.addWidget(window)

    window._set_primary("VoiceMeeter Input (X)")  # type: ignore[attr-defined]

    assert settings_repo.load() == Settings(output_device="VoiceMeeter Input (X)")
    assert built == [["VoiceMeeter Input (X)"]]

    window._set_primary(None)  # type: ignore[attr-defined]
    assert settings_repo.load() == Settings(output_device=None)
    assert built == [["VoiceMeeter Input (X)"], [None]]


def test_selecting_monitor_persists_and_rebuilds_player(
    qtbot: QtBot, paths: Paths, populated_repo: TomlLibraryRepository
) -> None:
    settings_repo = InMemorySettingsRepository(Settings(output_device="Speakers (X)"))
    built: list[list[str | None]] = []

    def factory(devices: list[str | None] | None = None) -> FakePlayer:
        built.append(list(devices) if devices is not None else [None])
        return FakePlayer(devices)

    window = MainWindow(
        paths,
        populated_repo,
        FakePlayer(),
        settings_repository=settings_repo,
        player_factory=factory,
        device_lister=lambda: ["Speakers (X)", "Headphones (Y)"],
    )
    qtbot.addWidget(window)

    window._set_monitor("Headphones (Y)")  # type: ignore[attr-defined]

    assert settings_repo.load() == Settings(
        output_device="Speakers (X)", monitor_device="Headphones (Y)"
    )
    assert built == [["Speakers (X)", "Headphones (Y)"]]

    window._set_monitor(None)  # type: ignore[attr-defined]
    assert settings_repo.load() == Settings(output_device="Speakers (X)")
    assert built[-1] == ["Speakers (X)"]


def test_import_adds_sound(
    qtbot: QtBot, paths: Paths, repo: TomlLibraryRepository, tmp_path: Path
) -> None:
    clip = tmp_path / "new.wav"
    clip.write_bytes(b"RIFF0000WAVE")
    window = MainWindow(paths, repo, FakePlayer())
    qtbot.addWidget(window)

    sound = window.import_sound(clip, name="new")

    assert sound is not None
    assert sound.name == "new"
    assert sound.path.parent == paths.sounds_dir
    assert sound.path.exists()
    assert {b.sound.name for b in window.buttons} == {"new"}


def test_button_uses_explicit_color_in_stylesheet(
    qtbot: QtBot, paths: Paths, tmp_path: Path
) -> None:
    repo = TomlLibraryRepository(paths.library_file)
    repo.save(
        SoundLibrary(
            [
                Sound(
                    id="a",
                    name="horn",
                    path=tmp_path / "a.wav",
                    color="#22aa55",
                )
            ]
        )
    )
    window = MainWindow(paths, repo, FakePlayer())
    qtbot.addWidget(window)
    button = window.buttons[0]
    qss = button.styleSheet()
    assert "#22aa55" in qss
    assert button.cap_color == "#22aa55"
    assert button.size().width() == 120
    assert button.size().height() == 120
    assert button.graphicsEffect() is not None


def test_button_size_loads_from_settings_and_persists_on_change(
    qtbot: QtBot, paths: Paths, populated_repo: TomlLibraryRepository
) -> None:
    settings_repo = InMemorySettingsRepository(Settings(gui_button_size=160))
    window = MainWindow(
        paths,
        populated_repo,
        FakePlayer(),
        settings_repository=settings_repo,
    )
    qtbot.addWidget(window)
    assert window._button_size == 160  # type: ignore[attr-defined]
    assert all(b.size().width() == 160 for b in window.buttons)

    window._on_size_changed(96)  # type: ignore[attr-defined]
    assert settings_repo.load().gui_button_size == 96
    assert all(b.size().width() == 96 for b in window.buttons)


def test_button_text_color_contrasts_with_cap(
    qtbot: QtBot, paths: Paths, tmp_path: Path
) -> None:
    repo = TomlLibraryRepository(paths.library_file)
    repo.save(
        SoundLibrary(
            [
                Sound(
                    id="light",
                    name="bright",
                    path=tmp_path / "l.wav",
                    color="#ffffff",
                ),
                Sound(
                    id="dark",
                    name="deep",
                    path=tmp_path / "d.wav",
                    color="#000000",
                ),
            ]
        )
    )
    window = MainWindow(paths, repo, FakePlayer())
    qtbot.addWidget(window)
    by_name = {b.sound.name: b.styleSheet() for b in window.buttons}
    assert "color: #000000" in by_name["bright"]
    assert "color: #ffffff" in by_name["deep"]


def Qt_LeftButton() -> object:
    from PySide6.QtCore import Qt

    return Qt.MouseButton.LeftButton


def test_edit_dialog_round_trips_unchanged_sound(qtbot: QtBot, tmp_path: Path) -> None:
    sound = Sound(
        id="a",
        name="horn",
        path=tmp_path / "a.wav",
        hotkey="ctrl+h",
        tags=("funny",),
        volume=0.5,
        color="#22aa55",
    )
    dialog = EditSoundDialog(sound)
    qtbot.addWidget(dialog)
    assert dialog.updated_sound() == sound


def test_edit_dialog_applies_name_volume_tags_color(qtbot: QtBot, tmp_path: Path) -> None:
    sound = Sound(id="a", name="horn", path=tmp_path / "a.wav")
    dialog = EditSoundDialog(sound)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("HORN!")  # type: ignore[attr-defined]
    dialog._volume_spin.setValue(0.25)  # type: ignore[attr-defined]
    dialog._tags_edit.setText("loud, brassy")  # type: ignore[attr-defined]
    dialog._color = "#abcdef"  # type: ignore[attr-defined]

    updated = dialog.updated_sound()
    assert updated.name == "HORN!"
    assert updated.volume == pytest.approx(0.25)
    assert updated.tags == ("loud", "brassy")
    assert updated.color == "#abcdef"
    assert updated.id == sound.id
    assert updated.path == sound.path


def test_edit_dialog_blank_hotkey_clears(qtbot: QtBot, tmp_path: Path) -> None:
    sound = Sound(id="a", name="horn", path=tmp_path / "a.wav", hotkey="ctrl+h")
    dialog = EditSoundDialog(sound)
    qtbot.addWidget(dialog)
    dialog._hotkey_edit.setText("")  # type: ignore[attr-defined]
    assert dialog.updated_sound().hotkey is None


