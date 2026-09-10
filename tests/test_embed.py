from __future__ import annotations

from sonicmatch.models import Track, VideoSonicProfile
from sonicmatch.music.embed import cosine, embed_profile, embed_track


def test_similar_moods_score_higher_than_opposite():
    warm = Track(
        id="w",
        title="Latte",
        energy=0.55,
        bpm=108,
        moods=["warm", "playful"],
        genres=["acoustic"],
        instrumental=True,
        source="seed",
    )
    trap = Track(
        id="t",
        title="808",
        energy=0.92,
        bpm=140,
        moods=["aggressive", "dark"],
        genres=["trap"],
        instrumental=True,
        source="seed",
    )
    profile = VideoSonicProfile(
        asset_id="a",
        duration_sec=15,
        aspect="9:16",
        overall_mood=["warm", "playful"],
        energy_mean=0.55,
        suggested_bpm=(100, 118),
        search_queries=["warm acoustic cafe"],
        analyzer="local",
    )
    target = embed_profile(profile)
    assert cosine(target, embed_track(warm)) > cosine(target, embed_track(trap))


def test_embed_is_unitish_and_stable():
    t = Track(id="x", title="x", moods=["warm"], energy=0.4, bpm=100)
    a = embed_track(t)
    b = embed_track(t)
    assert a == b
    assert len(a) >= 8
    assert abs(sum(x * x for x in a) - 1.0) < 0.02
