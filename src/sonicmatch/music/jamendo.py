"""Jamendo tracks API adapter. Optional — requires JAMENDO_CLIENT_ID."""

from __future__ import annotations

from typing import Any

import httpx

from sonicmatch.config import Settings
from sonicmatch.errors import SonicError
from sonicmatch.models import SearchQuery, Track

JAMENDO_URL = "https://api.jamendo.com/v3.0/tracks/"


def _cc_from_url(url: str | None) -> tuple[str, bool]:
    if not url:
        return ("Jamendo (see licenseccurl)", True)
    u = url.lower()
    if "publicdomain" in u or "/zero/" in u:
        return ("CC0-1.0", False)
    if "/by-nc" in u:
        return ("CC-BY-NC", True)
    if "/by-sa" in u:
        return ("CC-BY-SA", True)
    if "/by/" in u:
        return ("CC-BY", True)
    return (url, True)


def _map_track(item: dict[str, Any]) -> Track:
    musicinfo = item.get("musicinfo") or {}
    tags = musicinfo.get("tags") or {}
    moods = [str(x) for x in (tags.get("vartags") or tags.get("moods") or [])][:8]
    genres = [str(x) for x in (tags.get("genres") or [])][:8]
    instruments = [str(x) for x in (tags.get("instruments") or [])]
    vocaloverdubs = str(musicinfo.get("vocaloverdubs") or "").lower()
    vocalinstrumental = str(musicinfo.get("vocalinstrumental") or "").lower()
    instrumental = vocalinstrumental in {"instrumental", ""} and vocaloverdubs in {"", "none", "no"}
    # Jamendo sometimes puts vocals in tags
    if any(g.lower() in {"vocal", "vocals", "singer"} for g in genres + moods):
        instrumental = False
    bpm = None
    speed = musicinfo.get("speed") or item.get("speed")
    try:
        if speed:
            bpm = int(float(speed))
    except (TypeError, ValueError):
        bpm = None
    energy = 0.5
    if bpm:
        energy = max(0.15, min(0.95, (bpm - 60) / 100.0))
    license_name, attrib = _cc_from_url(item.get("license_ccurl") or item.get("licenseccurl"))
    artist = item.get("artist_name") or "Unknown"
    title = item.get("name") or "Untitled"
    duration = float(item.get("duration") or 0)
    tid = f"jamendo_{item.get('id')}"
    attrib_text = f'"{title}" by {artist} — {license_name} via Jamendo'
    if item.get("shareurl"):
        attrib_text += f" ({item['shareurl']})"
    return Track(
        id=tid,
        title=title,
        artist=artist,
        duration_sec=duration,
        bpm=bpm,
        energy=energy,
        moods=moods,
        genres=genres,
        instrumental=instrumental,
        loopable=duration >= 20,
        preview_url=item.get("audio") or item.get("audiodownload"),
        download_url=item.get("audiodownload") or item.get("audio"),
        license=license_name,
        attribution_required=attrib,
        attribution_text=attrib_text,
        source="jamendo",
        tags=instruments,
    )


class JamendoAdapter:
    name = "jamendo"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: dict[str, Track] = {}

    def get(self, track_id: str) -> Track | None:
        if track_id in self._cache:
            return self._cache[track_id]
        if not track_id.startswith("jamendo_"):
            return None
        raw_id = track_id.split("_", 1)[1]
        tracks = self._request({"id": raw_id, "limit": 1})
        return tracks[0] if tracks else None

    def search(self, query: SearchQuery) -> list[Track]:
        if not self.settings.has_jamendo:
            raise SonicError("JAMENDO_DISABLED", "JAMENDO_CLIENT_ID is not set.")
        params: dict[str, Any] = {
            "limit": max(1, min(query.limit, 25)),
            "include": "musicinfo+licenses",
            "audioformat": "mp32",
            "audiodlformat": "mp32",
        }
        q = query.query.strip()
        if q:
            params["search"] = q[:80]
            params["fuzzytags"] = q[:80]
        if query.instrumental is True:
            params["tags"] = ((params.get("tags") or "") + " instrumental").strip()
        if query.duration_min:
            params["durationbetween"] = f"{int(query.duration_min)}_{int(query.duration_max or 600)}"
        elif query.duration_max:
            params["durationbetween"] = f"0_{int(query.duration_max)}"
        # Jamendo's speed is not always BPM; still pass as a hint when we have a window.
        return self._request(params)

    def _request(self, extra: dict[str, Any]) -> list[Track]:
        params = {
            "client_id": self.settings.jamendo_client_id,
            "format": "json",
            **extra,
        }
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(JAMENDO_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPError as exc:
            raise SonicError("JAMENDO_FAILED", f"Jamendo request failed: {exc}") from exc
        except ValueError as exc:
            raise SonicError("JAMENDO_FAILED", "Jamendo returned invalid JSON.") from exc
        headers = payload.get("headers") or {}
        if headers.get("status") not in {"success", None, "Success"} and headers.get("code", 0) not in {0, "0"}:
            raise SonicError("JAMENDO_FAILED", f"Jamendo error: {headers}")
        results: list[Track] = []
        for item in payload.get("results") or []:
            track = _map_track(item)
            self._cache[track.id] = track
            results.append(track)
        return results
