from __future__ import annotations

from collections.abc import Iterable, Iterator

from soundboard.core.models import Sound


class SoundNotFoundError(KeyError):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key

    def __str__(self) -> str:
        return f"no sound with name or id '{self.key}'"


class SoundAlreadyExistsError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"a sound named '{self.name}' already exists"


class SoundLibrary:
    def __init__(self, sounds: Iterable[Sound] = ()) -> None:
        self._by_id: dict[str, Sound] = {}
        for s in sounds:
            self._insert(s)

    def _insert(self, sound: Sound) -> None:
        if any(s.name == sound.name for s in self._by_id.values()):
            raise SoundAlreadyExistsError(sound.name)
        self._by_id[sound.id] = sound

    def add(self, sound: Sound) -> None:
        self._insert(sound)

    def remove(self, key: str) -> Sound:
        sound = self.find(key)
        del self._by_id[sound.id]
        return sound

    def find(self, key: str) -> Sound:
        if key in self._by_id:
            return self._by_id[key]
        for s in self._by_id.values():
            if s.name == key:
                return s
        raise SoundNotFoundError(key)

    def get(self, key: str) -> Sound | None:
        try:
            return self.find(key)
        except SoundNotFoundError:
            return None

    def search(self, tag: str) -> list[Sound]:
        return [s for s in self._by_id.values() if tag in s.tags]

    def __iter__(self) -> Iterator[Sound]:
        return iter(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.get(key) is not None
