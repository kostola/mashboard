from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

from mashboard.core.models import Sound

if TYPE_CHECKING:
    pass


class _FakeOutputStream:
    instances: list[_FakeOutputStream] = []

    def __init__(
        self,
        *,
        samplerate: int,
        channels: int,
        device: str | None,
        dtype: str,
        callback: Any,
    ) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self.device = device
        self.dtype = dtype
        self.callback = callback
        self.started = False
        self.stopped = False
        self.closed = False
        _FakeOutputStream.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def pump(self, frames: int) -> np.ndarray:
        out = np.zeros((frames, self.channels), dtype=np.float32)
        self.callback(out, frames, None, None)
        return out


def _install_fake_sounddevice(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available_devices: list[str] | None = None,
) -> None:
    _FakeOutputStream.instances = []
    fake = types.ModuleType("sounddevice")
    fake.OutputStream = _FakeOutputStream  # type: ignore[attr-defined]
    devices = available_devices if available_devices is not None else [
        "Speakers (Test)",
        "Headphones (Test)",
        "VoiceMeeter Input (Test)",
    ]
    device_dicts = [
        {
            "name": name,
            "max_output_channels": 2,
            "hostapi": 0,
            "default_samplerate": 48000.0,
        }
        for name in devices
    ]

    def fake_query_devices(arg: object = None, kind: str | None = None) -> Any:
        if isinstance(arg, int):
            return device_dicts[arg]
        if kind == "output" and device_dicts:
            return device_dicts[0]
        return list(device_dicts)

    fake.query_devices = fake_query_devices  # type: ignore[attr-defined]
    fake.query_hostapis = lambda: [  # type: ignore[attr-defined]
        {"name": "Windows WASAPI"}
    ]
    monkeypatch.setitem(sys.modules, "sounddevice", fake)


def _install_fake_soundfile(
    monkeypatch: pytest.MonkeyPatch,
    samplerate: int = 44100,
    channels: int = 2,
    n_samples: int = 8,
) -> None:
    fake = types.ModuleType("soundfile")

    def fake_read(
        _path: str, dtype: str = "float32", always_2d: bool = True
    ) -> tuple[np.ndarray, int]:
        data = np.linspace(0.0, 1.0, n_samples * channels, dtype=np.float32).reshape(
            n_samples, channels
        )
        return data, samplerate

    fake.read = fake_read  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "soundfile", fake)


def _make_sound(tmp_path: Path, sound_id: str = "abc", volume: float = 1.0) -> Sound:
    clip = tmp_path / f"{sound_id}.wav"
    clip.write_bytes(b"RIFF0000WAVE")
    return Sound(id=sound_id, name=sound_id, path=clip, volume=volume)


def test_two_devices_open_two_streams(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_sounddevice(monkeypatch)
    _install_fake_soundfile(monkeypatch)
    from mashboard.audio.sounddevice_player import SoundDevicePlayer

    player = SoundDevicePlayer(devices=["Speakers (Test)", "Headphones (Test)"])
    try:
        player.play(_make_sound(tmp_path))
        assert len(_FakeOutputStream.instances) == 2
        # Names resolve to indices in the fake device list (Speakers=0, Headphones=1).
        assert [s.device for s in _FakeOutputStream.instances] == [0, 1]
        assert all(s.started for s in _FakeOutputStream.instances)
    finally:
        player.close()


def test_play_feeds_both_streams(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_sounddevice(monkeypatch)
    _install_fake_soundfile(monkeypatch, n_samples=4)
    from mashboard.audio.sounddevice_player import SoundDevicePlayer

    player = SoundDevicePlayer(devices=["Speakers (Test)", "Headphones (Test)"])
    try:
        handle = player.play(_make_sound(tmp_path, volume=0.5))
        primary, monitor = _FakeOutputStream.instances
        primary_buf = primary.pump(8)
        monitor_buf = monitor.pump(8)
        np.testing.assert_array_equal(primary_buf, monitor_buf)
        assert primary_buf[:4].any()
        assert not handle.is_playing()
    finally:
        player.close()


def test_stop_all_clears_voices_on_all_streams(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_sounddevice(monkeypatch)
    _install_fake_soundfile(monkeypatch, n_samples=1024)
    from mashboard.audio.sounddevice_player import SoundDevicePlayer

    player = SoundDevicePlayer(devices=["Speakers (Test)", "Headphones (Test)"])
    try:
        handle = player.play(_make_sound(tmp_path))
        player.stop_all()
        primary, monitor = _FakeOutputStream.instances
        out = primary.pump(64)
        assert not out.any()
        out = monitor.pump(64)
        assert not out.any()
        assert not handle.is_playing()
    finally:
        player.close()


def test_unknown_device_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_sounddevice(monkeypatch, available_devices=["Speakers (Test)"])
    _install_fake_soundfile(monkeypatch)
    from mashboard.audio.sounddevice_player import SoundDevicePlayer

    player = SoundDevicePlayer(devices=["Headphones (Missing)"])
    with pytest.raises(RuntimeError, match="Headphones \\(Missing\\)"):
        player.play(_make_sound(tmp_path))


def test_default_device_does_not_validate_against_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_sounddevice(monkeypatch, available_devices=["Ignored (Test)"])
    _install_fake_soundfile(monkeypatch)
    from mashboard.audio.sounddevice_player import SoundDevicePlayer

    player = SoundDevicePlayer(devices=[None])
    try:
        player.play(_make_sound(tmp_path))
        assert len(_FakeOutputStream.instances) == 1
        assert _FakeOutputStream.instances[0].device is None
    finally:
        player.close()


def test_close_closes_all_streams(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_sounddevice(monkeypatch)
    _install_fake_soundfile(monkeypatch)
    from mashboard.audio.sounddevice_player import SoundDevicePlayer

    player = SoundDevicePlayer(devices=["Speakers (Test)", "Headphones (Test)"])
    player.play(_make_sound(tmp_path))
    streams = list(_FakeOutputStream.instances)
    player.close()
    assert all(s.stopped and s.closed for s in streams)
