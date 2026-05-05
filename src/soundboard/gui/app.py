from __future__ import annotations

import contextlib
import shutil
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from soundboard.audio.devices import list_output_devices
from soundboard.audio.player import Player
from soundboard.audio.sounddevice_player import SoundDevicePlayer
from soundboard.config import Paths, default_paths
from soundboard.core.colors import (
    darken,
    effective_color,
    lighten,
    text_color_for,
)
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

DEFAULT_BUTTON_SIZE = 120
MIN_BUTTON_SIZE = 64
MAX_BUTTON_SIZE = 220
GRID_SPACING = 16
GRID_MARGIN = 16


def _arcade_qss(cap_hex: str, size: int) -> str:
    text = text_color_for(cap_hex)
    rim = darken(cap_hex, 0.5)
    bright = lighten(cap_hex, 0.45)
    base = cap_hex
    deep = darken(cap_hex, 0.3)
    pressed_top = darken(cap_hex, 0.05)
    pressed_bottom = darken(cap_hex, 0.45)
    font_pt = max(8, min(16, size // 10))
    return (
        "SoundButton {"
        f" background: qradialgradient(cx:0.5, cy:0.32, radius:0.95,"
        f" fx:0.5, fy:0.28, stop:0 {bright}, stop:0.55 {base}, stop:1 {deep});"
        f" border: 2px solid {rim};"
        f" border-radius: {size // 2}px;"
        f" color: {text};"
        " font-weight: bold;"
        f" font-size: {font_pt}pt;"
        " padding: 0;"
        "}"
        "SoundButton:pressed {"
        f" background: qradialgradient(cx:0.5, cy:0.5, radius:0.85,"
        f" fx:0.5, fy:0.5, stop:0 {pressed_top}, stop:1 {pressed_bottom});"
        " padding-top: 4px;"
        "}"
    )


class SoundButton(QPushButton):
    def __init__(
        self,
        sound: Sound,
        parent: QWidget | None = None,
        size: int = DEFAULT_BUTTON_SIZE,
    ) -> None:
        label = sound.name if not sound.hotkey else f"{sound.name}\n[{sound.hotkey}]"
        super().__init__(label, parent)
        self.sound = sound
        self.cap_color = effective_color(sound)
        self.set_button_size(size)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 128))
        self.setGraphicsEffect(shadow)

    def set_button_size(self, size: int) -> None:
        self.setFixedSize(size, size)
        self.setStyleSheet(_arcade_qss(self.cap_color, size))


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
        self._button_size = DEFAULT_BUTTON_SIZE
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

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        self._search = QLineEdit(central)
        self._search.setPlaceholderText("Filter by name or tag…")
        self._search.textChanged.connect(self._on_filter_changed)
        top_row.addWidget(self._search, 1)

        size_label = QLabel("Size", central)
        top_row.addWidget(size_label)
        self._size_slider = QSlider(Qt.Orientation.Horizontal, central)
        self._size_slider.setMinimum(MIN_BUTTON_SIZE)
        self._size_slider.setMaximum(MAX_BUTTON_SIZE)
        self._size_slider.setValue(self._button_size)
        self._size_slider.setFixedWidth(140)
        self._size_slider.valueChanged.connect(self._on_size_changed)
        top_row.addWidget(self._size_slider)
        layout.addLayout(top_row)

        self._scroll = QScrollArea(central)
        self._scroll.setWidgetResizable(True)
        layout.addWidget(self._scroll, 1)

        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(GRID_MARGIN, GRID_MARGIN, GRID_MARGIN, GRID_MARGIN)
        self._grid.setHorizontalSpacing(GRID_SPACING)
        self._grid.setVerticalSpacing(GRID_SPACING)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
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
            button = SoundButton(sound, self._grid_container, size=self._button_size)
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

    def _columns(self) -> int:
        viewport_w = self._scroll.viewport().width()
        usable = max(0, viewport_w - 2 * GRID_MARGIN)
        cell = self._button_size + GRID_SPACING
        if cell <= 0:
            return 1
        return max(1, (usable + GRID_SPACING) // cell)

    def _apply_layout(self) -> None:
        while self._grid.count():
            self._grid.takeAt(0)
        needle = self._filter_text.strip().lower()
        visible = [b for b in self._buttons if _matches(b.sound, needle)]
        visible_set = set(visible)
        for b in self._buttons:
            b.setVisible(b in visible_set)
        cols = self._columns()
        for i, b in enumerate(visible):
            self._grid.addWidget(b, i // cols, i % cols)

    def _on_filter_changed(self, text: str) -> None:
        self._filter_text = text
        self._apply_layout()

    def _on_size_changed(self, size: int) -> None:
        self._button_size = size
        for button in self._buttons:
            button.set_button_size(size)
        self._apply_layout()
        self.statusBar().showMessage(f"Button size → {size}px")

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
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
