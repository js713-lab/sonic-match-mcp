"""Optional generate path. Always marked source=generated.

Commercial terms of Suno / Stable Audio / Lyria are messy — this tool will
not pretend a generated bed is cleared for ads. Without an external API key
it synthesizes a local CC0-ish sine bed so the pipeline still demos.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sonicmatch.config import Settings
from sonicmatch.errors import SonicError
from sonicmatch.ffmpeg_util import synthesize_bed, which_ffmpeg
from sonicmatch.models import Track


def generate_bed(
    *,
    prompt: str,
    duration_sec: float = 16.0,
    bpm: int = 110,
    energy: float = 0.5,
    settings: Settings,
) -> Track:
    """Create a generated bed file in the cache and return a Track pointing at it."""
    which_ffmpeg()
    prompt = (prompt or "neutral instrumental bed").strip()[:160]
    duration_sec = max(4.0, min(float(duration_sec), 60.0))
    bpm = max(60, min(int(bpm), 180))
    energy = max(0.05, min(float(energy), 1.0))
    hid = hashlib.sha256(f"{prompt}|{duration_sec}|{bpm}|{energy}".encode()).hexdigest()[:12]
    dest = settings.cache_dir / "generated" / f"gen_{hid}.wav"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        synthesize_bed(dest, duration_sec=duration_sec, bpm=bpm, energy=energy)
    if not dest.exists():
        raise SonicError("GENERATE_FAILED", "Could not synthesize a demo bed.")
    title = f"Generated: {prompt[:48]}"
    return Track(
        id=f"generated_{hid}",
        title=title,
        artist="sonicmatch-generate",
        duration_sec=duration_sec,
        bpm=bpm,
        energy=energy,
        moods=[w for w in prompt.lower().split() if w.isalpha()][:4] or ["neutral"],
        genres=["generated", "bed"],
        instrumental=True,
        loopable=True,
        preview_url=None,
        download_url=str(dest),
        license="generated-demo — NOT cleared for commercial use; check model terms",
        attribution_required=True,
        attribution_text=(
            f"{title} — generated locally by sonicmatch-mcp. "
            "Not an official catalog track. Do not ship this sine bed in ads."
        ),
        source="generated",
        tags=["generated", "demo"],
        content_id_risk="likely",
    )
