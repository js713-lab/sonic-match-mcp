"""Day-1 product risks as gates, not slogans.

Content ID, yt-dlp ToS / broken extractors, upload size / SSRF,
Meta trending graphs, and generation-model commercial terms.
"""

from __future__ import annotations

import re
from typing import Any

from sonicmatch.models import Track

CONTENT_ID_WARNING = (
    "A Creative Commons or royalty-free label is not a Content ID waiver. "
    "YouTube/IG/TikTok can still match the recording. We never mark a track "
    "Content-ID-safe. Host files you have rights to, and check the platform "
    "before you publish."
)

YTDLP_TOS_WARNING = (
    "Platform URL ingest uses yt-dlp, which often breaks when extractors change "
    "and may violate YouTube/TikTok/Instagram terms. Default is off. Prefer a "
    "local file. Set SONICMATCH_ALLOW_YTDLP=1 only if you accept that risk."
)

TRENDING_WARNING = (
    "Instagram/TikTok/YouTube 'trending audio' is a closed platform graph. "
    "This server matches mood/pace of YOUR video against CC / RF / user-owned "
    "catalogs. It does not return viral sounds, official stickers, or Meta charts."
)

GENERATED_TERMS_WARNING = (
    "Generated audio is not a licensed catalog track. Suno, Stable Audio, Lyria, "
    "and similar tools have their own commercial terms. The local fallback is a "
    "sine-tremolo demo bed. Do not ship generated audio in ads or shop content "
    "unless you have read those terms and still want it. Pass "
    "i_understand_not_commercially_cleared=true to generate_bed."
)

SSRF_SIZE_WARNING = (
    "Remote ingest is HTTPS-only, rejects loopback/private IPs and file://, "
    "and is capped by SONICMATCH_MAX_DOWNLOAD_MB (default 200)."
)

_TRENDING = re.compile(
    r"\b("
    r"trending|"
    r"viral\s+(sound|audio|track)|"
    r"tiktok\s+sound|"
    r"instagram\s+audio|"
    r"ig\s+audio|"
    r"official\s+sticker|"
    r"meta\s+catalog|"
    r"for\s+you\s+page|"
    r"fyp\s+audio"
    r")\b",
    re.I,
)

_EXTRACTOR_HINTS = (
    "unsupported url",
    "unable to extract",
    "no video formats",
    "sign in to confirm",
    "http error 429",
    "http error 403",
    "this video is not available",
    "private video",
    "extractor",
)


def looks_like_trending_request(*parts: str | None) -> bool:
    blob = " ".join(p for p in parts if p)
    return bool(blob and _TRENDING.search(blob))


def content_id_risk(track: Track) -> str:
    """Never 'cleared'. CC/RF ≠ Content ID safe."""
    if track.source == "generated":
        return "likely"
    lic = (track.license or "").lower()
    if "generated" in lic or "not cleared" in lic:
        return "likely"
    return "unknown"


def ytdlp_extractor_failed(stderr: str) -> bool:
    text = (stderr or "").lower()
    return any(h in text for h in _EXTRACTOR_HINTS)


def track_risk_notes(track: Track) -> list[str]:
    notes = [CONTENT_ID_WARNING]
    if track.source == "generated":
        notes.append(GENERATED_TERMS_WARNING)
    if "nc" in (track.license or "").lower() or "noncommercial" in (track.license or "").lower():
        notes.append("This license is non-commercial (no ads / shops).")
    return notes


def day1_risks_status(allow_ytdlp: bool, max_download_mb: int) -> dict[str, Any]:
    return {
        "content_id": {
            "policy": "never_claim_cleared",
            "warning": CONTENT_ID_WARNING,
        },
        "ytdlp": {
            "enabled": allow_ytdlp,
            "default": False,
            "warning": YTDLP_TOS_WARNING,
        },
        "ssrf_and_size": {
            "https_only": True,
            "max_download_mb": max_download_mb,
            "warning": SSRF_SIZE_WARNING,
        },
        "trending": {
            "available": False,
            "warning": TRENDING_WARNING,
        },
        "generated_audio": {
            "commercially_cleared": False,
            "requires_ack": True,
            "warning": GENERATED_TERMS_WARNING,
        },
    }
