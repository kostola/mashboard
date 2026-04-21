from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from soundboard.audio.player import PlayHandle
from soundboard.cli import app as cli_module
from soundboard.config import Paths
from soundboard.core.models import Sound
from soundboard.settings import InMemorySettingsRepository, Settings
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

    def __init__(self, device_name: str | None = None) -> None:
        self.played: list[Sound] = []
        self.stopped_all = False
        self.closed = False
        self.handle = FakeHandle()
        self.device_name = device_name
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


def _forbidden_downloader(*_args: object, **_kwargs: object) -> Path:
    raise AssertionError("downloader called without being overridden in the test")


@pytest.fixture(autouse=True)
def _isolated_context(tmp_path: Path) -> InMemorySettingsRepository:
    paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    paths.ensure()
    settings_repo = InMemorySettingsRepository()
    cli_module.set_context(
        cli_module.Context(
            paths=paths,
            repository=TomlLibraryRepository(paths.library_file),
            settings_repository=settings_repo,
            player_factory=FakePlayer,
            device_lister=lambda: ["Speakers (Test)", "VoiceMeeter Input (Test)"],
            downloader=_forbidden_downloader,
        )
    )
    FakePlayer.last_instance = None
    return settings_repo


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


def test_devices_lists_with_default_marker(
    runner: CliRunner, _isolated_context: InMemorySettingsRepository
) -> None:
    r = runner.invoke(cli_module.app, ["devices"])
    assert r.exit_code == 0
    assert "(system default)" in r.stdout
    assert "Speakers (Test)" in r.stdout
    assert "VoiceMeeter Input (Test)" in r.stdout


def test_config_show_defaults(runner: CliRunner) -> None:
    r = runner.invoke(cli_module.app, ["config", "show"])
    assert r.exit_code == 0
    assert "(system default)" in r.stdout


def test_config_set_device_roundtrip(
    runner: CliRunner, _isolated_context: InMemorySettingsRepository
) -> None:
    r = runner.invoke(cli_module.app, ["config", "set-device", "VoiceMeeter Input (Test)"])
    assert r.exit_code == 0
    assert _isolated_context.load() == Settings(output_device="VoiceMeeter Input (Test)")

    r = runner.invoke(cli_module.app, ["config", "show"])
    assert "VoiceMeeter Input (Test)" in r.stdout

    r = runner.invoke(cli_module.app, ["config", "set-device", "--clear"])
    assert r.exit_code == 0
    assert _isolated_context.load() == Settings(output_device=None)


def test_edit_updates_volume_and_name(runner: CliRunner, tmp_path: Path) -> None:
    clip = _make_clip(tmp_path)
    runner.invoke(cli_module.app, ["add", str(clip), "--name", "horn"])

    r = runner.invoke(cli_module.app, ["edit", "horn", "--volume", "0.3", "--name", "Horn!"])
    assert r.exit_code == 0, r.stdout

    r = runner.invoke(cli_module.app, ["list"])
    assert "Horn!" in r.stdout
    assert "0.30" in r.stdout


def test_edit_clear_hotkey_and_tag_edits(runner: CliRunner, tmp_path: Path) -> None:
    clip = _make_clip(tmp_path)
    runner.invoke(
        cli_module.app,
        ["add", str(clip), "--name", "horn", "--hotkey", "ctrl+h", "--tag", "funny"],
    )

    r = runner.invoke(
        cli_module.app,
        ["edit", "horn", "--clear-hotkey", "--add-tag", "loud", "--remove-tag", "funny"],
    )
    assert r.exit_code == 0, r.stdout

    r = runner.invoke(cli_module.app, ["list"])
    assert "loud" in r.stdout
    assert "funny" not in r.stdout
    assert "ctrl+h" not in r.stdout


def test_edit_conflicting_hotkey_flags(runner: CliRunner, tmp_path: Path) -> None:
    clip = _make_clip(tmp_path)
    runner.invoke(cli_module.app, ["add", str(clip), "--name", "horn"])

    r = runner.invoke(
        cli_module.app, ["edit", "horn", "--hotkey", "x", "--clear-hotkey"]
    )
    assert r.exit_code == 2
    assert "Cannot combine" in r.stdout


def test_edit_rename_collision(runner: CliRunner, tmp_path: Path) -> None:
    clip = _make_clip(tmp_path)
    runner.invoke(cli_module.app, ["add", str(clip), "--name", "horn"])
    clip2 = _make_clip(tmp_path, "beep.wav")
    runner.invoke(cli_module.app, ["add", str(clip2), "--name", "beep"])

    r = runner.invoke(cli_module.app, ["edit", "beep", "--name", "horn"])
    assert r.exit_code == 1
    assert "already exists" in r.stdout


