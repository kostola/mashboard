from __future__ import annotations

import dataclasses
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from soundboard.audio.devices import list_output_devices
from soundboard.audio.fetcher import Downloader, parse_timecode, ytdlp_download
from soundboard.audio.player import Player
from soundboard.audio.sounddevice_player import SoundDevicePlayer
from soundboard.config import Paths, default_paths
from soundboard.core.colors import effective_color, parse_color
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

PlayerFactory = Callable[..., Player]

app = typer.Typer(help="Soundboard CLI — manage and play your sound library.")
config_app = typer.Typer(help="View and change soundboard settings.")
app.add_typer(config_app, name="config")
console = Console()


@dataclass(slots=True)
class Context:
    paths: Paths
    repository: LibraryRepository
    settings_repository: SettingsRepository
    player_factory: PlayerFactory | None
    device_lister: Callable[[], list[str]] = list_output_devices
    downloader: Downloader = ytdlp_download


def _build_default_context() -> Context:
    paths = default_paths()
    paths.ensure()
    return Context(
        paths=paths,
        repository=TomlLibraryRepository(paths.library_file),
        settings_repository=TomlSettingsRepository(paths.settings_file),
        player_factory=SoundDevicePlayer,
    )


_ctx: Context | None = None


def _context() -> Context:
    global _ctx
    if _ctx is None:
        _ctx = _build_default_context()
    return _ctx


def set_context(context: Context) -> None:
    """Inject a context (used by tests)."""
    global _ctx
    _ctx = context


def _copy_into_library(paths: Paths, source: Path, sound_id: str) -> Path:
    target = paths.sounds_dir / f"{sound_id}{source.suffix}"
    shutil.copy2(source, target)
    return target


def _make_player(ctx: Context) -> Player:
    if ctx.player_factory is None:
        raise typer.Exit(code=1)
    settings = ctx.settings_repository.load()
    devices: list[str | None] = [settings.output_device]
    if settings.monitor_device is not None:
        devices.append(settings.monitor_device)
    return ctx.player_factory(devices=devices)


@app.command("add")
def add(
    path: Annotated[Path, typer.Argument(help="Audio file to import.")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Display name.")] = None,
    hotkey: Annotated[str | None, typer.Option("--hotkey", "-k")] = None,
    tag: Annotated[list[str] | None, typer.Option("--tag", "-t", help="Repeatable.")] = None,
    volume: Annotated[float, typer.Option("--volume", "-v", min=0.0, max=1.0)] = 1.0,
    color: Annotated[
        str | None, typer.Option("--color", "-c", help="Hex (#rrggbb) or named colour.")
    ] = None,
    link: Annotated[bool, typer.Option("--link", help="Reference in place, don't copy.")] = False,
) -> None:
    """Register a sound."""
    ctx = _context()
    source = path.expanduser().resolve()
    if not source.is_file():
        console.print(f"[red]File not found:[/red] {source}")
        raise typer.Exit(code=2)

    color_hex: str | None = None
    if color is not None:
        try:
            color_hex = parse_color(color)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=2) from e

    library = ctx.repository.load()
    sound_id = uuid.uuid4().hex[:12]
    stored_path = source if link else _copy_into_library(ctx.paths, source, sound_id)
    sound = Sound(
        id=sound_id,
        name=name or source.stem,
        path=stored_path,
        hotkey=hotkey,
        tags=tuple(tag or ()),
        volume=volume,
        color=color_hex,
    )
    try:
        library.add(sound)
    except SoundAlreadyExistsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    ctx.repository.save(library)
    console.print(f"[green]Added[/green] '{sound.name}' ([dim]{sound.id}[/dim])")


