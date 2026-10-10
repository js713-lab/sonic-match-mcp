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
from sonicmatch.config import load_settings
from sonicmatch.hosted.timeline import build_timeline
from sonicmatch.ingest import sanitize_asset_id
from sonicmatch.errors import SonicError

_ALLOWED_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
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


def search_catalog(query: str, limit: int = 12) -> dict[str, Any]:
    tools.configure(load_settings())
    found = tools.search_music(query=query.strip(), limit=limit, catalog="auto")
    if not found.get("ok", True) and found.get("ok") is False:
        return found
    tracks = [_slim_track(track) for track in found.get("tracks") or []]
    return {"ok": True, "query": query, "tracks": tracks, "notes": found.get("notes") or []}


_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def start_match(source: str, platform: str) -> str:
    """Run a match off the request so a slow download does not drop the page."""
    job_id = secrets.token_hex(8)
    with _jobs_lock:
        _jobs[job_id] = {"status": "working"}

    def run() -> None:
        try:
            result = match_source(source, platform)
        except Exception:
            logging.getLogger("sonicmatch.hosted").exception("portal match failed")
            result = {"ok": False, "error": "Match failed."}
        with _jobs_lock:
            _jobs[job_id] = {"status": "done", "result": result}

    threading.Thread(target=run, daemon=True).start()
    return job_id


def match_job(job_id: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"[a-f0-9]{16}", job_id or ""):
        return None
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def match_source(source: str, platform: str) -> dict[str, Any]:
    tools.configure(load_settings())
    platform = platform if platform in _PLATFORMS else "instagram_reel"
    ingested = tools.ingest_video(source, max_seconds=60)
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
