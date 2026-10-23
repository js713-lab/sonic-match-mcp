"""SQLite track index (tags + license + optional embedding). LanceDB is optional."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable

from sonicmatch.models import SearchQuery, Track, VideoSonicProfile
from sonicmatch.music.embed import cosine, embed_profile, embed_track, ensure_embed


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT,
    json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tracks_source ON tracks(source);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class TrackIndex:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        # MCP 2.x calls tools on worker threads.
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        self._cache: dict[str, Track] | None = None

    def upsert(self, tracks: Iterable[Track]) -> int:
        now = time.time()
        materialized = [ensure_embed(raw) for raw in tracks]
        changed: list[Track] = []
        with self._lock:
            existing = self._existing_json([track.id for track in materialized])
            rows = []
            for track in materialized:
                blob = track.model_dump_json()
                if existing.get(track.id) == blob:
                    continue
                rows.append((track.id, track.source, track.title, blob, now))
                changed.append(track)
                if self._cache is not None:
                    self._cache[track.id] = track
            if rows:
                self._conn.executemany(
                    "INSERT OR REPLACE INTO tracks(id, source, title, json, updated_at) VALUES (?,?,?,?,?)",
                    rows,
                )
                self._conn.commit()
        if changed:
            self._maybe_lancedb(changed)
        return len(materialized)

    def _existing_json(self, ids: list[str]) -> dict[str, str]:
        found: dict[str, str] = {}
        for start in range(0, len(ids), 400):
            chunk = ids[start : start + 400]
            if not chunk:
                continue
            marks = ",".join("?" for _ in chunk)
            for track_id, blob in self._conn.execute(
                f"SELECT id, json FROM tracks WHERE id IN ({marks})",
                chunk,
            ):
                found[track_id] = blob
        return found

    def meta_get(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def meta_set(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                (key, value),
            )
            self._conn.commit()

    def _load_cache(self) -> dict[str, Track]:
        if self._cache is not None:
            return self._cache
        loaded: dict[str, Track] = {}
        for track_id, blob in self._conn.execute("SELECT id, json FROM tracks"):
            try:
                loaded[track_id] = Track.model_validate_json(blob)
            except Exception:
                continue
        self._cache = loaded
        return loaded

    def get(self, track_id: str) -> Track | None:
        with self._lock:
            return self._load_cache().get(track_id)

    def all(self, source: str | None = None) -> list[Track]:
        with self._lock:
            tracks = list(self._load_cache().values())
        if source:
            return [track for track in tracks if track.source == source]
        return tracks

    def search(self, query: SearchQuery) -> list[Track]:
        tokens = [t for t in query.query.lower().split() if t]
        hits: list[tuple[float, Track]] = []
        for track in self.all():
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
            hay = " ".join(
                [track.title, track.artist, " ".join(track.moods), " ".join(track.genres), " ".join(track.tags)]
            ).lower()
            score = 1.0
            if tokens:
                matched = sum(1 for tok in tokens if tok in hay)
                if matched == 0:
                    continue
                score = matched / len(tokens)
            hits.append((score, track))
        hits.sort(key=lambda x: x[0], reverse=True)
        return [t for _s, t in hits[: max(1, min(query.limit, 40))]]

    def similar(self, profile: VideoSonicProfile, limit: int = 20) -> list[tuple[float, Track]]:
        target = embed_profile(profile)
        scored: list[tuple[float, Track]] = []
        for track in self.all():
            vec = track.embed or embed_track(track)
            scored.append((cosine(target, vec), track))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:limit]

    def count(self) -> int:
        with self._lock:
            if self._cache is not None:
                return len(self._cache)
            row = self._conn.execute("SELECT COUNT(*) FROM tracks").fetchone()
        return int(row[0]) if row else 0

    def count_source(self, source: str) -> int:
        with self._lock:
            if self._cache is not None:
                return sum(1 for track in self._cache.values() if track.source == source)
            row = self._conn.execute(
                "SELECT COUNT(*) FROM tracks WHERE source = ?", (source,)
            ).fetchone()
        return int(row[0]) if row else 0

    def _maybe_lancedb(self, tracks: list[Track]) -> None:
        if not tracks:
            return
        try:
            import lancedb  # type: ignore
        except Exception:
            return
        try:
            db = lancedb.connect(str(self.path.parent / "lancedb"))
            rows = [
                {
                    "id": t.id,
                    "vector": t.embed or embed_track(t),
                    "title": t.title,
                    "source": t.source,
                    "payload": t.model_dump_json(),
                }
                for t in tracks
            ]
            if "tracks" in db.table_names():
                tbl = db.open_table("tracks")
                tbl.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(rows)
            else:
                db.create_table("tracks", rows)
        except Exception:
            return