@app.command("fetch")
def fetch(
    url: Annotated[str, typer.Argument(help="YouTube (or yt-dlp-supported) URL.")],
    start: Annotated[
        str | None, typer.Option("--start", "-s", help="Start time (SS, MM:SS, or H:MM:SS).")
    ] = None,
    end: Annotated[
        str | None, typer.Option("--end", "-e", help="End time (SS, MM:SS, or H:MM:SS).")
    ] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Display name.")] = None,
    hotkey: Annotated[str | None, typer.Option("--hotkey", "-k")] = None,
    tag: Annotated[list[str] | None, typer.Option("--tag", "-t", help="Repeatable.")] = None,
    volume: Annotated[float, typer.Option("--volume", "-v", min=0.0, max=1.0)] = 1.0,
    color: Annotated[
        str | None, typer.Option("--color", "-c", help="Hex (#rrggbb) or named colour.")
    ] = None,
) -> None:
    """Download a clip from a URL (YouTube et al.) and register it."""
    ctx = _context()
    if (start is None) != (end is None):
        console.print("[red]--start and --end must be provided together[/red]")
        raise typer.Exit(code=2)
    try:
        start_sec = parse_timecode(start) if start is not None else None
        end_sec = parse_timecode(end) if end is not None else None
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2) from e
    if start_sec is not None and end_sec is not None and start_sec >= end_sec:
        console.print("[red]start must be before end[/red]")
        raise typer.Exit(code=2)
    color_hex: str | None = None
    if color is not None:
        try:
            color_hex = parse_color(color)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=2) from e

    try:
        downloaded = ctx.downloader(url, start_sec, end_sec, ctx.paths.sounds_dir)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Download failed:[/red] {e}")
        raise typer.Exit(code=1) from e

    library = ctx.repository.load()
    sound_id = uuid.uuid4().hex[:12]
    stored_path = ctx.paths.sounds_dir / f"{sound_id}{downloaded.suffix}"
    downloaded.rename(stored_path)
    sound = Sound(
        id=sound_id,
        name=name or stored_path.stem,
        path=stored_path,
        hotkey=hotkey,
        tags=tuple(tag or ()),
        volume=volume,
        color=color_hex,
    )
    try:
        library.add(sound)
    except SoundAlreadyExistsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    ctx.repository.save(library)
    console.print(f"[green]Fetched[/green] '{sound.name}' ([dim]{sound.id}[/dim])")


@app.command("edit")
def edit(
    name: Annotated[str, typer.Argument(help="Sound name or id.")],
    new_name: Annotated[str | None, typer.Option("--name", "-n", help="Rename.")] = None,
    hotkey: Annotated[
        str | None, typer.Option("--hotkey", "-k", help="Set the hotkey.")
    ] = None,
    clear_hotkey: Annotated[
        bool, typer.Option("--clear-hotkey", help="Remove the hotkey.")
    ] = False,
    volume: Annotated[
        float | None,
        typer.Option("--volume", "-v", min=0.0, max=1.0, help="Set volume (0.0–1.0)."),
    ] = None,
    add_tag: Annotated[
        list[str] | None, typer.Option("--add-tag", help="Add a tag (repeatable).")
    ] = None,
    remove_tag: Annotated[
        list[str] | None, typer.Option("--remove-tag", help="Remove a tag (repeatable).")
    ] = None,
    color: Annotated[
        str | None,
        typer.Option("--color", "-c", help="Set the colour (hex or named)."),
    ] = None,
    clear_color: Annotated[
        bool, typer.Option("--clear-color", help="Remove the colour.")
    ] = False,
) -> None:
    """Edit a sound's metadata in place."""
    ctx = _context()
    library = ctx.repository.load()
    try:
        sound = library.find(name)
    except SoundNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    changes: dict[str, object] = {}
    if new_name is not None:
        if not new_name:
            console.print("[red]--name cannot be empty[/red]")
            raise typer.Exit(code=2)
        changes["name"] = new_name
    if clear_hotkey and hotkey is not None:
        console.print("[red]Cannot combine --hotkey and --clear-hotkey[/red]")
        raise typer.Exit(code=2)
    if clear_hotkey:
        changes["hotkey"] = None
    elif hotkey is not None:
        changes["hotkey"] = hotkey
    if clear_color and color is not None:
        console.print("[red]Cannot combine --color and --clear-color[/red]")
        raise typer.Exit(code=2)
    if clear_color:
        changes["color"] = None
    elif color is not None:
        try:
            changes["color"] = parse_color(color)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=2) from e
    if volume is not None:
        changes["volume"] = volume
    if add_tag or remove_tag:
        tags = list(sound.tags)
        for t in remove_tag or []:
            if t in tags:
                tags.remove(t)
        for t in add_tag or []:
            if t not in tags:
                tags.append(t)
        changes["tags"] = tuple(tags)

    if not changes:
        console.print("[yellow]Nothing to change. See `soundboard edit --help`.[/yellow]")
        return

    updated = dataclasses.replace(sound, **changes)
    try:
        library.update(updated)
    except SoundAlreadyExistsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    ctx.repository.save(library)
    diff = ", ".join(f"{k}={v!r}" for k, v in changes.items())
    console.print(f"[green]Updated[/green] '{updated.name}' ({diff})")


@app.command("remove")
def remove(name: Annotated[str, typer.Argument(help="Sound name or id.")]) -> None:
    """Remove a sound from the library (file on disk is kept)."""
    ctx = _context()
    library = ctx.repository.load()
    try:
        sound = library.remove(name)
    except SoundNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    ctx.repository.save(library)
    console.print(f"[green]Removed[/green] '{sound.name}'")


