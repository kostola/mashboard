from __future__ import annotations

PREFERRED_HOSTAPIS: tuple[str, ...] = (
    "Windows WASAPI",
    "Core Audio",
    "ALSA",
    "JACK Audio Connection Kit",
    "PulseAudio",
)


def _preferred_hostapi_index(hostapis: list[dict]) -> int | None:
    for preferred in PREFERRED_HOSTAPIS:
        for i, h in enumerate(hostapis):
            if h.get("name") == preferred:
                return i
    return None


def list_output_devices() -> list[str]:
    """Enumerate audio output devices available to PortAudio.

    Filters to a single preferred host API per platform (WASAPI on Windows,
    Core Audio on macOS, ALSA on Linux). This avoids duplicate entries — the
    same physical endpoint shows up under MME / DirectSound / WASAPI on
    Windows, with MME truncating names to 31 characters.

    Returns names in the form accepted by ``sounddevice.OutputStream(device=...)``.
    De-duplicates while preserving order.
    """
    import sounddevice as sd

    devices = list(sd.query_devices())
    hostapis = list(sd.query_hostapis())
    preferred = _preferred_hostapi_index(hostapis)

    seen: set[str] = set()
    names: list[str] = []
    for dev in devices:
        if dev.get("max_output_channels", 0) <= 0:
            continue
        if preferred is not None and dev.get("hostapi") != preferred:
            continue
        name = str(dev.get("name", ""))
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names
