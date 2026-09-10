"""Pydantic v2 I/O models for every MCP tool."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


SourceType = Literal["file", "url"]
Pacing = Literal["slow", "medium", "fast-cut"]
Analyzer = Literal["gemini", "local", "hybrid"]
PlatformHint = Literal[
    "instagram_story",
    "instagram_reel",
    "tiktok",
    "youtube_short",
    "youtube_long",
    "generic",
]
TrackSource = Literal["seed", "jamendo", "freesound", "generated", "library"]
DuckingMode = Literal["recommended", "off"]
CatalogName = Literal["auto", "seed", "jamendo", "freesound", "library"]
CATALOG_CHOICES = ("auto", "seed", "jamendo", "freesound", "library")


class VideoAsset(BaseModel):
    asset_id: str
    source_type: SourceType
    local_path: str
    duration_sec: float
    width: int
    height: int
    fps: float
    aspect: str
    has_audio: bool
    probe_json: dict[str, Any] = Field(default_factory=dict)
    original_source: str = ""
    audio_path: Optional[str] = None
    keyframe_paths: list[str] = Field(default_factory=list)
    proxy_path: Optional[str] = None
    silence_ratio: Optional[float] = None
    degraded: list[str] = Field(default_factory=list)


class SceneBeat(BaseModel):
    start: float
    end: float
    description: str = ""
    energy: float = Field(ge=0.0, le=1.0, default=0.5)
    tags: list[str] = Field(default_factory=list)

    @field_validator("energy", mode="before")
    @classmethod
    def _clamp_energy(cls, v: Any) -> float:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return 0.5
        return max(0.0, min(1.0, x))


class EnergyPoint(BaseModel):
    t: float
    energy: float = Field(ge=0.0, le=1.0)

    @field_validator("energy", mode="before")
    @classmethod
    def _clamp_energy(cls, v: Any) -> float:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, x))


class VideoSonicProfile(BaseModel):
    asset_id: str
    duration_sec: float
    aspect: str
    content_type: str = "lifestyle"
    has_speech: bool = False
    speech_coverage: float = Field(ge=0.0, le=1.0, default=0.0)
    existing_music: bool = False
    overall_mood: list[str] = Field(default_factory=list)
    energy_mean: float = Field(ge=0.0, le=1.0, default=0.5)
    energy_curve: list[EnergyPoint] = Field(default_factory=list)
    pacing: Pacing = "medium"
    scenes: list[SceneBeat] = Field(default_factory=list)
    hook_window: tuple[float, float] = (0.0, 6.0)
    suggested_bpm: tuple[int, int] = (90, 120)
    avoid: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    platform_hint: PlatformHint = "generic"
    analyzer: Analyzer = "local"
    degraded: list[str] = Field(default_factory=list)

    @field_validator("speech_coverage", "energy_mean", mode="before")
    @classmethod
    def _clamp_unit(cls, v: Any) -> float:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, x))

    @field_validator("pacing", mode="before")
    @classmethod
    def _norm_pacing(cls, v: Any) -> str:
        s = str(v or "medium").strip().lower().replace("_", "-")
        if s in {"fast", "fastcut", "fast-cuts", "quick"}:
            return "fast-cut"
        if s in {"slow", "medium", "fast-cut"}:
            return s
        return "medium"

    @field_validator("platform_hint", mode="before")
    @classmethod
    def _norm_platform(cls, v: Any) -> str:
        s = str(v or "generic").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "ig_story": "instagram_story",
            "story": "instagram_story",
            "ig_reel": "instagram_reel",
            "reel": "instagram_reel",
            "reels": "instagram_reel",
            "shorts": "youtube_short",
            "yt_short": "youtube_short",
            "yt_long": "youtube_long",
            "youtube": "youtube_long",
        }
        s = aliases.get(s, s)
        allowed = {
            "instagram_story",
            "instagram_reel",
            "tiktok",
            "youtube_short",
            "youtube_long",
            "generic",
        }
        return s if s in allowed else "generic"

    @field_validator("hook_window", mode="before")
    @classmethod
    def _hook_tuple(cls, v: Any) -> tuple[float, float]:
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            return (float(v[0]), float(v[1]))
        return (0.0, 6.0)

    @field_validator("suggested_bpm", mode="before")
    @classmethod
    def _bpm_tuple(cls, v: Any) -> tuple[int, int]:
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            lo, hi = int(v[0]), int(v[1])
            if lo > hi:
                lo, hi = hi, lo
            return (max(40, lo), min(220, hi))
        return (90, 120)

    @model_validator(mode="after")
    def _ensure_queries(self) -> "VideoSonicProfile":
        if not self.search_queries:
            moods = " ".join(self.overall_mood[:2]) or "neutral"
            inst = "instrumental" if self.has_speech or self.speech_coverage > 0.25 else ""
            bpm = f"{self.suggested_bpm[0]}-{self.suggested_bpm[1]}bpm"
            self.search_queries = [
                f"{moods} {self.content_type} {inst}".strip(),
                f"{moods} {inst} {bpm}".strip(),
                f"{self.pacing} {self.content_type} bed {inst}".strip(),
            ]
        return self


class Track(BaseModel):
    id: str
    title: str
    artist: str = "Unknown"
    duration_sec: float = 120.0
    bpm: Optional[int] = None
    energy: float = Field(ge=0.0, le=1.0, default=0.5)
    moods: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    instrumental: bool = True
    loopable: bool = False
    preview_url: Optional[str] = None
    download_url: Optional[str] = None
    license: str = "Unknown"
    attribution_required: bool = True
    attribution_text: str = ""
    source: TrackSource = "seed"
    embed: Optional[list[float]] = None
    tags: list[str] = Field(default_factory=list)
    # CC/RF is not a Content ID waiver. Never set this to "cleared".
    content_id_risk: Literal["unknown", "likely"] = "unknown"

    @field_validator("energy", mode="before")
    @classmethod
    def _clamp_energy(cls, v: Any) -> float:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return 0.5
        return max(0.0, min(1.0, x))


class Recommendation(BaseModel):
    track: Track
    score: float
    reason: str
    suggested_in_out: tuple[float, float]
    ducking: DuckingMode = "off"
    # Declared license is not NC. NOT Content ID / Meta sticker clearance.
    license_ok_for_platform: bool = False
    content_id_risk: Literal["unknown", "likely"] = "unknown"

    @field_validator("suggested_in_out", mode="before")
    @classmethod
    def _io_tuple(cls, v: Any) -> tuple[float, float]:
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            return (float(v[0]), float(v[1]))
        return (0.0, 15.0)


class MixResult(BaseModel):
    preview_audio_path: Optional[str] = None
    preview_video_path: Optional[str] = None
    ffmpeg_command: str = ""
    mix_spec: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class CutHint(BaseModel):
    scene_t: float
    beat_t: float
    delta_sec: float
    bar: int = 1
    kind: str = "scene"


class CutPlan(BaseModel):
    asset_id: str
    bpm: float
    beat_grid: list[float] = Field(default_factory=list)
    scene_cuts: list[float] = Field(default_factory=list)
    suggested_cuts: list[CutHint] = Field(default_factory=list)
    acts: list[dict[str, Any]] = Field(default_factory=list)
    edl: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BrandKit(BaseModel):
    name: str
    bpm_min: Optional[int] = None
    bpm_max: Optional[int] = None
    moods: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    instrumental_only: bool = True
    avoid: list[str] = Field(default_factory=list)
    energy_min: Optional[float] = None
    energy_max: Optional[float] = None
    notes: str = ""


class SearchQuery(BaseModel):
    query: str = ""
    bpm_min: Optional[int] = None
    bpm_max: Optional[int] = None
    instrumental: Optional[bool] = None
    duration_min: Optional[float] = None
    duration_max: Optional[float] = None
    moods: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    limit: int = 10


class ToolError(BaseModel):
    ok: Literal[False] = False
    code: str
    error: str
