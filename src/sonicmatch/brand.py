"""Brand-kit lock: BPM range, no vocals, mood whitelist — so a shop's videos stay on-brand."""

from __future__ import annotations

from pathlib import Path

from sonicmatch.config import Settings
from sonicmatch.errors import SonicError
from sonicmatch.models import BrandKit, VideoSonicProfile


def _dir(settings: Settings) -> Path:
    d = settings.cache_dir / "brand"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_brand_kit(kit: BrandKit, settings: Settings) -> BrandKit:
    name = "".join(ch for ch in kit.name.lower() if ch.isalnum() or ch in "-_")[:40]
    if not name:
        raise SonicError("BAD_ARGS", "brand kit name is required.")
    kit = kit.model_copy(update={"name": name})
    path = _dir(settings) / f"{name}.json"
    path.write_text(kit.model_dump_json(indent=2), encoding="utf-8")
    return kit


def load_brand_kit(name: str, settings: Settings) -> BrandKit:
    slug = "".join(ch for ch in name.lower() if ch.isalnum() or ch in "-_")
    path = _dir(settings) / f"{slug}.json"
    if not path.exists():
        raise SonicError("NOT_FOUND", f"Unknown brand kit: {name}")
    return BrandKit.model_validate_json(path.read_text(encoding="utf-8"))


def list_brand_kits(settings: Settings) -> list[str]:
    return sorted(p.stem for p in _dir(settings).glob("*.json"))


def apply_brand_kit(profile: VideoSonicProfile, kit: BrandKit) -> VideoSonicProfile:
    p = profile.model_copy(deep=True)
    if kit.moods:
        p.overall_mood = list(dict.fromkeys(kit.moods + p.overall_mood))
    if kit.avoid:
        p.avoid = list(dict.fromkeys(p.avoid + kit.avoid))
    lo, hi = p.suggested_bpm
    if kit.bpm_min is not None:
        lo = max(lo, kit.bpm_min)
    if kit.bpm_max is not None:
        hi = min(hi, kit.bpm_max)
    if lo > hi:
        lo, hi = hi, lo
    p.suggested_bpm = (lo, hi)
    if kit.instrumental_only:
        p.has_speech = True
        p.speech_coverage = max(p.speech_coverage, 0.26)
    if kit.genres:
        extra = [f"{' '.join(kit.moods[:2])} {' '.join(kit.genres[:2])} instrumental".strip()]
        p.search_queries = extra + p.search_queries
    return p
