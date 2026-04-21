from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from soundboard.audio.player import PlayHandle
from soundboard.cli import app as cli_module
from soundboard.config import Paths
from soundboard.core.models import Sound
from soundboard.storage.toml_repository import TomlLibraryRepository


class FakeHandle:
    def __init__(self) -> None:
        self.stopped = False
        self.waited = False

    def is_playing(self) -> bool:
        return not self.stopped

    def stop(self) -> None:
        self.stopped = True

    def wait(self) -> None:
        self.waited = True


class FakePlayer:
    last_instance: FakePlayer | None = None

    def __init__(self) -> None:
        self.played: list[Sound] = []
        self.stopped_all = False
        self.closed = False
        self.handle = FakeHandle()
        FakePlayer.last_instance = self

    def play(self, sound: Sound) -> PlayHandle:
        self.played.append(sound)
        return self.handle

    def stop_all(self) -> None:
        self.stopped_all = True

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _isolated_context(tmp_path: Path) -> None:
    paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    paths.ensure()
    cli_module.set_context(
        cli_module.Context(
            paths=paths,
            repository=TomlLibraryRepository(paths.library_file),
            player_factory=FakePlayer,
        )
    )
    FakePlayer.last_instance = None


def _make_clip(tmp_path: Path, name: str = "horn.wav") -> Path:
    clip = tmp_path / name
    clip.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    return clip


def test_add_list_remove_flow(runner: CliRunner, tmp_path: Path) -> None:
    clip = _make_clip(tmp_path)

    r = runner.invoke(cli_module.app, ["add", str(clip), "--name", "horn", "--tag", "funny"])
    assert r.exit_code == 0, r.stdout
    assert "Added" in r.stdout

    r = runner.invoke(cli_module.app, ["list"])
    assert r.exit_code == 0
    assert "horn" in r.stdout
    assert "funny" in r.stdout

    r = runner.invoke(cli_module.app, ["remove", "horn"])
    assert r.exit_code == 0
    assert "Removed" in r.stdout

    r = runner.invoke(cli_module.app, ["list"])
    assert "No sounds" in r.stdout


def test_add_duplicate_name_errors(runner: CliRunner, tmp_path: Path) -> None:
    clip = _make_clip(tmp_path)
    r1 = runner.invoke(cli_module.app, ["add", str(clip), "--name", "horn"])
    assert r1.exit_code == 0
    r2 = runner.invoke(cli_module.app, ["add", str(clip), "--name", "horn"])
    assert r2.exit_code == 1
    assert "already exists" in r2.stdout


def test_play_unknown_errors(runner: CliRunner) -> None:
    r = runner.invoke(cli_module.app, ["play", "ghost"])
    assert r.exit_code == 1
    assert "no sound" in r.stdout


def test_play_invokes_player(runner: CliRunner, tmp_path: Path) -> None:
    clip = _make_clip(tmp_path)
    runner.invoke(cli_module.app, ["add", str(clip), "--name", "horn"])

    r = runner.invoke(cli_module.app, ["play", "horn", "--no-wait"])
    assert r.exit_code == 0, r.stdout
    assert FakePlayer.last_instance is not None
    assert [s.name for s in FakePlayer.last_instance.played] == ["horn"]
    assert FakePlayer.last_instance.closed is True


def test_remove_missing_errors(runner: CliRunner) -> None:
    r = runner.invoke(cli_module.app, ["remove", "ghost"])
    assert r.exit_code == 1
