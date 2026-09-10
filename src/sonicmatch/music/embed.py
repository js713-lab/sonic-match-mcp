"""Deterministic tag embeddings (CLAP-shaped, no extra deps).

A 24-d vector from mood / genre / energy / BPM. Optional CLAP or LanceDB
can replace this later; ranking already consumes `Track.embed`.
"""

from __future__ import annotations

import math
from typing import Sequence

from sonicmatch.models import Track, VideoSonicProfile

MOOD_AXES = (
    "warm",
    "playful",
    "calm",
    "dark",
    "upbeat",
    "hype",
    "cozy",
    "sad",
    "tropical",
    "elegant",
    "chill",
    "clean",
    "adventurous",
    "celebratory",
    "understated",
    "melodic",
    "aggressive",
    "cinematic",
)

GENRE_AXES = (
    "acoustic",
    "electronic",
    "folk",
    "pop",
    "ambient",
    "hip hop",
    "world",
)


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("_", " ").replace("-", " ").split())


def _axis_hit(axes: Sequence[str], hay: Sequence[str]) -> list[float]:
    blob = {_norm(x) for x in hay}
    out: list[float] = []
    for axis in axes:
        a = _norm(axis)
        hit = 1.0 if a in blob or any(a in h or h in a for h in blob if h) else 0.0
        out.append(hit)
    return out


def embed_track(track: Track) -> list[float]:
    if track.embed and len(track.embed) >= 8:
        return [float(x) for x in track.embed]
    bpm = track.bpm or 110
    hay = list(track.moods) + list(track.genres) + list(track.tags) + [track.title]
    vec = [
        float(track.energy),
        max(0.0, min(1.0, (bpm - 60) / 100.0)),
        1.0 if track.instrumental else 0.0,
        1.0 if track.loopable else 0.0,
        *_axis_hit(MOOD_AXES, hay),
        *_axis_hit(GENRE_AXES, hay),
    ]
    return _l2(vec)


def embed_profile(profile: VideoSonicProfile) -> list[float]:
    bpm = sum(profile.suggested_bpm) / 2.0
    hay = list(profile.overall_mood) + [profile.content_type, profile.pacing]
    vec = [
        float(profile.energy_mean),
        max(0.0, min(1.0, (bpm - 60) / 100.0)),
        1.0 if profile.speech_coverage > 0.25 else 0.0,
        1.0 if profile.duration_sec <= 30 else 0.0,
        *_axis_hit(MOOD_AXES, hay),
        *_axis_hit(GENRE_AXES, hay + profile.search_queries),
    ]
    return _l2(vec)


def _l2(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / n, 6) for x in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.5
    n = min(len(a), len(b))
    if n == 0:
        return 0.5
    dot = sum(float(a[i]) * float(b[i]) for i in range(n))
    na = math.sqrt(sum(float(a[i]) * float(a[i]) for i in range(n))) or 1.0
    nb = math.sqrt(sum(float(b[i]) * float(b[i]) for i in range(n))) or 1.0
    return max(0.0, min(1.0, (dot / (na * nb) + 1.0) / 2.0))  # 0–1 from cosine [-1,1]


def ensure_embed(track: Track) -> Track:
    if track.embed:
        return track
    return track.model_copy(update={"embed": embed_track(track)})
