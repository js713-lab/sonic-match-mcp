from __future__ import annotations

from pathlib import Path

from sonicmatch.ingest import ingest_video
from sonicmatch.mix import preview_mix
from sonicmatch.music.seed import SeedAdapter
from sonicmatch.tools import configure, generate_bed, recommend_bgm


def test_preview_mix_writes_files(color_mp4: Path, settings):
    configure(settings)
    asset = ingest_video(str(color_mp4), settings=settings)
    track = SeedAdapter().get("seed_golden_hour_latte")
    assert track is not None
    result = preview_mix(asset.asset_id, track, ducking=True, settings=settings)
    assert result.preview_video_path and Path(result.preview_video_path).exists()
    assert result.preview_audio_path and Path(result.preview_audio_path).exists()
    assert "ffmpeg" in result.ffmpeg_command
    assert result.mix_spec["track_id"] == track.id
    assert any("license" in n.lower() or "sticker" in n.lower() for n in result.notes)


def test_preview_mix_uses_generated_local_file(color_mp4: Path, settings):
    configure(settings)
    asset = ingest_video(str(color_mp4), settings=settings)
    gen = generate_bed(
        prompt="warm cafe",
        duration_sec=8,
        bpm=108,
        i_understand_not_commercially_cleared=True,
    )
    assert gen["ok"]
    local = Path(gen["track"]["download_url"])
    assert local.exists()
    from sonicmatch.tools import preview_mix as tool_mix

    mixed = tool_mix(asset.asset_id, gen["track"]["id"], ducking=False)
    assert mixed["ok"] is True
    assert any("local audio" in n for n in mixed["notes"])


def test_recommend_then_get_top_id(settings):
    configure(settings)
    recs = recommend_bgm(
        mood="warm",
        instrumental_only=True,
        catalog="seed",
        max_results=5,
        platform_hint="instagram_reel",
    )
    assert recs["ok"]
    assert recs["recommendations"][0]["track"]["id"].startswith("seed_")
