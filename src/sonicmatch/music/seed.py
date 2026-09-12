"""Always-available seed catalog.

Twenty Reel-editor beds (CC0 / CC-BY) plus two fixtures: a vocal track and a
CC-BY-NC track. Non-commercial rows are searchable and never auto-recommended.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sonicmatch.config import seed_catalog_path
from sonicmatch.models import SearchQuery, Track


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("-", " ").split())


@lru_cache(maxsize=4)
def load_seed_tracks(path: str | None = None) -> list[Track]:
    p = Path(path) if path else seed_catalog_path()
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    items = raw.get("tracks", raw) if isinstance(raw, dict) else raw
    tracks: list[Track] = []
    for item in items:
        try:
            tracks.append(Track.model_validate(item))
        except Exception:
            continue
    return tracks


class SeedAdapter:
    name = "seed"

    def __init__(self, path: str | None = None) -> None:
        self._path = path
        self._by_id = {t.id: t for t in load_seed_tracks(path)}

    def all(self) -> list[Track]:
        return list(self._by_id.values())

    def get(self, track_id: str) -> Track | None:
        return self._by_id.get(track_id)

    def search(self, query: SearchQuery) -> list[Track]:
        tokens = [t for t in _norm(query.query).split() if t]
        hits: list[tuple[float, Track]] = []
        for track in self._by_id.values():
            if query.instrumental is True and not track.instrumental:
                continue
            if query.instrumental is False and track.instrumental:
                continue
            if query.bpm_min and track.bpm and track.bpm < query.bpm_min:
                continue
            if query.bpm_max and track.bpm and track.bpm > query.bpm_max:
                continue
            if query.duration_min and track.duration_sec < query.duration_min:
                continue
            if query.duration_max and track.duration_sec > query.duration_max:
                continue
            hay = _norm(
                " ".join(
                    [
                        track.title,
                        track.artist,
                        " ".join(track.moods),
                        " ".join(track.genres),
                        " ".join(track.tags),
                        "instrumental" if track.instrumental else "vocal",
                    ]
                )
            )
            score = 1.0
            if tokens:
                matched = sum(1 for tok in tokens if tok in hay)
                score = matched / len(tokens)
                if score <= 0:
                    continue
            if query.moods:
                tm = {_norm(m) for m in track.moods}
                if not any(_norm(m) in tm or _norm(m) in hay for m in query.moods):
                    score *= 0.4
            hits.append((score, track))
        hits.sort(key=lambda x: x[0], reverse=True)
        limit = max(1, min(query.limit, 40))
        return [t for _s, t in hits[:limit]]
