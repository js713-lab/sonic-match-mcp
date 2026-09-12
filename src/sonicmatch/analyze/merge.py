"""Merge probe-grounded local heuristics with optional Gemini understanding."""

from __future__ import annotations

from pathlib import Path

from sonicmatch.config import Settings, load_settings
from sonicmatch.analyze.gemini import analyze_gemini
from sonicmatch.analyze.local import analyze_local
from sonicmatch.errors import SonicError
from sonicmatch.ingest import load_asset, sanitize_asset_id, save_asset
from sonicmatch.models import VideoSonicProfile


def _save_profile(settings: Settings, profile: VideoSonicProfile) -> None:
    path = settings.cache_dir / "assets" / profile.asset_id / "profile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")


def load_profile(asset_id: str, settings: Settings | None = None) -> VideoSonicProfile | None:
    settings = settings or load_settings()
    try:
        safe = sanitize_asset_id(asset_id)
    except SonicError:
        return None
    path = settings.cache_dir / "assets" / safe / "profile.json"
    if not path.exists():
        return None
    return VideoSonicProfile.model_validate_json(path.read_text(encoding="utf-8"))


def merge_profiles(local: VideoSonicProfile, gemini: VideoSonicProfile) -> VideoSonicProfile:
    """Gemini owns mood/scenes/queries; local probe always owns duration/aspect/asset_id."""
    merged = gemini.model_copy(deep=True)
    merged.asset_id = local.asset_id
    merged.duration_sec = local.duration_sec
    merged.aspect = local.aspect
    merged.analyzer = "hybrid"
    # If Gemini omitted curve, keep local energy.
    if not merged.energy_curve and local.energy_curve:
        merged.energy_curve = local.energy_curve
        merged.energy_mean = local.energy_mean
    if not merged.scenes and local.scenes:
        merged.scenes = local.scenes
    if not merged.search_queries:
        merged.search_queries = local.search_queries
    if not merged.overall_mood:
        merged.overall_mood = local.overall_mood
    # Prefer the more conservative speech flag (don't duck into vocals by accident).
    merged.has_speech = merged.has_speech or local.has_speech
    merged.speech_coverage = max(merged.speech_coverage, local.speech_coverage)
    merged.degraded = list(dict.fromkeys(local.degraded + gemini.degraded))
    if merged.platform_hint == "generic" and local.platform_hint != "generic":
        merged.platform_hint = local.platform_hint
    return merged


def analyze_video_music(
    asset_id: str,
    platform_hint: str = "generic",
    extra_notes: str = "",
    settings: Settings | None = None,
    force: bool = False,
) -> VideoSonicProfile:
    settings = settings or load_settings()
    cached = None if force else load_profile(asset_id, settings)
    if cached and not extra_notes:
        return cached

    asset = load_asset(asset_id, settings)
    local = analyze_local(asset, platform_hint=platform_hint, extra_notes=extra_notes)

    if not settings.has_gemini:
        local.degraded = list(dict.fromkeys(local.degraded + ["gemini-disabled"]))
        _save_profile(settings, local)
        return local

    try:
        gemini = analyze_gemini(
            asset,
            settings,
            platform_hint=platform_hint,
            extra_notes=extra_notes,
        )
        profile = merge_profiles(local, gemini)
    except SonicError as exc:
        local.degraded = list(dict.fromkeys(local.degraded + [f"gemini:{exc.code}"]))
        profile = local

    _save_profile(settings, profile)
    try:
        save_asset(settings, asset)
    except Exception:
        pass
    return profile
