from __future__ import annotations

import os


def list_output_devices() -> list[str]:
    """Enumerate audio output devices available to SDL2/pygame.

    Initializes SDL's audio subsystem directly (without opening an audio
    stream), so this works even when another app holds the default output
    device exclusively (e.g. VoiceMeeter bound to the same device).
    Returns names in the form accepted by ``pygame.mixer.init(devicename=...)``.
    """
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame._sdl2 as sdl2

    sdl2.init_subsystem(sdl2.INIT_AUDIO)
    return list(sdl2.get_audio_device_names(False))
