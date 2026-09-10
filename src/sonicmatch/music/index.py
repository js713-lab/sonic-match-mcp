"""SQLite track index (tags + license + optional embedding). LanceDB is optional."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable

from sonicmatch.config import Settings
from sonicmatch.models import SearchQuery, Track
from sonicmatch.music.embed import cosine, embed_profile, embed_track, ensure_embed
from sonicmatch.models import VideoSonicProfile


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT,
    json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tracks_source ON tracks(source);
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

    def upsert(self, tracks: Iterable[Track]) -> int:
        n = 0
        now = time.time()
        materialized = [ensure_embed(raw) for raw in tracks]
        with self._lock:
            for track in materialized:
                self._conn.execute(
                    "INSERT OR REPLACE INTO tracks(id, source, title, json, updated_at) VALUES (?,?,?,?,?)",
                    (
                        track.id,
                        track.source,
                        track.title,
                        track.model_dump_json(),
                        now,
                    ),
                )
                n += 1
            self._conn.commit()
        self._maybe_lancedb(materialized)
        return n

    def get(self, track_id: str) -> Track | None:
        with self._lock:
            row = self._conn.execute("SELECT json FROM tracks WHERE id = ?", (track_id,)).fetchone()
        if not row:
            return None
        return Track.model_validate_json(row[0])

    def all(self, source: str | None = None) -> list[Track]:
        with self._lock:
            if source:
                rows = self._conn.execute(
                    "SELECT json FROM tracks WHERE source = ?", (source,)
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT json FROM tracks").fetchall()
        out: list[Track] = []
        for (blob,) in rows:
            try:
                out.append(Track.model_validate_json(blob))
            except Exception:
                continue
        return out

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
            row = self._conn.execute("SELECT COUNT(*) FROM tracks").fetchone()
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
