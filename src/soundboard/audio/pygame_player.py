from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pygame.mixer import Channel
    from pygame.mixer import Sound as MixerSound

from soundboard.core.models import Sound


class _PygameHandle:
    def __init__(self, channel: Channel) -> None:
        self._channel = channel

    def is_playing(self) -> bool:
        return bool(self._channel.get_busy())

    def stop(self) -> None:
        self._channel.stop()

    def wait(self) -> None:
        while self.is_playing():
            time.sleep(0.05)


class PygamePlayer:
    def __init__(self, device_name: str | None = None) -> None:
        self._initialized = False
        self._cache: dict[str, MixerSound] = {}
        self._device_name = device_name

    @property
    def device_name(self) -> str | None:
        return self._device_name

    def _ensure_init(self) -> None:
        if self._initialized:
            return
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame

        if self._device_name:
            pygame.mixer.init(devicename=self._device_name)
        else:
            pygame.mixer.init()
        self._initialized = True

    def play(self, sound: Sound) -> _PygameHandle:
        self._ensure_init()
        import pygame

        mixer_sound = self._cache.get(sound.id)
        if mixer_sound is None:
            mixer_sound = pygame.mixer.Sound(str(sound.path))
            self._cache[sound.id] = mixer_sound
        mixer_sound.set_volume(sound.volume)
        channel = mixer_sound.play()
        if channel is None:
            raise RuntimeError("no free mixer channel available")
        return _PygameHandle(channel)

    def stop_all(self) -> None:
        if not self._initialized:
            return
        import pygame

        pygame.mixer.stop()

    def close(self) -> None:
        if not self._initialized:
            return
        import pygame

        pygame.mixer.quit()
        self._cache.clear()
        self._initialized = False
