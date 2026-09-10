from __future__ import annotations

from pathlib import Path

from sonicmatch.brand import apply_brand_kit, load_brand_kit
from sonicmatch.ingest import ingest_video
from sonicmatch.models import VideoSonicProfile
from sonicmatch.tools import configure, export_mix_spec, generate_bed, recommend_bgm, save_brand_kit_tool, suggest_cuts


def test_brand_kit_forces_instrumental(settings):
    configure(settings)
    out = save_brand_kit_tool(
        name="shop-kit",
        bpm_min=96,
        bpm_max=110,
        moods=["warm"],
        genres=["acoustic"],
        instrumental_only=True,
        avoid=["trap"],
    )
    assert out["ok"] is True
    kit = load_brand_kit("shop-kit", settings)
    profile = VideoSonicProfile(
        asset_id="p",
        duration_sec=12,
        aspect="9:16",
        speech_coverage=0.0,
        has_speech=False,
        overall_mood=["playful"],
        suggested_bpm=(80, 140),
        analyzer="local",
    )
    applied = apply_brand_kit(profile, kit)
    assert applied.speech_coverage >= 0.26
    assert applied.suggested_bpm[0] >= 96
    recs = recommend_bgm(
        profile=applied.model_dump(mode="json"),
        catalog="seed",
        brand_kit="shop-kit",
        max_results=5,
    )
    assert recs["ok"] is True
    assert recs["instrumental_only"] is True


def test_export_mix_spec_no_render(color_mp4: Path, settings):
    configure(settings)
    asset = ingest_video(str(color_mp4), settings=settings)
    from sonicmatch.analyze.merge import analyze_video_music

    analyze_video_music(asset.asset_id, platform_hint="instagram_reel", settings=settings)
    out = export_mix_spec(asset.asset_id, "seed_golden_hour_latte", render=False)
    assert out["ok"] is True
    assert out["mix_spec"]["rendered"] is False
    assert "ffmpeg" in out["ffmpeg_command"]
    assert out["mix_spec"]["license"]
    assert out["preview_video_path"] is None


def test_suggest_cuts_after_analyze(color_mp4: Path, settings):
    configure(settings)
    asset = ingest_video(str(color_mp4), settings=settings)
    from sonicmatch.analyze.merge import analyze_video_music

    analyze_video_music(asset.asset_id, settings=settings)
    plan = suggest_cuts(asset.asset_id, bpm=120)
    assert plan["ok"] is True
    assert plan["bpm"] == 120
    assert "edl" in plan


def test_generate_bed(settings):
    configure(settings)
    out = generate_bed(
        prompt="warm cafe instrumental",
        duration_sec=8,
        bpm=108,
        energy=0.5,
        i_understand_not_commercially_cleared=True,
    )
    assert out["ok"] is True
    assert out["track"]["source"] == "generated"
    assert "NOT" in out["warning"] or "not" in out["warning"].lower()
    assert Path(out["track"]["download_url"]).exists()
