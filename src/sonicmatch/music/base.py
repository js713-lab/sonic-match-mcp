"""Music adapter protocol."""

from __future__ import annotations

from typing import Protocol

from sonicmatch.models import SearchQuery, Track


class MusicAdapter(Protocol):
    name: str

    def search(self, query: SearchQuery) -> list[Track]:
        ...

    def get(self, track_id: str) -> Track | None:
        ...
