from __future__ import annotations

import contextlib
import dataclasses
from collections.abc import Callable
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from soundboard.audio.devices import list_output_devices
from soundboard.audio.player import Player
from soundboard.audio.sounddevice_player import SoundDevicePlayer
from soundboard.config import default_paths
from soundboard.core.colors import effective_color, parse_color, text_color_for
from soundboard.core.library import SoundAlreadyExistsError
from soundboard.core.models import Sound
from soundboard.settings import Settings, SettingsRepository, TomlSettingsRepository
from soundboard.storage.repository import LibraryRepository
from soundboard.storage.toml_repository import TomlLibraryRepository

PlayerFactory = Callable[..., Player]
NO_DEVICE_VALUE = "__none__"

SIZE_PRESETS: tuple[tuple[int, int], ...] = (
    (6, 2),  # small
    (4, 3),  # medium (default)
    (3, 5),  # large
    (2, 7),  # x-large
)
DEFAULT_SIZE_INDEX = 1


def _clamp_size_index(value: int | None) -> int:
    if value is None:
        return DEFAULT_SIZE_INDEX
    return max(0, min(len(SIZE_PRESETS) - 1, value))


class SoundButton(Button):
    def __init__(self, sound: Sound) -> None:
        label = sound.name if not sound.hotkey else f"{sound.name}  [{sound.hotkey}]"
        super().__init__(label, classes="sound-button")
        self.sound = sound
        cap = effective_color(sound)
        self.cap_color = cap
        self.styles.background = cap
        self.styles.color = text_color_for(cap)


