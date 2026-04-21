from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from soundboard.audio.player import Player
from soundboard.audio.pygame_player import PygamePlayer
from soundboard.config import Paths, default_paths
from soundboard.core.library import (
    SoundAlreadyExistsError,
    SoundLibrary,
    SoundNotFoundError,
)
from soundboard.core.models import Sound
from soundboard.storage.repository import LibraryRepository
from soundboard.storage.toml_repository import TomlLibraryRepository

app = typer.Typer(help="Soundboard CLI — manage and play your sound library.")
console = Console()


@dataclass(slots=True)
class Context:
    paths: Paths
    repository: LibraryRepository
    player_factory: type[Player] | None


def _build_default_context() -> Context:
    paths = default_paths()
    paths.ensure()
    return Context(
        paths=paths,
        repository=TomlLibraryRepository(paths.library_file),
        player_factory=PygamePlayer,
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


@app.command("add")
def add(
    path: Annotated[Path, typer.Argument(help="Audio file to import.")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Display name.")] = None,
    hotkey: Annotated[str | None, typer.Option("--hotkey", "-k")] = None,
    tag: Annotated[list[str] | None, typer.Option("--tag", "-t", help="Repeatable.")] = None,
    volume: Annotated[float, typer.Option("--volume", "-v", min=0.0, max=1.0)] = 1.0,
    link: Annotated[bool, typer.Option("--link", help="Reference in place, don't copy.")] = False,
) -> None:
    """Register a sound."""
    ctx = _context()
    source = path.expanduser().resolve()
    if not source.is_file():
        console.print(f"[red]File not found:[/red] {source}")
        raise typer.Exit(code=2)

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
    )
    try:
        library.add(sound)
    except SoundAlreadyExistsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    ctx.repository.save(library)
    console.print(f"[green]Added[/green] '{sound.name}' ([dim]{sound.id}[/dim])")


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
    for col in ("Name", "Id", "Hotkey", "Tags", "Vol", "Path"):
        table.add_column(col)
    for s in sounds:
        table.add_row(
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
    player = ctx.player_factory()
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
    player = ctx.player_factory()
    try:
        player.stop_all()
    finally:
        player.close()
    console.print("[green]Stopped all.[/green]")


@app.command("where")
def where() -> None:
    """Show config and data paths."""
    ctx = _context()
    console.print(f"Library file: [bold]{ctx.paths.library_file}[/bold]")
    console.print(f"Sounds dir:   [bold]{ctx.paths.sounds_dir}[/bold]")


def build_library(library: SoundLibrary) -> SoundLibrary:
    """Convenience for tests/scripts that want a library to pre-populate."""
    return library


def main() -> None:
    app()


if __name__ == "__main__":
    main()
