from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from soundboard.audio.player import PlayHandle
from soundboard.config import Paths
from soundboard.core.library import SoundLibrary
from soundboard.core.models import Sound
from soundboard.gui.app import MainWindow
from soundboard.settings import InMemorySettingsRepository, Settings
from soundboard.storage.toml_repository import TomlLibraryRepository

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
    def __init__(self, device_name: str | None = None) -> None:
        self.played: list[Sound] = []
        self.stopped_all = False
        self.closed = False
        self.device_name = device_name

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


def test_audio_menu_lists_devices_and_marks_current(
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
    window._rebuild_audio_menu()  # type: ignore[attr-defined]
    assert window._audio_menu is not None  # type: ignore[attr-defined]
    actions = window._audio_menu.actions()  # type: ignore[attr-defined]
    labels = {a.text() for a in actions if a.isEnabled()}
    assert "&Use system default" in labels
    assert "Speakers (X)" in labels
    assert "VoiceMeeter Input (X)" in labels
    checked = {a.text() for a in actions if a.isCheckable() and a.isChecked()}
    assert checked == {"VoiceMeeter Input (X)"}


def test_selecting_device_persists_and_rebuilds_player(
    qtbot: QtBot, paths: Paths, populated_repo: TomlLibraryRepository
) -> None:
    settings_repo = InMemorySettingsRepository()
    built: list[str | None] = []

    def factory(device_name: str | None = None) -> FakePlayer:
        built.append(device_name)
        return FakePlayer(device_name)

    window = MainWindow(
        paths,
        populated_repo,
        FakePlayer(),
        settings_repository=settings_repo,
        player_factory=factory,
        device_lister=lambda: ["Speakers (X)", "VoiceMeeter Input (X)"],
    )
    qtbot.addWidget(window)

    window._set_device("VoiceMeeter Input (X)")  # type: ignore[attr-defined]

    assert settings_repo.load() == Settings(output_device="VoiceMeeter Input (X)")
    assert built == ["VoiceMeeter Input (X)"]

    window._set_device(None)  # type: ignore[attr-defined]
    assert settings_repo.load() == Settings(output_device=None)
    assert built == ["VoiceMeeter Input (X)", None]


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


def Qt_LeftButton() -> object:
    from PySide6.QtCore import Qt

    return Qt.MouseButton.LeftButton
