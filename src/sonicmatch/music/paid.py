"""User-owned licensed library adapters (Epidemic / Artlist / generic JSON).

We do NOT scrape Epidemic Sound or Artlist. Drop a JSON export of tracks you
already have the right to use (subscription libraries you pay for).
"""

from __future__ import annotations

import json
from pathlib import Path

from sonicmatch.config import Settings
from sonicmatch.errors import SonicError
from sonicmatch.models import SearchQuery, Track
from sonicmatch.music.seed import SeedAdapter


def _load_json(path: Path) -> list[Track]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("tracks", raw) if isinstance(raw, dict) else raw
    tracks: list[Track] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item.setdefault("source", "library")
        item.setdefault("license", "user-owned-library")
        item.setdefault("attribution_required", True)
        try:
            tracks.append(Track.model_validate(item))
        except Exception:
            continue
    return tracks


class LibraryAdapter:
    name = "library"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._tracks: dict[str, Track] = {}
        for env_path in (
            settings.user_library_path,
            settings.epidemic_library_path,
            settings.artlist_library_path,
        ):
            if env_path:
                for t in _load_json(Path(env_path).expanduser()):
                    self._tracks[t.id] = t
        default = settings.cache_dir / "libraries"
        if default.exists():
            for p in default.glob("*.json"):
                for t in _load_json(p):
                    self._tracks[t.id] = t

    def empty(self) -> bool:
        return not self._tracks

    def all(self) -> list[Track]:
        return list(self._tracks.values())

    def get(self, track_id: str) -> Track | None:
        return self._tracks.get(track_id)

    def search(self, query: SearchQuery) -> list[Track]:
        if not self._tracks:
            raise SonicError(
                "LIBRARY_EMPTY",
                "No user-owned library JSON found. Export tracks you already license "
                "(Epidemic/Artlist subscription) to SONICMATCH_LIBRARY_PATH or "
                "cache/libraries/*.json. This adapter will not scrape paid catalogs.",
            )
        # Reuse seed-style filtering by wrapping as a tiny adapter.
        tmp = SeedAdapter.__new__(SeedAdapter)
        tmp._path = None
        tmp._by_id = dict(self._tracks)
        return tmp.search(query)
