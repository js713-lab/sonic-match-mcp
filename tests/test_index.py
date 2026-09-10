from __future__ import annotations

from sonicmatch.models import SearchQuery, Track
from sonicmatch.music.index import TrackIndex
from sonicmatch.music.seed import load_seed_tracks
from sonicmatch.tools import configure, get_track, status


def test_sqlite_roundtrip(settings):
    idx = TrackIndex(settings.db_path)
    tracks = load_seed_tracks()[:3]
    n = idx.upsert(tracks)
    assert n == 3
    got = idx.get(tracks[0].id)
    assert got is not None
    assert got.title == tracks[0].title
    assert got.embed
    hits = idx.search(SearchQuery(query=tracks[0].moods[0] if tracks[0].moods else "warm", limit=10))
    assert hits


def test_status_and_get_track_via_index(settings):
    configure(settings)
    st = status()
    assert st["ok"] is True
    assert st["seed_tracks"] >= 20
    assert st["index_tracks"] >= 20
    assert "ffmpeg" in st
    got = get_track("seed_golden_hour_latte")
    assert got["ok"] is True
    assert got["track"]["license"] == "CC0-1.0"