class EditSoundScreen(ModalScreen[Sound | None]):
    DEFAULT_CSS = """
    EditSoundScreen {
        align: center middle;
    }
    #edit-dialog {
        width: 64;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: tall $primary;
    }
    #edit-dialog Input { margin-bottom: 1; }
    #edit-buttons { height: 3; align: right middle; }
    #edit-buttons Button { margin-left: 1; }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, sound: Sound) -> None:
        super().__init__()
        self._sound = sound

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-dialog"):
            yield Label(f"Edit '{self._sound.name}'")
            yield Input(value=self._sound.name, placeholder="Name", id="edit-name")
            yield Input(
                value=self._sound.hotkey or "",
                placeholder="Hotkey (blank to clear)",
                id="edit-hotkey",
            )
            yield Input(
                value=f"{self._sound.volume:.2f}",
                placeholder="Volume (0.0 – 1.0)",
                id="edit-volume",
            )
            yield Input(
                value=self._sound.color or "",
                placeholder="Colour (hex or named, blank for default)",
                id="edit-color",
            )
            yield Input(
                value=", ".join(self._sound.tags),
                placeholder="Tags (comma-separated)",
                id="edit-tags",
            )
            with Horizontal(id="edit-buttons"):
                yield Button("Cancel", id="edit-cancel")
                yield Button("OK", id="edit-ok", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "edit-ok":
            self._submit()
        elif event.button.id == "edit-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        try:
            updated = self._build_sound()
        except ValueError as e:
            self.app.notify(str(e), severity="error")
            return
        self.dismiss(updated)

    def _build_sound(self) -> Sound:
        name = self.query_one("#edit-name", Input).value.strip() or self._sound.name
        hotkey_text = self.query_one("#edit-hotkey", Input).value.strip()
        hotkey = hotkey_text or None
        volume_text = self.query_one("#edit-volume", Input).value.strip()
        try:
            volume = float(volume_text)
        except ValueError as e:
            raise ValueError(f"invalid volume: {volume_text!r}") from e
        color_text = self.query_one("#edit-color", Input).value.strip()
        color = parse_color(color_text) if color_text else None
        tags_text = self.query_one("#edit-tags", Input).value.strip()
        tags = (
            tuple(t.strip() for t in tags_text.split(",") if t.strip())
            if tags_text
            else ()
        )
        return dataclasses.replace(
            self._sound,
            name=name,
            hotkey=hotkey,
            volume=volume,
            tags=tags,
            color=color,
        )


class DeviceSettingsScreen(ModalScreen[Settings | None]):
    DEFAULT_CSS = """
    DeviceSettingsScreen {
        align: center middle;
    }
    #device-dialog {
        width: 72;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: tall $primary;
    }
    #device-dialog Label { margin-top: 1; }
    #device-dialog Select { margin-bottom: 1; }
    #device-buttons { height: 3; align: right middle; }
    #device-buttons Button { margin-left: 1; }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, current: Settings, devices: list[str]) -> None:
        super().__init__()
        self._current = current
        self._devices = devices

    def compose(self) -> ComposeResult:
        with Vertical(id="device-dialog"):
            yield Label("Audio devices")
            yield Label("Primary")
            yield Select(
                [("(system default)", NO_DEVICE_VALUE)]
                + [(name, name) for name in self._devices],
                value=self._current.output_device or NO_DEVICE_VALUE,
                allow_blank=False,
                id="primary-select",
            )
            yield Label("Monitor")
            yield Select(
                [("(off)", NO_DEVICE_VALUE)]
                + [(name, name) for name in self._devices],
                value=self._current.monitor_device or NO_DEVICE_VALUE,
                allow_blank=False,
                id="monitor-select",
            )
            with Horizontal(id="device-buttons"):
                yield Button("Cancel", id="device-cancel")
                yield Button("OK", id="device-ok", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "device-ok":
            primary_raw = self.query_one("#primary-select", Select).value
            monitor_raw = self.query_one("#monitor-select", Select).value
            primary = None if primary_raw == NO_DEVICE_VALUE else str(primary_raw)
            monitor = None if monitor_raw == NO_DEVICE_VALUE else str(monitor_raw)
            self.dismiss(
                dataclasses.replace(
                    self._current,
                    output_device=primary,
                    monitor_device=monitor,
                )
            )
        elif event.button.id == "device-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SoundboardApp(App[None]):
    CSS = """
    Screen { layout: vertical; }
    #search { dock: top; margin: 1 2; }
    #grid {
        grid-size: 4;
        grid-gutter: 1 2;
        padding: 1 2;
        grid-rows: 3;
    }
    SoundButton { width: 100%; height: 3; }
    .empty { content-align: center middle; color: $text-muted; height: 100%; }
    #status { dock: bottom; height: 1; padding: 0 2; color: $accent; }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("escape", "stop_all", "Stop all", show=True),
        Binding("slash", "focus_search", "Search", show=True),
        Binding("r", "reload", "Reload", show=True),
        Binding("e", "edit_focused", "Edit", show=True),
        Binding("d", "devices", "Devices", show=True),
        Binding("plus,equals_sign", "resize_up", "Bigger", show=True),
        Binding("minus", "resize_down", "Smaller", show=True),
    ]

    filter_text: reactive[str] = reactive("")

    def __init__(
        self,
        repository: LibraryRepository,
        player: Player,
        settings: Settings | None = None,
        settings_repository: SettingsRepository | None = None,
        device_lister: Callable[[], list[str]] = list_output_devices,
        player_factory: PlayerFactory | None = None,
    ) -> None:
        super().__init__()
        self._repository = repository
        self._player = player
        self._settings = settings or Settings()
        self._settings_repository = settings_repository
        self._device_lister = device_lister
        self._player_factory = player_factory
        self._sounds: list[Sound] = []
        self._size_idx = _clamp_size_index(self._settings.tui_button_size)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Filter by name or tag…", id="search")
        yield Vertical(Grid(id="grid"), Static("", id="status"))
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Soundboard"
        primary = self._settings.output_device or "system default"
        monitor = self._settings.monitor_device or "off"
        self.sub_title = f"Primary: {primary}  |  Monitor: {monitor}"
        self.run_worker(self._reload, exclusive=True, group="render")

    async def _reload(self) -> None:
        self._sounds = list(self._repository.load())
        for sound in self._sounds:
            if sound.hotkey:
                self.bind(
                    sound.hotkey,
                    f"play_id('{sound.id}')",
                    description=f"Play {sound.name}",
                )
        grid = self.query_one("#grid", Grid)
        await grid.remove_children()
        if not self._sounds:
            await grid.mount(Static("No sounds.", classes="empty"))
        else:
            await grid.mount_all([SoundButton(s) for s in self._sounds])
        self._apply_size()
        self._apply_filter()

    def _apply_size(self) -> None:
        cols, rows = SIZE_PRESETS[self._size_idx]
        grid = self.query_one("#grid", Grid)
        grid.styles.grid_size_columns = cols
        grid.styles.grid_rows = [rows]
        for btn in self.query(SoundButton):
            btn.styles.height = rows

    def _persist_size(self) -> None:
        if self._settings_repository is None:
            return
        current = self._settings_repository.load()
        self._settings_repository.save(
            dataclasses.replace(current, tui_button_size=self._size_idx)
        )

    def _apply_filter(self) -> None:
        needle = self.filter_text.strip().lower()
        visible = 0
        for btn in self.query(SoundButton):
            show = _matches(btn.sound, needle)
            btn.display = show
            if show:
                visible += 1
        try:
            empty = self.query_one(".empty", Static)
        except Exception:
            empty = None
        if self._sounds and visible == 0:
            if empty is None:
                self.query_one("#grid", Grid).mount(
                    Static("No matches.", classes="empty")
                )
            else:
                empty.update("No matches.")
                empty.display = True
        elif empty is not None and self._sounds:
            empty.display = False

    def watch_filter_text(self, _old: str, _new: str) -> None:
        if self.is_mounted:
            self._apply_filter()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self.filter_text = event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if isinstance(event.button, SoundButton):
            self._play(event.button.sound)

    def _play(self, sound: Sound) -> None:
        try:
            self._player.play(sound)
        except Exception as e:  # noqa: BLE001
            self._status(f"Error: {e}", error=True)
            return
        self._status(f"▶ {sound.name}")

    def _status(self, message: str, *, error: bool = False) -> None:
        widget = self.query_one("#status", Static)
        widget.update(f"[red]{message}[/red]" if error else message)

    def action_stop_all(self) -> None:
        self._player.stop_all()
        self._status("Stopped all.")

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_reload(self) -> None:
        self.run_worker(self._reload, exclusive=True, group="render")
        self._status("Library reloaded.")

    def action_play_id(self, sound_id: str) -> None:
        for sound in self._sounds:
            if sound.id == sound_id:
                self._play(sound)
                return

    def action_resize_up(self) -> None:
        if self._size_idx >= len(SIZE_PRESETS) - 1:
            return
        self._size_idx += 1
        self._apply_size()
        self._persist_size()
        self._status(f"Size → {self._size_idx + 1}/{len(SIZE_PRESETS)}")

    def action_resize_down(self) -> None:
        if self._size_idx <= 0:
            return
        self._size_idx -= 1
        self._apply_size()
        self._persist_size()
        self._status(f"Size → {self._size_idx + 1}/{len(SIZE_PRESETS)}")

    def action_devices(self) -> None:
        try:
            devices = self._device_lister()
        except Exception as e:  # noqa: BLE001
            self._status(f"Could not enumerate devices: {e}", error=True)
            return
        current = (
            self._settings_repository.load()
            if self._settings_repository is not None
            else self._settings
        )
        self.push_screen(
            DeviceSettingsScreen(current, devices), self._on_devices_changed
        )

    def _on_devices_changed(self, updated: Settings | None) -> None:
        if updated is None:
            return
        if self._settings_repository is not None:
            self._settings_repository.save(updated)
        self._settings = updated
        self._rebuild_player(updated)
        primary = updated.output_device or "system default"
        monitor = updated.monitor_device or "off"
        self.sub_title = f"Primary: {primary}  |  Monitor: {monitor}"
        self._status(f"Audio: primary={primary}, monitor={monitor}")

    def _rebuild_player(self, settings: Settings) -> None:
        if self._player_factory is None:
            return
        devices: list[str | None] = [settings.output_device]
        if settings.monitor_device is not None:
            devices.append(settings.monitor_device)
        old = self._player
        try:
            self._player = self._player_factory(devices=devices)
        finally:
            with contextlib.suppress(Exception):
                old.close()

    def action_edit_focused(self) -> None:
        focused = self.focused
        if not isinstance(focused, SoundButton):
            self._status("Focus a sound (Tab) before pressing Edit.", error=True)
            return
        self.push_screen(EditSoundScreen(focused.sound), self._on_edit_done)

    def _on_edit_done(self, updated: Sound | None) -> None:
        if updated is None:
            return
        library = self._repository.load()
        try:
            library.update(updated)
        except SoundAlreadyExistsError as e:
            self._status(str(e), error=True)
            return
        self._repository.save(library)
        self.run_worker(self._reload, exclusive=True, group="render")
        self._status(f"Updated '{updated.name}'")


def _matches(sound: Sound, needle: str) -> bool:
    if not needle:
        return True
    if needle in sound.name.lower():
        return True
    return any(needle in tag.lower() for tag in sound.tags)


def main() -> None:
    paths = default_paths()
    paths.ensure()
    repo = TomlLibraryRepository(paths.library_file)
    settings_repo = TomlSettingsRepository(paths.settings_file)
    settings = settings_repo.load()
    devices: list[str | None] = [settings.output_device]
    if settings.monitor_device is not None:
        devices.append(settings.monitor_device)
    player = SoundDevicePlayer(devices=devices)
    app = SoundboardApp(
        repo,
        player,
        settings,
        settings_repository=settings_repo,
        player_factory=SoundDevicePlayer,
    )
    try:
        app.run()
    finally:
        # The app may have rebuilt the player while running.
        with contextlib.suppress(Exception):
            app._player.close()


if __name__ == "__main__":
    main()
