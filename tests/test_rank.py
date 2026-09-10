from __future__ import annotations

from sonicmatch.models import Track, VideoSonicProfile
from sonicmatch.music.rank import hook_slice, license_ok, rank_tracks, score_track
from sonicmatch.music.seed import SeedAdapter, load_seed_tracks


def _profile(**kwargs) -> VideoSonicProfile:
    base = dict(
        asset_id="a",
        duration_sec=15.0,
        aspect="9:16",
        content_type="lifestyle",
        has_speech=True,
        speech_coverage=0.6,
        overall_mood=["warm", "playful"],
        energy_mean=0.55,
        pacing="medium",
        suggested_bpm=(95, 118),
        avoid=["aggressive trap", "dark cinematic drone"],
        search_queries=["warm acoustic instrumental cafe"],
        platform_hint="instagram_reel",
        analyzer="local",
    )
    base.update(kwargs)
    return VideoSonicProfile(**base)


def test_seed_catalog_loads():
    tracks = load_seed_tracks()
    assert len(tracks) >= 20
    assert any(t.id == "seed_golden_hour_latte" for t in tracks)


def test_instrumental_preferred_when_speech():
    profile = _profile()
    acoustic = Track(
        id="a",
        title="Cafe",
        bpm=108,
        energy=0.55,
        moods=["warm", "playful"],
        genres=["acoustic"],
        instrumental=True,
        duration_sec=120,
        license="CC0-1.0",
        source="seed",
    )
    vocal = Track(
        id="b",
        title="Chorus",
        bpm=108,
        energy=0.55,
        moods=["warm", "playful"],
        genres=["pop"],
        instrumental=False,
        duration_sec=120,
        license="CC0-1.0",
        source="seed",
    )
    recs = rank_tracks([vocal, acoustic], profile, instrumental_only=True, max_results=5)
    assert recs
    assert recs[0].track.id == "a"
    assert all(r.track.instrumental for r in recs)


def test_trap_avoided_for_lifestyle():
    profile = _profile()
    cafe = Track(
        id="cafe",
        title="Latte",
        bpm=108,
        energy=0.55,
        moods=["warm"],
        genres=["acoustic"],
        instrumental=True,
        license="CC0-1.0",
        source="seed",
        duration_sec=100,
    )
    trap = Track(
        id="trap",
        title="Hard Count",
        bpm=140,
        energy=0.92,
        moods=["aggressive"],
        genres=["trap"],
        instrumental=True,
        license="CC-BY-4.0",
        source="seed",
        duration_sec=96,
        tags=["trap", "808"],
    )
    recs = rank_tracks([trap, cafe], profile, instrumental_only=True, max_results=5)
    assert recs[0].track.id == "cafe"


def test_nc_license_not_ok_for_platform():
    nc = Track(id="n", title="nc", license="CC-BY-NC-4.0", source="seed")
    cc0 = Track(id="z", title="z", license="CC0-1.0", source="seed")
    assert license_ok(nc, "instagram_reel") is False
    assert license_ok(cc0, "instagram_reel") is True


def test_hook_slice_is_short():
    track = Track(id="t", title="long", duration_sec=180, loopable=False, energy=0.7)
    start, end = hook_slice(track, 15.0, 0.6)
    assert 12 <= (end - start) <= 20
    assert start >= 0


def test_seed_search_filters_instrumental():
    adapter = SeedAdapter()
    vocals = adapter.search(__import__("sonicmatch.models", fromlist=["SearchQuery"]).SearchQuery(
        query="pop", instrumental=False, limit=20
    ))
    assert vocals
    assert all(not t.instrumental for t in vocals)


def test_score_includes_reason_and_license():
    profile = _profile()
    track = Track(
        id="seed_golden_hour_latte",
        title="Golden Hour Latte",
        bpm=108,
        energy=0.55,
        moods=["warm", "playful"],
        genres=["acoustic"],
        instrumental=True,
        license="CC0-1.0",
        source="seed",
        duration_sec=142,
    )
    score, reason, ok = score_track(track, profile, instrumental_only=True)
    assert score > 0.4
    assert "license" in reason.lower()
    assert ok is True
