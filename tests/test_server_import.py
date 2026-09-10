from __future__ import annotations

from sonicmatch.server import mcp


def test_tools_registered():
    names = {t.name for t in mcp._tool_manager.list_tools()}
    for expected in (
        "ingest_video",
        "analyze_video_music",
        "recommend_bgm",
        "search_music",
        "get_track",
        "preview_mix",
        "export_mix_spec",
        "suggest_cuts",
        "generate_bed",
        "save_brand_kit",
        "analyze_batch",
        "status",
    ):
        assert expected in names
