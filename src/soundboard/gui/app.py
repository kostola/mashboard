from __future__ import annotations

import contextlib
import shutil
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from soundboard.audio.devices import list_output_devices
from soundboard.audio.player import Player
from soundboard.audio.sounddevice_player import SoundDevicePlayer
from soundboard.config import Paths, default_paths
from soundboard.core.library import (
    SoundAlreadyExistsError,
    SoundNotFoundError,
)
from soundboard.core.models import Sound
from soundboard.settings import (
    Settings,
    SettingsRepository,
    TomlSettingsRepository,
)
from soundboard.storage.repository import LibraryRepository
from soundboard.storage.toml_repository import TomlLibraryRepository

GRID_COLUMNS = 4


class SoundButton(QPushButton):
    def __init__(self, sound: Sound, parent: QWidget | None = None) -> None:
        label = sound.name if not sound.hotkey else f"{sound.name}\n[{sound.hotkey}]"
        super().__init__(label, parent)
        self.sound = sound
        self.setMinimumHeight(64)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)


PlayerFactory = Callable[..., Player]


class MainWindow(QMainWindow):
    def __init__(
        self,
        paths: Paths,
        repository: LibraryRepository,
        player: Player,
        settings_repository: SettingsRepository | None = None,
        player_factory: PlayerFactory = SoundDevicePlayer,
        device_lister: Callable[[], list[str]] = list_output_devices,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._paths = paths
        self._repository = repository
        self._player = player
        self._settings_repository = settings_repository
        self._player_factory = player_factory
        self._device_lister = device_lister
        self._shortcuts: list[QShortcut] = []
        self._buttons: list[SoundButton] = []
        self._filter_text = ""
        self._audio_menu: QMenu | None = None
        self._primary_menu: QMenu | None = None
        self._monitor_menu: QMenu | None = None
        self._primary_group: QActionGroup | None = None
        self._monitor_group: QActionGroup | None = None

        self.setWindowTitle("Soundboard")
        self.resize(720, 520)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        self._search = QLineEdit(central)
        self._search.setPlaceholderText("Filter by name or tag…")
        self._search.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self._search)

        self._scroll = QScrollArea(central)
        self._scroll.setWidgetResizable(True)
        layout.addWidget(self._scroll, 1)

        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._grid_container)

        self.setCentralWidget(central)

        self._build_menu()
        self.statusBar().showMessage("Ready")
        self._reload()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        import_action = QAction("&Import sound…", self)
        import_action.setShortcut(QKeySequence("Ctrl+O"))
        import_action.triggered.connect(self._import_sound)
        file_menu.addAction(import_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        sound_menu = self.menuBar().addMenu("&Sound")
        stop_all = QAction("&Stop all", self)
        stop_all.setShortcut(QKeySequence("Esc"))
        stop_all.triggered.connect(self._stop_all)
        sound_menu.addAction(stop_all)

        reload_action = QAction("&Reload library", self)
        reload_action.setShortcut(QKeySequence("F5"))
        reload_action.triggered.connect(self._reload)
        sound_menu.addAction(reload_action)

        self._audio_menu = self.menuBar().addMenu("&Audio")
        self._primary_menu = self._audio_menu.addMenu("&Output device")
        self._monitor_menu = self._audio_menu.addMenu("&Monitor device")
        self._primary_menu.aboutToShow.connect(self._rebuild_primary_menu)
        self._monitor_menu.aboutToShow.connect(self._rebuild_monitor_menu)
        self._rebuild_primary_menu()
        self._rebuild_monitor_menu()

    def _current_settings(self) -> Settings:
        if self._settings_repository is None:
            return Settings()
        return self._settings_repository.load()

    def _devices(self) -> list[str]:
        try:
            return self._device_lister()
        except Exception:  # noqa: BLE001
            return []

    def _rebuild_primary_menu(self) -> None:
        if self._primary_menu is None:
            return
        self._primary_menu.clear()
        self._primary_group = QActionGroup(self)
        self._primary_group.setExclusive(True)

        current = self._current_settings().output_device
        default_action = QAction("&Use system default", self)
        default_action.setCheckable(True)
        default_action.setChecked(current is None)
        default_action.triggered.connect(lambda: self._set_primary(None))
        self._primary_group.addAction(default_action)
        self._primary_menu.addAction(default_action)
        self._primary_menu.addSeparator()

        devices = self._devices()
        if not devices:
            placeholder = QAction("(no devices found)", self)
            placeholder.setEnabled(False)
            self._primary_menu.addAction(placeholder)
            return
        for name in devices:
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(name == current)
            action.triggered.connect(lambda _checked=False, n=name: self._set_primary(n))
            self._primary_group.addAction(action)
            self._primary_menu.addAction(action)

    def _rebuild_monitor_menu(self) -> None:
        if self._monitor_menu is None:
            return
        self._monitor_menu.clear()
        self._monitor_group = QActionGroup(self)
        self._monitor_group.setExclusive(True)

        current = self._current_settings().monitor_device
        none_action = QAction("&None (off)", self)
        none_action.setCheckable(True)
        none_action.setChecked(current is None)
        none_action.triggered.connect(lambda: self._set_monitor(None))
        self._monitor_group.addAction(none_action)
        self._monitor_menu.addAction(none_action)
        self._monitor_menu.addSeparator()

        devices = self._devices()
        if not devices:
            placeholder = QAction("(no devices found)", self)
            placeholder.setEnabled(False)
            self._monitor_menu.addAction(placeholder)
            return
        for name in devices:
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(name == current)
            action.triggered.connect(lambda _checked=False, n=name: self._set_monitor(n))
            self._monitor_group.addAction(action)
            self._monitor_menu.addAction(action)

    def _rebuild_player(self, settings: Settings) -> None:
        devices: list[str | None] = [settings.output_device]
        if settings.monitor_device is not None:
            devices.append(settings.monitor_device)
        old = self._player
        try:
            self._player = self._player_factory(devices=devices)
        finally:
            with contextlib.suppress(Exception):
                old.close()

    def _set_primary(self, device_name: str | None) -> None:
        if self._settings_repository is None:
            return
        current = self._settings_repository.load()
        new = Settings(output_device=device_name, monitor_device=current.monitor_device)
        self._settings_repository.save(new)
        self._rebuild_player(new)
        label = device_name or "system default"
        self.statusBar().showMessage(f"Output device → {label}")

    def _set_monitor(self, device_name: str | None) -> None:
        if self._settings_repository is None:
            return
        current = self._settings_repository.load()
        new = Settings(output_device=current.output_device, monitor_device=device_name)
        self._settings_repository.save(new)
        self._rebuild_player(new)
        label = device_name or "off"
        self.statusBar().showMessage(f"Monitor device → {label}")

    def _clear_grid(self) -> None:
        for btn in self._buttons:
            btn.setParent(None)
            btn.deleteLater()
        self._buttons.clear()
        for sc in self._shortcuts:
            sc.setParent(None)
            sc.deleteLater()
        self._shortcuts.clear()

    def _reload(self) -> None:
        library = self._repository.load()
        self._clear_grid()
        for sound in library:
            button = SoundButton(sound, self._grid_container)
            button.clicked.connect(lambda _=False, s=sound: self._play(s))
            button.customContextMenuRequested.connect(
                lambda pos, b=button: self._show_context_menu(b, pos)
            )
            self._buttons.append(button)
            if sound.hotkey:
                try:
                    shortcut = QShortcut(QKeySequence(sound.hotkey), self)
                except Exception:  # noqa: BLE001
                    continue
                shortcut.activated.connect(lambda s=sound: self._play(s))
                self._shortcuts.append(shortcut)
        self._apply_layout()
        self.statusBar().showMessage(f"{len(self._buttons)} sound(s) loaded")

    def _apply_layout(self) -> None:
        while self._grid.count():
            self._grid.takeAt(0)
        needle = self._filter_text.strip().lower()
        visible = [b for b in self._buttons if _matches(b.sound, needle)]
        for b in self._buttons:
            b.setVisible(b in set(visible))
        for i, b in enumerate(visible):
            self._grid.addWidget(b, i // GRID_COLUMNS, i % GRID_COLUMNS)

    def _on_filter_changed(self, text: str) -> None:
        self._filter_text = text
        self._apply_layout()

    def _play(self, sound: Sound) -> None:
        try:
            self._player.play(sound)
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"Error: {e}")
            return
        self.statusBar().showMessage(f"▶ {sound.name}")

    def _stop_all(self) -> None:
        self._player.stop_all()
        self.statusBar().showMessage("Stopped all.")

    def _show_context_menu(self, button: SoundButton, pos: object) -> None:
        menu = QMenu(self)
        remove = menu.addAction("Remove from library")
        action = menu.exec(button.mapToGlobal(pos))  # type: ignore[arg-type]
        if action is remove:
            self._remove_sound(button.sound)

    def _remove_sound(self, sound: Sound) -> None:
        library = self._repository.load()
        try:
            library.remove(sound.id)
        except SoundNotFoundError:
            return
        self._repository.save(library)
        self._reload()
        self.statusBar().showMessage(f"Removed '{sound.name}'")

    def _import_sound(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Import sound",
            "",
            "Audio files (*.wav *.ogg *.mp3 *.flac);;All files (*)",
        )
        if not path_str:
            return
        self.import_sound(Path(path_str))

    def import_sound(self, source: Path, *, name: str | None = None) -> Sound | None:
        source = source.expanduser().resolve()
        if not source.is_file():
            QMessageBox.warning(self, "Import failed", f"Not a file: {source}")
            return None
        library = self._repository.load()
        sound_id = uuid.uuid4().hex[:12]
        target = self._paths.sounds_dir / f"{sound_id}{source.suffix}"
        shutil.copy2(source, target)
        sound = Sound(id=sound_id, name=name or source.stem, path=target)
        try:
            library.add(sound)
        except SoundAlreadyExistsError as e:
            QMessageBox.warning(self, "Import failed", str(e))
            target.unlink(missing_ok=True)
            return None
        self._repository.save(library)
        self._reload()
        self.statusBar().showMessage(f"Added '{sound.name}'")
        return sound

    @property
    def buttons(self) -> list[SoundButton]:
        return list(self._buttons)

    def visible_buttons(self) -> list[SoundButton]:
        return [b for b in self._buttons if b.isVisibleTo(self._grid_container)]


def _matches(sound: Sound, needle: str) -> bool:
    if not needle:
        return True
    if needle in sound.name.lower():
        return True
    return any(needle in tag.lower() for tag in sound.tags)


def main() -> None:
    paths = default_paths()
    paths.ensure()
    repository = TomlLibraryRepository(paths.library_file)
    settings_repository = TomlSettingsRepository(paths.settings_file)
    settings = settings_repository.load()
    devices: list[str | None] = [settings.output_device]
    if settings.monitor_device is not None:
        devices.append(settings.monitor_device)
    player = SoundDevicePlayer(devices=devices)
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(
        paths=paths,
        repository=repository,
        player=player,
        settings_repository=settings_repository,
    )
    window.show()
    try:
        sys.exit(app.exec())
    finally:
        player.close()


if __name__ == "__main__":
    main()
