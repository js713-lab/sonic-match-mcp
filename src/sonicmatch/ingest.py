"""Ingest local files and public URLs into a cached VideoAsset. Never return bytes."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from sonicmatch.config import Settings, load_settings
from sonicmatch.errors import SonicError
from sonicmatch.audio import dump_audio_stats, probe_audio
from sonicmatch.ffmpeg_util import (
    aspect_label,
    extract_audio_wav,
    extract_scene_keyframes,
    ffprobe,
    make_proxy,
    which_ffmpeg,
)
from sonicmatch.models import VideoAsset
from sonicmatch.policy import YTDLP_TOS_WARNING, ytdlp_extractor_failed
from sonicmatch.ssrf import classify_url, fetch_https_capped, parse_source_url

_ASSET_INDEX = "index.json"
_ASSET_ID_RE = re.compile(r"^[0-9a-f]{8,32}$")


def sanitize_asset_id(asset_id: str) -> str:
    """Reject path traversal and non-hex ids before joining onto the cache dir."""
    value = (asset_id or "").strip().lower()
    if not _ASSET_ID_RE.fullmatch(value):
        raise SonicError("ASSET_NOT_FOUND", f"Unknown asset_id: {asset_id}")
    return value


def _hash_id(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", errors="replace"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def _clamp_seconds(max_seconds: int) -> int:
    if max_seconds <= 0:
        return 180
    return min(int(max_seconds), 600)


def _is_inside(path: Path, root: Path) -> bool:
    """True when path itself sits under root. Does not follow symlinks."""
    try:
        path.absolute().relative_to(root.absolute())
    except ValueError:
        return False
    return True


_MEDIA_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".wav", ".jpg", ".jpeg", ".png"}


def _asset_id_for(source: str, max_seconds: int) -> str | None:
    """Same id ingest_video will use, so a finished job can find its cache."""
    source = source.strip().strip("\"'")
    if not source:
        return None
    seconds = str(_clamp_seconds(max_seconds))
    if source.lower().startswith(("http://", "https://")):
        return _hash_id("url", source, seconds)
    path = Path(source).expanduser()
    if not path.is_file():
        return None
    path = path.resolve()
    st = path.stat()
    return _hash_id("file", str(path), str(st.st_mtime_ns), str(st.st_size), seconds)


def _unlink_inside(path: Path, root: Path) -> None:
    if path.is_symlink():
        if _is_inside(path, root):
            path.unlink(missing_ok=True)
        return
    if path.is_file() and _is_inside(path, root):
        path.unlink(missing_ok=True)


def _strip_media(adir: Path, root: Path) -> None:
    for path in list(adir.rglob("*")):
        if not _is_inside(path, root):
            continue
        if path.is_symlink() or (path.is_file() and path.suffix.lower() in _MEDIA_SUFFIXES):
            path.unlink(missing_ok=True)
    frames = adir / "frames"
    if frames.is_dir() and _is_inside(frames, root) and not any(frames.iterdir()):
        frames.rmdir()


def _remove_tree(path: Path, root: Path) -> None:
    if not _is_inside(path, root):
        return
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
        return
    if not path.is_dir():
        return
    for child in list(path.iterdir()):
        _remove_tree(child, root)
    if _is_inside(path, root):
        path.rmdir()


def discard_ingested_media(
    source: str,
    max_seconds: int,
    *,
    keep_profile: bool,
    settings: Settings | None = None,
) -> None:
    """Drop the upload or download after a hosted match. The timeline JSON stays.

    A file outside the cache is left alone. On success the small profile stays so
    the same link does not need the video again. On failure the asset cache goes
    too, so a retry can fetch a fresh copy.
    """
    settings = settings or load_settings()
    root = settings.cache_dir.resolve()
    source = (source or "").strip().strip("\"'")
    if not source:
        return
    asset_id = _asset_id_for(source, max_seconds)
    portal_file: Path | None = None
    if not source.lower().startswith(("http://", "https://")):
        candidate = Path(source).expanduser()
        portal = root / "portal"
        if candidate.is_file() or candidate.is_symlink():
            if _is_inside(candidate, portal):
                portal_file = candidate
    adir = (root / "assets" / asset_id) if asset_id else None
    if adir is not None and adir.is_dir() and _is_inside(adir, root / "assets"):
        profile = adir / "profile.json"
        if keep_profile and profile.is_file():
            _strip_media(adir, root)
        else:
            _remove_tree(adir, root)
    if portal_file is not None:
        _unlink_inside(portal_file, root)


def _asset_dir(settings: Settings, asset_id: str) -> Path:
    d = settings.cache_dir / "assets" / asset_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_asset(settings: Settings, asset: VideoAsset) -> None:
    path = _asset_dir(settings, asset.asset_id) / _ASSET_INDEX
    path.write_text(asset.model_dump_json(indent=2), encoding="utf-8")


def load_asset(asset_id: str, settings: Settings | None = None) -> VideoAsset:
    settings = settings or load_settings()
    safe = sanitize_asset_id(asset_id)
    path = settings.cache_dir / "assets" / safe / _ASSET_INDEX
    if not path.exists():
        raise SonicError("ASSET_NOT_FOUND", f"Unknown asset_id: {asset_id}")
    return VideoAsset.model_validate_json(path.read_text(encoding="utf-8"))


def _parse_probe(probe: dict[str, Any]) -> dict[str, Any]:
    fmt = probe.get("format") or {}
    streams = probe.get("streams") or []
    vstreams = [s for s in streams if s.get("codec_type") == "video"]
    astreams = [s for s in streams if s.get("codec_type") == "audio"]
    vs = vstreams[0] if vstreams else {}
    width = int(vs.get("width") or 0)
    height = int(vs.get("height") or 0)
    fps = 0.0
    rate = vs.get("avg_frame_rate") or vs.get("r_frame_rate") or "0/1"
    if isinstance(rate, str) and "/" in rate:
        num, den = rate.split("/", 1)
        try:
            fps = float(num) / float(den) if float(den) else 0.0
        except ValueError:
            fps = 0.0
    elif rate:
        try:
            fps = float(rate)
        except (TypeError, ValueError):
            fps = 0.0
    try:
        duration = float(fmt.get("duration") or vs.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration_sec": duration,
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "aspect": aspect_label(width, height),
        "has_audio": bool(astreams),
    }


def _copy_or_link(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    try:
        dest.symlink_to(src)
        return dest
    except OSError:
        shutil.copy2(src, dest)
        return dest


def _download_direct(url: str, dest: Path, settings: Settings) -> Path:
    parse_source_url(url)
    max_bytes = settings.max_download_mb * 1024 * 1024
    fetch_https_capped(url, dest, max_bytes=max_bytes)
    return dest


_ytdlp_lock = threading.Lock()


def _yt_dlp_download(url: str, dest_dir: Path, max_seconds: int, max_mb: int) -> Path:
    """Fetch only the opening of a platform video. One download at a time."""
    with _ytdlp_lock:
        return _yt_dlp_download_locked(url, dest_dir, max_seconds, max_mb)


def _yt_dlp_download_locked(url: str, dest_dir: Path, max_seconds: int, max_mb: int) -> Path:
    binary = shutil.which("yt-dlp")
    if not binary:
        raise SonicError(
            "YTDLP_MISSING",
            "yt-dlp is not on PATH. Prefer a local file. "
            + YTDLP_TOS_WARNING,
        )
    window = max(15, min(int(max_seconds), 75))
    try:
        probe = subprocess.run(
            [
                binary,
                "-f",
                "18/b[height<=360][ext=mp4]/b[height<=480]",
                "-g",
                "--no-playlist",
                "--no-warnings",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SonicError(
            "TIMEOUT",
            "YouTube did not answer in time. Upload the clip instead.",
        ) from exc
    if probe.returncode != 0:
        blob = (probe.stderr or probe.stdout or "").strip()
        tail = " | ".join(blob.splitlines()[-4:])
        if ytdlp_extractor_failed(blob):
            raise SonicError(
                "YTDLP_EXTRACTOR",
                "yt-dlp extractor failed or the platform blocked the download. "
                "Pass a local file instead. " + tail,
            )
        raise SonicError("DOWNLOAD_FAILED", "yt-dlp failed: " + tail)
    media = ""
    for line in (probe.stdout or "").splitlines():
        if line.startswith("https://"):
            media = line.strip()
            break
    if not media:
        raise SonicError("DOWNLOAD_FAILED", "yt-dlp did not return a video URL.")
    nbytes = min(12 * 1024 * 1024, max(4 * 1024 * 1024, 160_000 * window))
    grab = dest_dir / "range.mp4"
    local = dest_dir / "source.mp4"
    try:
        fetched = subprocess.run(
            ["curl", "-fL", "--retry", "1", "--range", f"0-{nbytes - 1}", "-o", str(grab), media],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        grab.unlink(missing_ok=True)
        raise SonicError(
            "TIMEOUT",
            "The YouTube opening downloaded too slowly. Upload the clip instead.",
        ) from exc
    if fetched.returncode != 0 or not grab.exists() or grab.stat().st_size < 80_000:
        grab.unlink(missing_ok=True)
        raise SonicError(
            "DOWNLOAD_FAILED",
            "Could not fetch the opening of that YouTube video. Upload the clip instead.",
        )
    if grab.stat().st_size > max_mb * 1024 * 1024:
        grab.unlink(missing_ok=True)
        raise SonicError("TOO_LARGE", f"yt-dlp file exceeded {max_mb} MB.")
    cut = subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-t", str(window),
            "-i", str(grab),
            "-c", "copy",
            "-movflags", "+faststart",
            str(local),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    grab.unlink(missing_ok=True)
    if cut.returncode != 0 or not local.exists() or local.stat().st_size < 40_000:
        local.unlink(missing_ok=True)
        raise SonicError(
            "DOWNLOAD_FAILED",
            "That YouTube opening could not be cut. Upload the clip instead.",
        )
    return local


def ingest_video(
    source: str,
    max_seconds: int = 180,
    settings: Settings | None = None,
) -> VideoAsset:
    """
    Accept a local path or public URL, cache a proxy + wav + keyframes, return VideoAsset.

    Never returns raw video bytes. Re-ingest of the same URL/file hash is a cache hit.
    """
    settings = settings or load_settings()
    settings.ensure_dirs()
    source = source.strip().strip("\"'")
    if not source:
        raise SonicError("BAD_SOURCE", "source is required (local path or http(s) URL).")
    max_seconds = _clamp_seconds(max_seconds)

    degraded: list[str] = []
    is_url = source.lower().startswith(("http://", "https://", "file:"))
    if source.lower().startswith("file:"):
        raise SonicError("SSRF_REJECTED", "file:// URLs are not allowed. Pass a local filesystem path.")

    if is_url:
        kind = classify_url(source)
        asset_id = _hash_id("url", source, str(max_seconds))
        adir = _asset_dir(settings, asset_id)
        index = adir / _ASSET_INDEX
        if index.exists():
            return VideoAsset.model_validate_json(index.read_text(encoding="utf-8"))
        local = adir / "source.mp4"
        if kind == "platform":
            if not settings.allow_ytdlp:
                raise SonicError(
                    "YTDLP_DISABLED",
                    "Platform URL ingest is off by default. "
                    + YTDLP_TOS_WARNING
                    + " Pass a local file, or set SONICMATCH_ALLOW_YTDLP=1.",
                )
            downloaded = _yt_dlp_download(
                source, adir, max_seconds, settings.max_download_mb
            )
            if downloaded.resolve() != local.resolve():
                if local.exists():
                    local.unlink()
                downloaded.rename(local)
        else:
            _download_direct(source, local, settings)
        source_type: str = "url"
        original = source
    else:
        path = Path(source).expanduser()
        if not path.exists():
            # Common UX: relative path from the editor cwd.
            alt = Path.cwd() / source
            if alt.exists():
                path = alt
            else:
                raise SonicError("NOT_FOUND", f"Local file not found: {source}")
        path = path.resolve()
        if not path.is_file():
            raise SonicError("NOT_FOUND", f"Not a file: {source}")
        st = path.stat()
        if st.st_size > settings.max_download_mb * 1024 * 1024:
            raise SonicError(
                "TOO_LARGE",
                f"File is {st.st_size} bytes; max is {settings.max_download_mb} MB.",
            )
        asset_id = _hash_id("file", str(path), str(st.st_mtime_ns), str(st.st_size), str(max_seconds))
        adir = _asset_dir(settings, asset_id)
        index = adir / _ASSET_INDEX
        if index.exists():
            return VideoAsset.model_validate_json(index.read_text(encoding="utf-8"))
        local = adir / f"source{path.suffix.lower() or '.mp4'}"
        _copy_or_link(path, local)
        source_type = "file"
        original = str(path)

    which_ffmpeg()
    probe = ffprobe(local)
    meta = _parse_probe(probe)
    duration = meta["duration_sec"]
    if duration <= 0:
        raise SonicError("PROBE_FAILED", "Could not read video duration (not a valid media file?).")

    proxy_seconds = min(settings.proxy_max_seconds, max_seconds, int(duration) + 1)
    long_edge = max(int(meta["width"]), int(meta["height"]))
    # A clip that is already near 360p costs more to re-encode than later steps save.
    reuse_source = 0 < long_edge <= 720 and duration <= proxy_seconds + 0.5
    proxy_file = adir / "proxy.mp4"
    audio_file = adir / "audio.wav"
    frames_dir = adir / "frames"
    has_audio = bool(meta["has_audio"])
    audio_limit = min(max_seconds, int(duration) + 1)
    stats: dict[str, Any] | None = None
    frames: list[Path] = []
    scene_cuts: list[float] | None = None

    def _extract_audio() -> dict[str, Any]:
        extract_audio_wav(local, audio_file, max_seconds=audio_limit)
        return probe_audio(audio_file)

    def _frames_from(src: Path) -> tuple[list[Path], list[float]]:
        return extract_scene_keyframes(src, frames_dir, max_frames=settings.max_keyframes)

    with ThreadPoolExecutor(max_workers=2) as pool:
        audio_fut = pool.submit(_extract_audio) if has_audio else None
        if reuse_source:
            proxy_path: Path = local
            frame_fut = pool.submit(_frames_from, local)
        else:
            try:
                pool.submit(make_proxy, local, proxy_file, max_seconds=proxy_seconds, height=360).result()
                proxy_path = proxy_file
            except SonicError as exc:
                degraded.append(f"proxy:{exc.code}")
                proxy_path = local
            frame_fut = pool.submit(_frames_from, proxy_path if proxy_path.exists() else local)
        if audio_fut is not None:
            try:
                stats = audio_fut.result()
            except SonicError as exc:
                degraded.append(f"audio:{exc.code}")
                has_audio = False
        try:
            frames, scene_cuts = frame_fut.result()
        except SonicError as exc:
            degraded.append(f"keyframes:{exc.code}")
            frames, scene_cuts = [], None

    if not has_audio:
        audio_file_out = None
    elif not audio_file.exists():
        has_audio = False
        audio_file_out = None
    else:
        audio_file_out = audio_file
    if not frames and not scene_cuts:
        # The keyframe pass failed outright. Leave cuts unset so analyze can retry.
        scene_cuts = None

    silence_ratio = None if not stats else stats.get("silence_ratio")

    probe_path = adir / "probe.json"
    probe_path.write_text(json.dumps(probe, indent=2)[:200_000], encoding="utf-8")

    asset = VideoAsset(
        asset_id=asset_id,
        source_type=source_type,  # type: ignore[arg-type]
        local_path=str(local),
        duration_sec=round(float(duration), 3),
        width=int(meta["width"]),
        height=int(meta["height"]),
        fps=float(meta["fps"]),
        aspect=str(meta["aspect"]),
        has_audio=bool(has_audio),
        probe_json={"format": (probe.get("format") or {}), "n_streams": len(probe.get("streams") or [])},
        original_source=original,
        audio_path=str(audio_file_out) if audio_file_out else None,
        keyframe_paths=[str(p) for p in frames],
        proxy_path=str(proxy_path) if Path(proxy_path).exists() else None,
        silence_ratio=silence_ratio,
        scene_cuts=scene_cuts,
        audio_stats=dump_audio_stats(stats) if stats else {},
        degraded=degraded,
    )
    save_asset(settings, asset)
    return asset
