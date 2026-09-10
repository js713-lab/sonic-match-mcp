from __future__ import annotations

from sonicmatch.models import EnergyPoint, SceneBeat, Track, VideoSonicProfile


def test_videasonic_schema_roundtrip():
    profile = VideoSonicProfile(
        asset_id="abc",
        duration_sec=18.4,
        aspect="9:16",
        content_type="lifestyle",
        has_speech=True,
        speech_coverage=0.62,
        existing_music=False,
        overall_mood=["warm", "playful"],
        energy_mean=0.62,
        energy_curve=[EnergyPoint(t=0, energy=0.3), EnergyPoint(t=4, energy=0.8)],
        pacing="fast-cut",
        scenes=[
            SceneBeat(start=0, end=3.2, description="cafe exterior", energy=0.4, tags=["cafe"])
        ],
        hook_window=(9.0, 15.0),
        suggested_bpm=(95, 118),
        avoid=["dark cinematic drone", "aggressive trap", "lyrics-dense"],
        search_queries=["warm acoustic pop instrumental cafe"],
        platform_hint="instagram_story",
        analyzer="hybrid",
    )
    data = profile.model_dump(mode="json")
    again = VideoSonicProfile.model_validate(data)
    assert again.asset_id == "abc"
    assert again.pacing == "fast-cut"
    assert again.hook_window == (9.0, 15.0)
    assert again.suggested_bpm == (95, 118)
    schema = VideoSonicProfile.model_json_schema()
    required = set(schema.get("required") or [])
    for key in ("asset_id", "duration_sec", "aspect"):
        assert key in required
    properties = schema["properties"]
    for key in (
        "overall_mood",
        "energy_curve",
        "scenes",
        "hook_window",
        "suggested_bpm",
        "search_queries",
        "platform_hint",
        "analyzer",
    ):
        assert key in properties


def test_profile_fills_search_queries_when_missing():
    p = VideoSonicProfile(
        asset_id="x",
        duration_sec=10,
        aspect="9:16",
        has_speech=True,
        speech_coverage=0.5,
        overall_mood=["warm"],
        search_queries=[],
    )
    assert p.search_queries
    assert any("instrumental" in q for q in p.search_queries)


def test_track_energy_clamped():
    t = Track(id="t", title="x", energy=9)
    assert t.energy == 1.0
