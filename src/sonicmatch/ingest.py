"""Ingest local files and public URLs into a cached VideoAsset. Never return bytes."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any
import httpx

from sonicmatch.config import Settings, load_settings
from sonicmatch.errors import SonicError
from sonicmatch.ffmpeg_util import (
    aspect_label,
    extract_audio_wav,
    extract_scene_keyframes,
    ffprobe,
    make_proxy,
    which_ffmpeg,
)
from sonicmatch.models import VideoAsset
from sonicmatch.ssrf import (
    classify_url,
    content_type_looks_like_video,
    parse_source_url,
    resolve_and_check_host,
)

_ASSET_INDEX = "index.json"


def _hash_id(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", errors="replace"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def _asset_dir(settings: Settings, asset_id: str) -> Path:
    d = settings.cache_dir / "assets" / asset_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_asset(settings: Settings, asset: VideoAsset) -> None:
    path = _asset_dir(settings, asset.asset_id) / _ASSET_INDEX
    path.write_text(asset.model_dump_json(indent=2), encoding="utf-8")


def load_asset(asset_id: str, settings: Settings | None = None) -> VideoAsset:
    settings = settings or load_settings()
    path = settings.cache_dir / "assets" / asset_id / _ASSET_INDEX
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
    dest.parent.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(30.0, read=120.0)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        current = url
        for _ in range(5):
            _, host, _ = parse_source_url(current)
            resolve_and_check_host(host)
            resp = client.head(current, headers={"User-Agent": "sonicmatch-mcp/0.1"})
            if resp.status_code in {301, 302, 303, 307, 308}:
                nxt = resp.headers.get("location")
                if not nxt:
                    break
                current = str(httpx.URL(current).join(nxt))
                continue
            break
        parse_source_url(current)
        with client.stream("GET", current, headers={"User-Agent": "sonicmatch-mcp/0.1"}) as resp:
            if resp.status_code >= 400:
                raise SonicError("DOWNLOAD_FAILED", f"HTTP {resp.status_code} fetching video.")
            hops = [current] + [str(u) for u in resp.history]
            for hop in hops:
                if hop.startswith("http"):
                    parse_source_url(hop)
            ct = resp.headers.get("content-type", "")
            cl = resp.headers.get("content-length")
            if cl and int(cl) > max_bytes:
                raise SonicError(
                    "TOO_LARGE",
                    f"Remote file is {int(cl)} bytes; max is {settings.max_download_mb} MB.",
                )
            if not content_type_looks_like_video(ct) and not classify_url(url) == "direct":
                raise SonicError(
                    "NOT_VIDEO",
                    f"Remote content-type {ct!r} does not look like video.",
                )
            written = 0
            with dest.open("wb") as fh:
                for chunk in resp.iter_bytes(1024 * 64):
                    written += len(chunk)
                    if written > max_bytes:
                        fh.close()
                        dest.unlink(missing_ok=True)
                        raise SonicError(
                            "TOO_LARGE",
                            f"Download exceeded {settings.max_download_mb} MB.",
                        )
                    fh.write(chunk)
    return dest


def _yt_dlp_download(url: str, dest_dir: Path, max_seconds: int) -> Path:
    binary = shutil.which("yt-dlp")
    if not binary:
        raise SonicError(
            "YTDLP_MISSING",
            "yt-dlp is not on PATH. Install it to ingest YouTube/TikTok/IG/FB URLs.",
        )
    out_tmpl = str(dest_dir / "source.%(ext)s")
    cmd = [
        binary,
        "--no-playlist",
        "--no-warnings",
        "-f",
        "mp4/bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "-o",
        out_tmpl,
        "--download-sections",
        f"*0-{int(max_seconds)}",
        "--force-keyframes-at-cuts",
        url,
    ]
    # download-sections is best-effort; also pass --max-filesize
    try:
        import subprocess

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SonicError("TIMEOUT", "yt-dlp timed out.") from exc
    if proc.returncode != 0:
        # Retry without download-sections (older yt-dlp).
        cmd = [
            binary,
            "--no-playlist",
            "--no-warnings",
            "-f",
            "mp4/bv*+ba/b",
            "--merge-output-format",
            "mp4",
            "-o",
            out_tmpl,
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
            raise SonicError("DOWNLOAD_FAILED", "yt-dlp failed: " + " | ".join(tail))
    files = list(dest_dir.glob("source.*"))
    files = [f for f in files if f.suffix.lower() not in {".part", ".ytdl", ".json"}]
    if not files:
        raise SonicError("DOWNLOAD_FAILED", "yt-dlp did not produce a file.")
    return files[0]


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
    if max_seconds <= 0:
        max_seconds = 180
    max_seconds = min(int(max_seconds), 600)

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
            downloaded = _yt_dlp_download(source, adir, max_seconds)
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
    proxy_path = adir / "proxy.mp4"
    try:
        make_proxy(local, proxy_path, max_seconds=proxy_seconds, height=360)
    except SonicError as exc:
        degraded.append(f"proxy:{exc.code}")
        proxy_path = Path(str(local))

    audio_path = adir / "audio.wav"
    has_audio = meta["has_audio"]
    if has_audio:
        try:
            extract_audio_wav(local, audio_path, max_seconds=min(max_seconds, int(duration) + 1))
        except SonicError as exc:
            degraded.append(f"audio:{exc.code}")
            has_audio = False
            audio_path = None  # type: ignore[assignment]
    else:
        audio_path = None  # type: ignore[assignment]

    frames_dir = adir / "frames"
    try:
        frames = extract_scene_keyframes(
            proxy_path if proxy_path.exists() else local,
            frames_dir,
            max_frames=settings.max_keyframes,
        )
    except SonicError as exc:
        degraded.append(f"keyframes:{exc.code}")
        frames = []

    # Silence ratio from wav if present.
    silence_ratio = None
    if audio_path and Path(audio_path).exists():
        from sonicmatch.audio import wav_stats

        stats = wav_stats(audio_path)
        silence_ratio = stats.get("silence_ratio")

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
        audio_path=str(audio_path) if audio_path else None,
        keyframe_paths=[str(p) for p in frames],
        proxy_path=str(proxy_path) if Path(proxy_path).exists() else None,
        silence_ratio=silence_ratio,
        degraded=degraded,
    )
    save_asset(settings, asset)
    return asset
