"""Hosted credit prices. Self-hosting the MIT repo does not use this meter."""

from __future__ import annotations

# Credits charged for a tools/call. Listing tools and status stay free.
TOOL_CREDITS: dict[str, int] = {
    "status": 0,
    "get_track": 0,
    "search_music": 1,
    "save_brand_kit": 1,
    "ingest_video": 2,
    "export_mix_spec": 2,
    "suggest_cuts": 3,
    "recommend_bgm": 4,
    "generate_bed": 5,
    "preview_mix": 6,
    "analyze_video_music": 8,
    "analyze_batch": 15,
}

# A tool we have not priced yet still costs something.
UNKNOWN_TOOL_CREDITS = 4

TRIAL_CREDITS = 25

# Published pack prices for the hosted endpoint. Card checkout is separate.
PACKS: tuple[dict[str, int | str], ...] = (
    {"id": "reel", "label": "Reel", "credits": 500, "usd": 9},
    {"id": "studio", "label": "Studio", "credits": 3000, "usd": 39},
)

PUBLIC_ORIGIN = "https://sonic.codecrafter.dev"
GITHUB_REPO = "https://github.com/js713-lab/sonic-match-mcp"


def credits_for(tool_name: str) -> int:
    return TOOL_CREDITS.get(tool_name, UNKNOWN_TOOL_CREDITS)
