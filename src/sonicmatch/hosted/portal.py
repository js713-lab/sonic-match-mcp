"""Website match and catalog search. The MCP port stays on /mcp."""

from __future__ import annotations

import json
import logging
import re
import secrets
import threading
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from sonicmatch import tools
from sonicmatch.config import Settings, load_settings
from sonicmatch.ffmpeg_util import synthesize_bed
from sonicmatch.hosted.timeline import build_timeline
from sonicmatch.ingest import discard_ingested_media, sanitize_asset_id
from sonicmatch.errors import SonicError
from sonicmatch.models import Track

_ALLOWED_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
_TRACK_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,80}$")
_preview_lock = threading.Lock()
_PLATFORMS = {
    "instagram_reel",
    "instagram_story",
    "tiktok",
    "youtube_short",
    "youtube_long",
    "generic",
}


def _slim_track(track: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "id",
        "title",
        "artist",
        "duration_sec",
        "bpm",
        "energy",
        "moods",
        "genres",
        "instrumental",
        "license",
        "attribution_text",
        "preview_url",
        "source",
        "tags",
    )
    return {key: track.get(key) for key in keep}


def _slim_rec(rec: dict[str, Any]) -> dict[str, Any]:
    window = rec.get("suggested_in_out") or [0, 0]
    return {
        "score": rec.get("score"),
        "reason": rec.get("reason") or "",
        "hook_in": window[0] if len(window) > 0 else 0,
        "hook_out": window[1] if len(window) > 1 else 0,
        "ducking": rec.get("ducking") or "off",
        "license_ok_for_platform": rec.get("license_ok_for_platform"),
        "track": _slim_track(rec.get("track") or {}),
    }


def _owned_audio(url: str, settings: Settings) -> Path | None:
    """A catalog file this process wrote under the cache. Never an arbitrary path."""
    if not url or url.startswith(("http://", "https://", "file:")):
        return None
    try:
        path = Path(url).expanduser().resolve()
    except OSError:
        return None
    root = settings.cache_dir.resolve()
    if path.is_file() and root in path.parents:
        return path
    return None


def preview_for_track(track: Track, settings: Settings) -> str | Path:
    """Real preview URL, a cached file, or a short demo bed at the track's BPM."""
    for url in (track.preview_url, track.download_url):
        if url and url.startswith("https://"):
            return url
    for url in (track.download_url, track.preview_url):
        owned = _owned_audio(url or "", settings)
        if owned:
            return owned
    dest = settings.cache_dir / "previews" / f"{track.id}.wav"
    with _preview_lock:
        if not dest.exists() or dest.stat().st_size < 64:
            synthesize_bed(
                dest,
                duration_sec=8,
                bpm=int(track.bpm or 110),
                energy=float(track.energy or 0.5),
            )
    return dest


def resolve_preview(track_id: str) -> str | Path:
    if not _TRACK_ID_RE.fullmatch(track_id or ""):
        raise ValueError("Unknown track.")
    settings = tools.configure(load_settings())
    try:
        track = tools.hub().get(track_id)
    except SonicError as exc:
        raise ValueError(exc.message) from exc
    if track is None:
        raise ValueError("Unknown track.")
    return preview_for_track(track, settings)


def search_catalog(query: str, limit: int = 12) -> dict[str, Any]:
    tools.configure(load_settings())
    found = tools.search_music(query=query.strip(), limit=limit, catalog="auto")
    if not found.get("ok", True) and found.get("ok") is False:
        return found
    tracks = [_slim_track(track) for track in found.get("tracks") or []]
    return {"ok": True, "query": query, "tracks": tracks, "notes": found.get("notes") or []}


# The public site runs this many matches at once. The rest wait in order.
MATCH_SLOTS = 5
_HOSTED_MAX_SECONDS = 60

_jobs: dict[str, dict[str, Any]] = {}
_queue: list[str] = []
_running = 0
_jobs_lock = threading.Lock()


def reset_match_slots() -> None:
    """Clear the hosted queue. Tests call this only after their workers have finished."""
    global _running
    with _jobs_lock:
        _jobs.clear()
        _queue.clear()
        _running = 0


def _ahead_locked(job_id: str) -> int:
    try:
        place = _queue.index(job_id)
    except ValueError:
        return _running
    return _running + place


def _pump_locked() -> None:
    global _running
    while _running < MATCH_SLOTS and _queue:
        job_id = _queue.pop(0)
        job = _jobs.get(job_id)
        if not job:
            continue
        job["status"] = "working"
        _running += 1
        threading.Thread(target=_run_match, args=(job_id,), daemon=True).start()


def _run_match(job_id: str) -> None:
    global _running
    with _jobs_lock:
        job = _jobs.get(job_id) or {}
        source = str(job.get("source") or "")
        platform = str(job.get("platform") or "")
    try:
        result = match_source(source, platform)
    except Exception:
        logging.getLogger("sonicmatch.hosted").exception("portal match failed")
        result = {"ok": False, "error": "Match failed."}
    if not isinstance(result, dict):
        result = {"ok": False, "error": "Match failed."}
    with _jobs_lock:
        others = any(
            other != job_id
            and str(item.get("source") or "") == source
            and item.get("status") in {"queued", "working"}
            for other, item in _jobs.items()
        )
        _jobs[job_id] = {"status": "done", "result": result}
        _running = max(0, _running - 1)
        _pump_locked()
    if source and not others:
        try:
            discard_ingested_media(
                source,
                _HOSTED_MAX_SECONDS,
                keep_profile=result.get("ok") is not False,
            )
        except Exception:
            logging.getLogger("sonicmatch.hosted").exception("media cleanup failed")


