from __future__ import annotations

from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Input, Static

from soundboard.audio.player import Player
from soundboard.audio.pygame_player import PygamePlayer
from soundboard.config import default_paths
from soundboard.core.models import Sound
from soundboard.settings import Settings, TomlSettingsRepository
from soundboard.storage.repository import LibraryRepository
from soundboard.storage.toml_repository import TomlLibraryRepository


class SoundButton(Button):
    def __init__(self, sound: Sound) -> None:
        label = sound.name if not sound.hotkey else f"{sound.name}  [{sound.hotkey}]"
        super().__init__(label, classes="sound-button")
        self.sound = sound


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
    ]

    filter_text: reactive[str] = reactive("")

    def __init__(
        self,
        repository: LibraryRepository,
        player: Player,
        settings: Settings | None = None,
    ) -> None:
        super().__init__()
        self._repository = repository
        self._player = player
        self._settings = settings or Settings()
        self._sounds: list[Sound] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Filter by name or tag…", id="search")
        yield Vertical(Grid(id="grid"), Static("", id="status"))
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Soundboard"
        self.sub_title = (
            f"Output: {self._settings.output_device}"
            if self._settings.output_device
            else "Output: system default"
        )
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
        self._apply_filter()

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
    settings = TomlSettingsRepository(paths.settings_file).load()
    player = PygamePlayer(device_name=settings.output_device)
    try:
        SoundboardApp(repo, player, settings).run()
    finally:
        player.close()


if __name__ == "__main__":
    main()
