from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

from soundboard.core.models import Sound

FALLBACK_SAMPLE_RATE = 44100
CHANNELS = 2


class _Voice:
    __slots__ = ("samples", "position", "volume", "cancelled", "done")

    def __init__(self, samples: np.ndarray, volume: float) -> None:
        self.samples = samples
        self.position = 0
        self.volume = volume
        self.cancelled = False
        self.done = threading.Event()


class _SDHandle:
    def __init__(self, voices: list[_Voice]) -> None:
        self._voices = voices

    def is_playing(self) -> bool:
        return any(not v.done.is_set() for v in self._voices)

    def stop(self) -> None:
        for v in self._voices:
            v.cancelled = True

    def wait(self) -> None:
        for v in self._voices:
            v.done.wait()


class _DeviceStream:
    def __init__(
        self,
        device: str | None,
        resolved: int | str | None,
        lock: threading.Lock,
    ) -> None:
        import sounddevice as sd

        self._device = device
        self._voices: list[_Voice] = []
        self._lock = lock
        self._resampled: dict[str, np.ndarray] = {}
        if resolved is not None:
            info = sd.query_devices(resolved)
        else:
            info = sd.query_devices(kind="output")
        rate = info.get("default_samplerate") or FALLBACK_SAMPLE_RATE
        self.samplerate = int(round(float(rate)))
        self._stream = sd.OutputStream(
            samplerate=self.samplerate,
            channels=CHANNELS,
            device=resolved,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    @property
    def device(self) -> str | None:
        return self._device

    def voice_for(self, sound_id: str, native: np.ndarray, native_sr: int, volume: float) -> _Voice:
        cached = self._resampled.get(sound_id)
        if cached is None:
            import numpy as np

            cached = native if native_sr == self.samplerate else _resample(
                native, native_sr, self.samplerate
            )
            cached = np.ascontiguousarray(cached, dtype=np.float32)
            self._resampled[sound_id] = cached
        return _Voice(cached, volume)

    def _callback(
        self,
        outdata: np.ndarray,
        frames: int,
        _time: object,
        _status: object,
    ) -> None:
        outdata.fill(0)
        with self._lock:
            for voice in list(self._voices):
                if voice.cancelled:
                    voice.done.set()
                    self._voices.remove(voice)
                    continue
                remaining = voice.samples.shape[0] - voice.position
                n = min(frames, remaining)
                if n > 0:
                    chunk = voice.samples[voice.position : voice.position + n]
                    outdata[:n] += chunk * voice.volume
                    voice.position += n
                if voice.position >= voice.samples.shape[0]:
                    voice.done.set()
                    self._voices.remove(voice)

    def add_voice(self, voice: _Voice) -> None:
        with self._lock:
            self._voices.append(voice)

    def clear_voices(self) -> None:
        with self._lock:
            for v in self._voices:
                v.done.set()
            self._voices.clear()

    def close(self) -> None:
        try:
            self._stream.stop()
        finally:
            self._stream.close()


class SoundDevicePlayer:
    def __init__(self, devices: Sequence[str | None] | None = None) -> None:
        names: tuple[str | None, ...] = tuple(devices) if devices else (None,)
        if not names:
            names = (None,)
        self._device_names = names
        self._streams: list[_DeviceStream] | None = None
        self._cache: dict[str, tuple[np.ndarray, int]] = {}
        self._lock = threading.Lock()

    @property
    def devices(self) -> tuple[str | None, ...]:
        return self._device_names

    def _ensure_open(self) -> list[_DeviceStream]:
        if self._streams is not None:
            return self._streams
        resolved: list[int | str | None] = []
        named = [d for d in self._device_names if d is not None]
        if named:
            import sounddevice as sd

            from soundboard.audio.devices import _preferred_hostapi_index

            devices = list(sd.query_devices())
            hostapis = list(sd.query_hostapis())
            preferred = _preferred_hostapi_index(hostapis)
            lookup: dict[str, int] = {}
            for i, dev in enumerate(devices):
                if dev.get("max_output_channels", 0) <= 0:
                    continue
                if preferred is not None and dev.get("hostapi") != preferred:
                    continue
                name = str(dev.get("name", ""))
                if name and name not in lookup:
                    lookup[name] = i
            if preferred is None or not lookup:
                lookup = {
                    str(dev.get("name", "")): i
                    for i, dev in enumerate(devices)
                    if dev.get("max_output_channels", 0) > 0 and dev.get("name")
                }
        else:
            lookup = {}
        for d in self._device_names:
            if d is None:
                resolved.append(None)
            elif d in lookup:
                resolved.append(lookup[d])
            else:
                raise RuntimeError(f"audio device not found: {d}")
        self._streams = [
            _DeviceStream(name, idx, self._lock)
            for name, idx in zip(self._device_names, resolved, strict=True)
        ]
        return self._streams

    def _decode(self, sound: Sound) -> tuple[np.ndarray, int]:
        cached = self._cache.get(sound.id)
        if cached is not None:
            return cached
        import numpy as np
        import soundfile as sf

        data, src_sr = sf.read(str(sound.path), dtype="float32", always_2d=True)
        if data.shape[1] == 1:
            data = np.repeat(data, CHANNELS, axis=1)
        elif data.shape[1] > CHANNELS:
            data = data[:, :CHANNELS]
        data = np.ascontiguousarray(data, dtype=np.float32)
        result = (data, int(src_sr))
        self._cache[sound.id] = result
        return result

    def play(self, sound: Sound) -> _SDHandle:
        streams = self._ensure_open()
        native, native_sr = self._decode(sound)
        voices = [
            stream.voice_for(sound.id, native, native_sr, sound.volume)
            for stream in streams
        ]
        for stream, voice in zip(streams, voices, strict=True):
            stream.add_voice(voice)
        return _SDHandle(voices)

    def stop_all(self) -> None:
        if self._streams is None:
            return
        for stream in self._streams:
            stream.clear_voices()

    def close(self) -> None:
        if self._streams is None:
            return
        for stream in self._streams:
            stream.close()
        self._streams = None
        self._cache.clear()


def _resample(samples: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    import numpy as np

    if src_sr == dst_sr:
        return samples
    n_src = samples.shape[0]
    n_dst = max(1, int(round(n_src * dst_sr / src_sr)))
    x_src = np.linspace(0.0, 1.0, n_src, endpoint=False)
    x_dst = np.linspace(0.0, 1.0, n_dst, endpoint=False)
    if samples.ndim == 1:
        return np.interp(x_dst, x_src, samples).astype(np.float32)
    out = np.empty((n_dst, samples.shape[1]), dtype=np.float32)
    for c in range(samples.shape[1]):
        out[:, c] = np.interp(x_dst, x_src, samples[:, c])
    return out