def start_match(source: str, platform: str) -> str:
    """Queue a match. At most MATCH_SLOTS run; the rest wait for a free slot."""
    job_id = secrets.token_hex(8)
    with _jobs_lock:
        _jobs[job_id] = {"status": "queued", "source": source, "platform": platform}
        _queue.append(job_id)
        _pump_locked()
    return job_id


def match_job(job_id: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"[a-f0-9]{16}", job_id or ""):
        return None
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        status = str(job.get("status") or "")
        if status == "done":
            return {"status": "done", "result": job.get("result")}
        if status == "queued":
            return {"status": "queued", "ahead": _ahead_locked(job_id)}
        return {"status": "working"}


def match_source(source: str, platform: str) -> dict[str, Any]:
    tools.configure(load_settings())
    platform = platform if platform in _PLATFORMS else "instagram_reel"
    ingested = tools.ingest_video(source, max_seconds=_HOSTED_MAX_SECONDS)
    if ingested.get("ok") is False:
        return ingested
    asset = ingested.get("asset") or {}
    asset_id = asset.get("asset_id") or ""
    analyzed = tools.analyze_video_music(asset_id, platform_hint=platform)
    if analyzed.get("ok") is False:
        return analyzed
    recs = tools.recommend_bgm(
        asset_id=asset_id,
        platform_hint=platform,
        max_results=7,
    )
    if recs.get("ok") is False:
        return recs
    profile = analyzed.get("profile") or {}
    recommendations = [_slim_rec(rec) for rec in recs.get("recommendations") or []]
    timeline = build_timeline(
        profile,
        recommendations,
        asset_id=asset_id,
        duration_sec=float(asset.get("duration_sec") or profile.get("duration_sec") or 0),
    )
    _write_timeline(timeline)
    return {
        "ok": True,
        "asset_id": asset_id,
        "duration_sec": asset.get("duration_sec"),
        "aspect": asset.get("aspect"),
        "platform": platform,
        "mood": profile.get("overall_mood") or [],
        "pacing": profile.get("pacing"),
        "hook_window": profile.get("hook_window"),
        "suggested_bpm": profile.get("suggested_bpm"),
        "speech_coverage": profile.get("speech_coverage"),
        "recommendations": recommendations,
        "timeline": timeline,
        "notes": (analyzed.get("notes") or []) + (recs.get("notes") or []),
        "license_warning": recs.get("license_warning") or "",
    }


def timeline_path(asset_id: str) -> Path:
    safe = sanitize_asset_id(asset_id)
    return load_settings().cache_dir / "timelines" / f"{safe}.json"


def _write_timeline(timeline: dict[str, Any]) -> None:
    path = timeline_path(str(timeline.get("asset_id") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(timeline), encoding="utf-8")


def load_timeline(asset_id: str) -> dict[str, Any] | None:
    try:
        path = timeline_path(asset_id)
    except SonicError:
        return None
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def save_upload(filename: str, data: bytes, directory: Path) -> Path:
    ext = Path(filename or "").suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise ValueError("Upload an mp4, mov, webm, mkv, or m4v.")
    if not data:
        raise ValueError("That file is empty.")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"portal-{secrets.token_hex(8)}{ext}"
    path.write_bytes(data)
    return path


def public_url(value: str) -> str:
    url = (value or "").strip()
    if url.lower().startswith("http://"):
        url = "https://" + url[7:]
    if not url.lower().startswith("https://") or re.search(r"\s", url):
        raise ValueError("Paste a public https link, or upload a file.")
    return url


def form_fields(body: bytes, content_type: str) -> dict[str, Any]:
    """Pull url, platform, and an optional file out of a portal request."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype == "application/json":
        data = json.loads(body.decode() or "{}")
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        return {"url": str(data.get("url") or ""), "platform": str(data.get("platform") or ""), "file": None}
    if ctype == "application/x-www-form-urlencoded":
        parsed = parse_qs(body.decode(), keep_blank_values=True)
        return {
            "url": (parsed.get("url") or [""])[0],
            "platform": (parsed.get("platform") or [""])[0],
            "file": None,
        }
    if ctype != "multipart/form-data":
        raise ValueError("Send the clip as a file or an https link.")
    match = re.search(r"boundary=([^;]+)", content_type, re.I)
    if not match:
        raise ValueError("Missing upload boundary.")
    boundary = match.group(1).strip().strip('"').encode()
    fields: dict[str, Any] = {"url": "", "platform": "", "file": None}
    for chunk in body.split(b"--" + boundary):
        if not chunk or chunk in {b"--", b"--\r\n"} or chunk.startswith(b"--"):
            continue
        chunk = chunk.strip(b"\r\n")
        if b"\r\n\r\n" not in chunk:
            continue
        head, payload = chunk.split(b"\r\n\r\n", 1)
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]
        header = head.decode("utf-8", "replace")
        name_match = re.search(r'name="([^"]+)"', header)
        if not name_match:
            continue
        name = name_match.group(1)
        file_match = re.search(r'filename="([^"]*)"', header)
        if file_match:
            fields["file"] = (file_match.group(1), payload)
        else:
            fields[name] = payload.decode("utf-8", "replace")
    return fields
