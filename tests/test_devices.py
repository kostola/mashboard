from __future__ import annotations

from soundboard.audio.devices import list_output_devices


def test_list_output_devices_returns_strings() -> None:
    devices = list_output_devices()
    assert isinstance(devices, list)
    for name in devices:
        assert isinstance(name, str)
        assert name != ""


def test_list_output_devices_is_idempotent() -> None:
    first = list_output_devices()
    second = list_output_devices()
    assert first == second