@app.command("list")
def list_sounds(
    tag: Annotated[str | None, typer.Option("--tag", "-t")] = None,
) -> None:
    """List all sounds."""
    library = _context().repository.load()
    sounds: list[Sound] = library.search(tag) if tag else list(library)
    if not sounds:
        console.print("[dim]No sounds.[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    for col in ("", "Name", "Id", "Hotkey", "Tags", "Vol", "Path"):
        table.add_column(col)
    for s in sounds:
        cap = effective_color(s)
        swatch = f"[{cap}]●[/{cap}]"
        table.add_row(
            swatch,
            s.name,
            s.id,
            s.hotkey or "-",
            ", ".join(s.tags) or "-",
            f"{s.volume:.2f}",
            str(s.path),
        )
    console.print(table)


@app.command("play")
def play(
    name: Annotated[str, typer.Argument(help="Sound name or id.")],
    no_wait: Annotated[bool, typer.Option("--no-wait", help="Return immediately.")] = False,
) -> None:
    """Play a sound."""
    ctx = _context()
    library = ctx.repository.load()
    try:
        sound = library.find(name)
    except SoundNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    if ctx.player_factory is None:
        console.print("[red]No audio player configured.[/red]")
        raise typer.Exit(code=1)
    player = _make_player(ctx)
    try:
        handle = player.play(sound)
        console.print(f"[green]Playing[/green] '{sound.name}'")
        if not no_wait:
            try:
                handle.wait()
            except KeyboardInterrupt:
                handle.stop()
                console.print("[yellow]Stopped.[/yellow]")
    finally:
        player.close()


@app.command("stop")
def stop() -> None:
    """Stop all playback on this player instance (no-op across processes)."""
    ctx = _context()
    if ctx.player_factory is None:
        return
    player = _make_player(ctx)
    try:
        player.stop_all()
    finally:
        player.close()
    console.print("[green]Stopped all.[/green]")


@app.command("where")
def where() -> None:
    """Show config and data paths."""
    ctx = _context()
    console.print(f"Library file:  [bold]{ctx.paths.library_file}[/bold]")
    console.print(f"Settings file: [bold]{ctx.paths.settings_file}[/bold]")
    console.print(f"Sounds dir:    [bold]{ctx.paths.sounds_dir}[/bold]")


@app.command("devices")
def devices() -> None:
    """List available audio output devices."""
    ctx = _context()
    settings = ctx.settings_repository.load()
    primary = settings.output_device
    monitor = settings.monitor_device
    try:
        names = ctx.device_lister()
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Could not enumerate devices:[/red] {e}")
        raise typer.Exit(code=1) from e
    if not names:
        console.print("[dim]No output devices found.[/dim]")
        return

    def _marker(name: str | None) -> str:
        flags = ""
        if primary == name and (name is not None or primary is None):
            flags += "P"
        if monitor is not None and monitor == name:
            flags += "M"
        return f"[green]{flags}[/green]" if flags else " "

    table = Table(show_header=True, header_style="bold")
    table.add_column("")
    table.add_column("Device name")
    table.add_row(_marker(None), "[dim](system default)[/dim]")
    for name in names:
        table.add_row(_marker(name), name)
    console.print(table)


@config_app.command("show")
def config_show() -> None:
    """Show current settings."""
    ctx = _context()
    settings = ctx.settings_repository.load()
    primary = settings.output_device or "[dim](system default)[/dim]"
    monitor = settings.monitor_device or "[dim](off)[/dim]"
    console.print(f"Output device:  [bold]{primary}[/bold]")
    console.print(f"Monitor device: [bold]{monitor}[/bold]")


@config_app.command("set-device")
def config_set_device(
    name: Annotated[
        str | None,
        typer.Argument(help='Device name (use "" or --clear for system default).'),
    ] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Reset to system default.")] = False,
) -> None:
    """Set the primary audio output device used for playback."""
    ctx = _context()
    chosen: str | None = None if clear or not name else name
    current = ctx.settings_repository.load()
    ctx.settings_repository.save(
        Settings(
            output_device=chosen,
            monitor_device=current.monitor_device,
            gui_button_size=current.gui_button_size,
        )
    )
    if chosen is None:
        console.print("[green]Output device[/green] -> system default")
    else:
        console.print(f"[green]Output device[/green] -> {chosen}")


@config_app.command("set-monitor")
def config_set_monitor(
    name: Annotated[
        str | None,
        typer.Argument(help='Monitor device name (use "" or --clear to disable).'),
    ] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Disable the monitor output.")] = False,
) -> None:
    """Set a second output device that mirrors playback (preview/monitor)."""
    ctx = _context()
    chosen: str | None = None if clear or not name else name
    current = ctx.settings_repository.load()
    ctx.settings_repository.save(
        Settings(
            output_device=current.output_device,
            monitor_device=chosen,
            gui_button_size=current.gui_button_size,
        )
    )
    if chosen is None:
        console.print("[green]Monitor device[/green] -> off")
    else:
        console.print(f"[green]Monitor device[/green] -> {chosen}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
