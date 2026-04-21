from __future__ import annotations

from typing import Protocol

from soundboard.core.library import SoundLibrary


class LibraryRepository(Protocol):
    def load(self) -> SoundLibrary: ...
    def save(self, library: SoundLibrary) -> None: ...
