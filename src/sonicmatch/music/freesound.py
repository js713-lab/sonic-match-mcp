"""Freesound adapter — loops and beds, not songs. Requires FREESOUND_API_KEY."""

from __future__ import annotations

from typing import Any

import httpx

from sonicmatch.config import Settings
from sonicmatch.errors import SonicError
from sonicmatch.models import SearchQuery, Track

FREESOUND_URL = "https://freesound.org/apiv2/search/text/"
FREESOUND_SOUND = "https://freesound.org/apiv2/sounds/{id}/"


def license_from_url(url: str | None) -> tuple[str, bool, bool]:
    """Return (license_name, attribution_required, commercial_ok-ish)."""
    if not url:
        return ("Freesound (see page)", True, False)
    u = url.lower()
    if "publicdomain" in u or "/zero/" in u:
        return ("CC0-1.0", False, True)
    if "sampling" in u:
        return ("CC-Sampling+", True, False)
    if "by-nc" in u:
        return ("CC-BY-NC", True, False)
    if "by-sa" in u:
        return ("CC-BY-SA", True, True)
    if "/by/" in u or "by-3" in u or "by-4" in u:
        return ("CC-BY", True, True)
    return (url, True, False)


def _map_sound(item: dict[str, Any]) -> Track:
    license_name, attrib, _ok = license_from_url(item.get("license"))
    tags = [str(t) for t in (item.get("tags") or [])][:12]
    previews = item.get("previews") or {}
    preview = (
        previews.get("preview-hq-mp3")
        or previews.get("preview-lq-mp3")
        or previews.get("preview-hq-ogg")
    )
    username = item.get("username") or "Unknown"
    name = item.get("name") or "Untitled"
    duration = float(item.get("duration") or 0)
    page = item.get("url") or f"https://freesound.org/s/{item.get('id')}/"
    moods = [t for t in tags if t.lower() in {"warm", "dark", "calm", "ambient", "loop", "drone"}]
    if not moods:
        moods = ["calm"] if duration > 20 else ["clean"]
    energy = 0.35
    blob = " ".join(tags).lower()
    if any(k in blob for k in ("kick", "drop", "hit", "impact")):
        energy = 0.75
    elif any(k in blob for k in ("pad", "drone", "ambient", "bed")):
        energy = 0.28
    attrib_text = f'"{name}" by {username} — {license_name} via Freesound ({page})'
    return Track(
        id=f"freesound_{item.get('id')}",
        title=name,
        artist=username,
        duration_sec=duration,
        bpm=None,
        energy=energy,
        moods=moods,
        genres=["bed", "sfx"] if duration < 8 else ["bed", "loop"],
        instrumental=True,
        loopable=True,
        preview_url=preview,
        download_url=preview,
        license=license_name,
        attribution_required=attrib,
        attribution_text=attrib_text,
        source="freesound",
        tags=tags,
    )


class FreesoundAdapter:
    name = "freesound"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: dict[str, Track] = {}

    def get(self, track_id: str) -> Track | None:
        if track_id in self._cache:
            return self._cache[track_id]
        if not track_id.startswith("freesound_"):
            return None
        if not self.settings.has_freesound:
            return None
        raw_id = track_id.split("_", 1)[1]
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(
                    FREESOUND_SOUND.format(id=raw_id),
                    params={
                        "token": self.settings.freesound_api_key,
                        "fields": "id,name,username,duration,license,tags,previews,url",
                    },
                )
                resp.raise_for_status()
                track = _map_sound(resp.json())
                self._cache[track.id] = track
                return track
        except httpx.HTTPError:
            return None

    def search(self, query: SearchQuery) -> list[Track]:
        if not self.settings.has_freesound:
            raise SonicError("FREESOUND_DISABLED", "FREESOUND_API_KEY is not set.")
        q = (query.query or "loop bed instrumental").strip()[:80]
        filt = []
        if query.duration_min is not None or query.duration_max is not None:
            lo = int(query.duration_min or 0)
            hi = int(query.duration_max or 300)
            filt.append(f"duration:[{lo} TO {hi}]")
        params: dict[str, Any] = {
            "query": q,
            "token": self.settings.freesound_api_key,
            "fields": "id,name,username,duration,license,tags,previews,url",
            "page_size": max(1, min(query.limit, 15)),
            "sort": "score",
        }
        if filt:
            params["filter"] = " ".join(filt)
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(FREESOUND_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPError as exc:
            raise SonicError("FREESOUND_FAILED", f"Freesound request failed: {exc}") from exc
        results: list[Track] = []
        for item in payload.get("results") or []:
            track = _map_sound(item)
            self._cache[track.id] = track
            results.append(track)
        return results
