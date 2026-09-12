"""
sonicmatch-mcp — FastMCP server (stdio + streamable HTTP).

North star:
  ingest_video → analyze_video_music → recommend_bgm → preview_mix → export_mix_spec

Also: search_music, get_track, suggest_cuts, generate_bed, save_brand_kit,
analyze_batch, status.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # mcp 2.x renamed FastMCP → MCPServer
    from mcp.server import MCPServer as FastMCP

from sonicmatch import __version__
from sonicmatch import tools
from sonicmatch.config import load_settings

LOGGER = logging.getLogger("sonicmatch")

INSTRUCTIONS = """
You are talking to sonicmatch-mcp, infrastructure for editors and agents.

UX contract (Instagram Story/Reels *feeling*, not Instagram's catalog):
  ingest_video → analyze_video_music → recommend_bgm → preview_mix → export_mix_spec

Rules:
- Analyze the actual video (picture, motion, speech), not just a script.
- Prefer instrumental tracks when speech_coverage > 0.25.
- Recommend a 12–20s hook window, not the whole song.
- Always surface license + attribution. Track licenses ≠ this repo's MIT license.
- CC-BY-NC is never auto-recommended. For ads/shops use user-owned Artlist/Epidemic JSON.
- Never scrape or pretend to have Instagram / TikTok / YouTube Music official libraries.
- Never claim a track is an official platform sticker or Content-ID-safe.
- Never invent "trending" audio. That graph is closed.
- yt-dlp platform ingest is opt-in (SONICMATCH_ALLOW_YTDLP). Prefer local files.
- generate_bed requires i_understand_not_commercially_cleared=true.
- Return 3–7 tracks, each with a why-string.
- Do not send raw video bytes through the MCP payload; use asset_id.
- Generated beds are NOT catalog-cleared. Paid catalogs only via user-owned JSON.

Example user request:
  "I dropped ./clip.mp4. Analyze it for an Instagram Reel and recommend 5
   instrumental BGMs. Then mix the top pick with ducking and give me the ffmpeg command."
""".strip()

mcp = FastMCP("sonicmatch-mcp", instructions=INSTRUCTIONS)


@mcp.tool()
def status() -> dict[str, Any]:
    """Show ffmpeg/yt-dlp availability and which music adapters have keys."""
    return tools.status()


@mcp.tool()
def ingest_video(source: str, max_seconds: int = 180) -> dict[str, Any]:
    """Ingest a local video path or public http(s) URL.

    Accepts a filesystem path or an HTTPS video URL. YouTube/TikTok/Instagram
    via yt-dlp is OFF unless SONICMATCH_ALLOW_YTDLP=1 (ToS + extractor risk).
    Rejects file://, http, loopback, and private IPs (SSRF). Size-capped.

    Extracts duration/fps/aspect with ffprobe, a 16 kHz mono wav, up to 12 scene
    keyframes, and a 360p proxy. Returns an asset_id. Never returns video bytes.

    Call this first. Then call analyze_video_music with the asset_id.
    """
    return tools.ingest_video(source, max_seconds=max_seconds)


@mcp.tool()
def analyze_video_music(
    asset_id: str,
    platform_hint: str = "generic",
    extra_notes: str = "",
) -> dict[str, Any]:
    """Produce a structured VideoSonic profile for BGM matching.

    platform_hint: instagram_story | instagram_reel | tiktok | youtube_short |
    youtube_long | generic.

    Uses Gemini video understanding when GEMINI_API_KEY is set; otherwise local
    ffmpeg/audio heuristics (and optional faster-whisper / PySceneDetect if installed).
    Always fills search_queries even if analysis is weak.

    extra_notes: optional caption/script the user already has — used as a hint,
    not as a replacement for watching the video.
    """
    return tools.analyze_video_music(
        asset_id, platform_hint=platform_hint, extra_notes=extra_notes
    )


@mcp.tool()
def recommend_bgm(
    asset_id: Optional[str] = None,
    profile: Optional[dict[str, Any]] = None,
    genre: Optional[str] = None,
    mood: Optional[str] = None,
    instrumental_only: Optional[bool] = None,
    max_results: int = 5,
    catalog: str = "auto",
    platform_hint: Optional[str] = None,
    brand_kit: Optional[str] = None,
) -> dict[str, Any]:
    """Rank license-safe BGM. Pass asset_id and/or a VideoSonic profile.

    Defaults instrumental_only=True when speech_coverage > 0.25.
    catalog: auto | seed | jamendo | freesound | library
    auto = seed always, plus Jamendo/Freesound/user-library when configured.

    Each recommendation includes score, reason, suggested song in/out (12–20s
    high-energy slice), ducking hint, and license_ok_for_platform.
    max_results is clamped to 3–7.
    brand_kit: name previously saved with save_brand_kit.
    """
    return tools.recommend_bgm(
        asset_id=asset_id,
        profile=profile,
        genre=genre,
        mood=mood,
        instrumental_only=instrumental_only,
        max_results=max_results,
        catalog=catalog,
        platform_hint=platform_hint,
        brand_kit=brand_kit,
    )


@mcp.tool()
def search_music(
    query: str,
    bpm_min: Optional[int] = None,
    bpm_max: Optional[int] = None,
    instrumental: Optional[bool] = None,
    duration_min: Optional[float] = None,
    duration_max: Optional[float] = None,
    limit: int = 10,
    catalog: str = "auto",
) -> dict[str, Any]:
    """Free-text search over seed + optional Jamendo / Freesound / user library."""
    return tools.search_music(
        query=query,
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        instrumental=instrumental,
        duration_min=duration_min,
        duration_max=duration_max,
        limit=limit,
        catalog=catalog,
    )


@mcp.tool()
def get_track(track_id: str) -> dict[str, Any]:
    """Return one track's metadata, license string, attribution text, and URLs."""
    return tools.get_track(track_id)


@mcp.tool()
def preview_mix(
    asset_id: str,
    track_id: str,
    ducking: bool = True,
    bgm_db: float = -18,
    voice_db: float = -16,
) -> dict[str, Any]:
    """Mix BGM under the video: hook trim, loop if needed, optional speech ducking.

    Returns preview mp3 + low-res mp4 paths, the ffmpeg command, and a mix_spec
    JSON an editor (CapCut / Premiere / DaVinci / your agent) can re-apply.

    Ducking uses ffmpeg sidechaincompress when the video has speech.
    Seed tracks without audio files get a synthesized CC0 demo bed so the
    pipeline still runs offline.
    """
    return tools.preview_mix(
        asset_id,
        track_id,
        ducking=ducking,
        bgm_db=bgm_db,
        voice_db=voice_db,
    )


@mcp.tool()
def export_mix_spec(
    asset_id: str,
    track_id: str,
    ducking: bool = True,
    bgm_db: float = -18,
    voice_db: float = -16,
    render: bool = False,
) -> dict[str, Any]:
    """Export the mix spec + ffmpeg recipe + attribution without requiring a render.

    This is the editor companion output (CapCut / Premiere / DaVinci / agent).
    Set render=true to also write preview files (same as preview_mix).
    """
    return tools.export_mix_spec(
        asset_id,
        track_id,
        ducking=ducking,
        bgm_db=bgm_db,
        voice_db=voice_db,
        render=render,
    )


@mcp.tool()
def suggest_cuts(
    asset_id: str,
    bpm: Optional[float] = None,
    track_id: Optional[str] = None,
) -> dict[str, Any]:
    """Snap detected scene cuts onto a beat grid. Returns EDL-ish spans and intro/peak/outro acts.

    bpm defaults to the VideoSonic suggested_bpm midpoint, or the track BPM if track_id is set.
    """
    return tools.suggest_cuts(asset_id, bpm=bpm, track_id=track_id)


@mcp.tool()
def generate_bed(
    prompt: str,
    duration_sec: float = 16.0,
    bpm: int = 110,
    energy: float = 0.5,
    asset_id: Optional[str] = None,
    i_understand_not_commercially_cleared: bool = False,
) -> dict[str, Any]:
    """Generate a bed when the catalog misses. Always marked source=generated.

    Refuses unless i_understand_not_commercially_cleared=true. Local fallback is
    a sine-tremolo demo. NOT cleared for ads. Check Suno/Stable Audio/Lyria terms
    before swapping in a real generator. Generated tracks are excluded from
    recommend_bgm auto catalogs.
    """
    return tools.generate_bed(
        prompt=prompt,
        duration_sec=duration_sec,
        bpm=bpm,
        energy=energy,
        asset_id=asset_id,
        i_understand_not_commercially_cleared=i_understand_not_commercially_cleared,
    )


@mcp.tool()
def save_brand_kit(
    name: str,
    bpm_min: Optional[int] = None,
    bpm_max: Optional[int] = None,
    moods: Optional[list[str]] = None,
    genres: Optional[list[str]] = None,
    instrumental_only: bool = True,
    avoid: Optional[list[str]] = None,
    notes: str = "",
) -> dict[str, Any]:
    """Save a brand kit (BPM lock + no vocals + mood whitelist). Pass brand_kit=name to recommend_bgm."""
    return tools.save_brand_kit_tool(
        name=name,
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        moods=moods,
        genres=genres,
        instrumental_only=instrumental_only,
        avoid=avoid,
        notes=notes,
    )


@mcp.tool()
def analyze_batch(
    sources: list[str],
    platform_hint: str = "generic",
    extra_notes: str = "",
    max_seconds: int = 180,
) -> dict[str, Any]:
    """Analyze up to 20 clips, cluster moods, return one consistent mini-playlist for the series."""
    return tools.analyze_batch(
        sources=sources,
        platform_hint=platform_hint,
        extra_notes=extra_notes,
        max_seconds=max_seconds,
    )


@mcp.prompt()
def ig_music_sticker() -> str:
    """Score this video like an IG music sticker (energy + hook, license-safe)."""
    return (
        "Score this video like an Instagram music sticker — energy and hook, "
        "not genre trivia. Use sonicmatch-mcp:\n"
        "1) ingest_video with the local path or public URL\n"
        "2) analyze_video_music with platform_hint matching the target "
        "(instagram_reel / instagram_story / tiktok / youtube_short)\n"
        "3) recommend_bgm for 5 tracks; prefer instrumental if anyone is talking\n"
        "4) suggest_cuts so edits land on the beat\n"
        "5) preview_mix the top pick with ducking, then export_mix_spec\n"
        "Always quote license + attribution. Never claim official IG/TikTok catalog clearance."
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="sonicmatch-mcp",
        description="Video-native, license-first BGM matcher (MCP server).",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve streamable HTTP instead of stdio (for web editors).",
    )
    parser.add_argument("--host", default=None, help="HTTP host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="HTTP port (default 8765)")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return

    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    tools.configure(settings)

    if args.http:
        host = args.host or settings.http_host
        port = args.port or settings.http_port
        if host not in {"127.0.0.1", "localhost", "::1"}:
            LOGGER.warning(
                "HTTP MCP has no authentication. Binding %s:%s lets anyone who "
                "can reach that port ingest local files and mix. Prefer 127.0.0.1 "
                "unless you put a reverse proxy in front.",
                host,
                port,
            )
        LOGGER.info("sonicmatch-mcp %s streamable-http on %s:%s", __version__, host, port)
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        LOGGER.info("sonicmatch-mcp %s stdio", __version__)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