def test_edit_unknown_sound_errors(runner: CliRunner) -> None:
    r = runner.invoke(cli_module.app, ["edit", "ghost", "--volume", "0.5"])
    assert r.exit_code == 1


def test_edit_no_options_is_noop(runner: CliRunner, tmp_path: Path) -> None:
    clip = _make_clip(tmp_path)
    runner.invoke(cli_module.app, ["add", str(clip), "--name", "horn"])
    r = runner.invoke(cli_module.app, ["edit", "horn"])
    assert r.exit_code == 0
    assert "Nothing to change" in r.stdout


def _install_downloader(
    runner_paths: Paths, settings_repo: InMemorySettingsRepository, downloader: object
) -> None:
    cli_module.set_context(
        cli_module.Context(
            paths=runner_paths,
            repository=TomlLibraryRepository(runner_paths.library_file),
            settings_repository=settings_repo,
            player_factory=FakePlayer,
            device_lister=lambda: [],
            downloader=downloader,  # type: ignore[arg-type]
        )
    )


def test_fetch_calls_downloader_and_adds_to_library(
    runner: CliRunner, _isolated_context: InMemorySettingsRepository
) -> None:
    ctx = cli_module._context()

    def fake_download(url: str, start: float | None, end: float | None, dest_dir: Path) -> Path:
        out = dest_dir / "abc123.mp3"
        out.write_bytes(b"ID3\x00")
        return out

    _install_downloader(ctx.paths, _isolated_context, fake_download)

    r = runner.invoke(cli_module.app, ["fetch", "https://example/x", "--name", "clip"])
    assert r.exit_code == 0, r.stdout
    assert "Fetched" in r.stdout

    r = runner.invoke(cli_module.app, ["list"])
    assert "clip" in r.stdout


def test_fetch_with_time_range_parses_and_forwards(
    runner: CliRunner, _isolated_context: InMemorySettingsRepository
) -> None:
    ctx = cli_module._context()
    captured: dict[str, object] = {}

    def spy(url: str, start: float | None, end: float | None, dest_dir: Path) -> Path:
        captured["start"] = start
        captured["end"] = end
        out = dest_dir / "abc123.mp3"
        out.write_bytes(b"ID3\x00")
        return out

    _install_downloader(ctx.paths, _isolated_context, spy)

    r = runner.invoke(
        cli_module.app,
        ["fetch", "https://example/x", "--start", "1:23", "--end", "1:30.5", "--name", "c"],
    )
    assert r.exit_code == 0, r.stdout
    assert captured["start"] == pytest.approx(83.0)
    assert captured["end"] == pytest.approx(90.5)


def test_fetch_invalid_range_errors(runner: CliRunner) -> None:
    r = runner.invoke(
        cli_module.app, ["fetch", "https://example/x", "--start", "10", "--end", "5"]
    )
    assert r.exit_code == 2
    assert "start must be before end" in r.stdout


def test_fetch_bad_timecode(runner: CliRunner) -> None:
    r = runner.invoke(
        cli_module.app,
        ["fetch", "https://example/x", "--start", "not-a-time", "--end", "1:00"],
    )
    assert r.exit_code == 2
    assert "invalid timecode" in r.stdout


def test_fetch_download_failure_errors(
    runner: CliRunner, _isolated_context: InMemorySettingsRepository
) -> None:
    ctx = cli_module._context()

    def boom(url: str, start: float | None, end: float | None, dest_dir: Path) -> Path:
        raise RuntimeError("network down")

    _install_downloader(ctx.paths, _isolated_context, boom)

    r = runner.invoke(cli_module.app, ["fetch", "https://example/x"])
    assert r.exit_code == 1
    assert "Download failed" in r.stdout
    assert "network down" in r.stdout


def test_play_uses_configured_device(
    runner: CliRunner, tmp_path: Path, _isolated_context: InMemorySettingsRepository
) -> None:
    clip = _make_clip(tmp_path)
    runner.invoke(cli_module.app, ["add", str(clip), "--name", "horn"])
    _isolated_context.save(Settings(output_device="VoiceMeeter Input (Test)"))

    r = runner.invoke(cli_module.app, ["play", "horn", "--no-wait"])
    assert r.exit_code == 0, r.stdout
    assert FakePlayer.last_instance is not None
    assert FakePlayer.last_instance.device_name == "VoiceMeeter Input (Test)"
