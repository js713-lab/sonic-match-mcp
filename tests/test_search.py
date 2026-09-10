from __future__ import annotations

from sonicmatch.models import VideoSonicProfile
from sonicmatch.tools import configure, get_track, recommend_bgm, search_music


def test_search_cafe_instrumental(settings):
    configure(settings)
    result = search_music("warm acoustic cafe", instrumental=True, limit=8)
    assert result["ok"] is True
    assert result["tracks"]
    assert all(t["instrumental"] for t in result["tracks"])


def test_recommend_without_asset_uses_prefs(settings):
    configure(settings)
    result = recommend_bgm(
        mood="warm",
        genre="acoustic",
        instrumental_only=True,
        max_results=5,
        catalog="seed",
        platform_hint="instagram_reel",
    )
    assert result["ok"] is True
    recs = result["recommendations"]
    assert 3 <= len(recs) <= 7
    top = recs[0]
    assert "reason" in top
    assert "license" in top["track"]
    assert len(top["suggested_in_out"]) == 2
    assert top["track"]["instrumental"] is True


def test_recommend_from_profile_speech_forces_instrumental(settings):
    configure(settings)
    profile = VideoSonicProfile(
        asset_id="p",
        duration_sec=12,
        aspect="9:16",
        has_speech=True,
        speech_coverage=0.7,
        overall_mood=["warm", "playful"],
        energy_mean=0.55,
        pacing="medium",
        suggested_bpm=(100, 118),
        search_queries=["warm acoustic instrumental cafe"],
        platform_hint="instagram_reel",
        analyzer="local",
    )
    result = recommend_bgm(profile=profile.model_dump(mode="json"), catalog="seed", max_results=5)
    assert result["ok"] is True
    assert result["instrumental_only"] is True
    assert all(r["track"]["instrumental"] for r in result["recommendations"])
    assert "license_warning" in result


def test_get_track_seed(settings):
    configure(settings)
    result = get_track("seed_golden_hour_latte")
    assert result["ok"] is True
    assert result["track"]["license"] == "CC0-1.0"


def test_get_unknown_track(settings):
    configure(settings)
    result = get_track("nope")
    assert result["ok"] is False
    assert result["code"] == "NOT_FOUND"
