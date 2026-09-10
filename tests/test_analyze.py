from __future__ import annotations

from pathlib import Path

from sonicmatch.analyze.local import analyze_local
from sonicmatch.ingest import ingest_video
from sonicmatch.tools import analyze_video_music, configure
from tests.conftest import make_color_mp4


def test_local_analyze_fills_queries(color_mp4: Path, settings):
    asset = ingest_video(str(color_mp4), settings=settings)
    profile = analyze_local(asset, platform_hint="instagram_reel", extra_notes="cafe latte")
    assert profile.asset_id == asset.asset_id
    assert profile.search_queries
    assert profile.duration_sec > 0
    assert profile.hook_window[1] >= profile.hook_window[0]
    assert profile.analyzer == "local"


def test_analyze_tool_degrades_without_gemini(tmp_path: Path, settings, ffmpeg_ok: bool):
    if not ffmpeg_ok:
        return
    clip = make_color_mp4(tmp_path / "reel.mp4", seconds=2.0, size="360x640")
    configure(settings)
    from sonicmatch.ingest import ingest_video as ing

    asset = ing(str(clip), settings=settings)
    out = analyze_video_music(asset.asset_id, platform_hint="instagram_reel")
    assert out["ok"] is True
    assert out["profile"]["search_queries"]
    assert out["profile"]["analyzer"] in {"local", "hybrid", "gemini"}
