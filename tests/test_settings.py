from __future__ import annotations

from pathlib import Path

from mashboard.settings import (
    InMemorySettingsRepository,
    Settings,
    TomlSettingsRepository,
)


def test_load_missing_file_returns_defaults(tmp_path: Path) -> None:
    repo = TomlSettingsRepository(tmp_path / "missing.toml")
    assert repo.load() == Settings()


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    repo = TomlSettingsRepository(tmp_path / "settings.toml")
    repo.save(Settings(output_device="VoiceMeeter Input"))
    assert repo.load() == Settings(output_device="VoiceMeeter Input")


def test_round_trip_with_monitor_device(tmp_path: Path) -> None:
    repo = TomlSettingsRepository(tmp_path / "settings.toml")
    repo.save(Settings(output_device="Speakers", monitor_device="Headphones"))
    assert repo.load() == Settings(output_device="Speakers", monitor_device="Headphones")


def test_round_trip_monitor_only(tmp_path: Path) -> None:
    repo = TomlSettingsRepository(tmp_path / "settings.toml")
    repo.save(Settings(monitor_device="Headphones"))
    assert repo.load() == Settings(monitor_device="Headphones")


def test_round_trip_button_size(tmp_path: Path) -> None:
    repo = TomlSettingsRepository(tmp_path / "settings.toml")
    repo.save(Settings(gui_button_size=160))
    assert repo.load() == Settings(gui_button_size=160)


def test_save_default_keeps_file_empty(tmp_path: Path) -> None:
    repo = TomlSettingsRepository(tmp_path / "settings.toml")
    repo.save(Settings(output_device=None))
    assert repo.load() == Settings()


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    repo = TomlSettingsRepository(tmp_path / "nested" / "settings.toml")
    repo.save(Settings(output_device="X"))
    assert repo.path.exists()


def test_in_memory_repository_round_trip() -> None:
    repo = InMemorySettingsRepository()
    assert repo.load() == Settings()
    repo.save(Settings(output_device="Foo", monitor_device="Bar"))
    assert repo.load() == Settings(output_device="Foo", monitor_device="Bar")
