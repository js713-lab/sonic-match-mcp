"""ffmpeg mixer: hook trim, loop, ducking under speech, mix spec JSON."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from sonicmatch.config import Settings, load_settings
from sonicmatch.errors import SonicError
from sonicmatch.ffmpeg_util import quote_ffmpeg_path, run, synthesize_bed, which_ffmpeg
from sonicmatch.ingest import load_asset
from sonicmatch.models import MixResult, Recommendation, Track, VideoSonicProfile
from sonicmatch.music.rank import hook_slice
from sonicmatch.ssrf import parse_source_url


_AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".opus"}


def _track_audio(
    track: Track,
    dest: Path,
    duration: float,
    settings: Settings,
) -> tuple[Path, list[str]]:
    notes: list[str] = []
    url = track.download_url or track.preview_url
    if url and not url.startswith(("http://", "https://")):
        local = Path(url).expanduser()
        if local.is_file() and (
            local.suffix.lower() in _AUDIO_SUFFIXES or local.stat().st_size > 64
        ):
            notes.append(f"using local audio from {track.source}: {local}")
            return local, notes
    if url and url.startswith(("http://", "https://")):
        try:
            parse_source_url(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "sonicmatch-mcp/0.1"})
                resp.raise_for_status()
                dest.write_bytes(resp.content)
            notes.append(f"downloaded track audio from {track.source}")
            return dest, notes
        except Exception as exc:
            notes.append(f"track download failed ({type(exc).__name__}); synthesizing demo bed")
    else:
        notes.append(
            "seed catalog has no remote audio; synthesizing a license-free demo bed "
            "(replace with a real CC file for production mixes)"
        )
    bpm = track.bpm or 110
    synthesize_bed(dest, duration_sec=max(duration, 12.0), bpm=bpm, energy=track.energy)
    return dest, notes


def _db_to_volume(db: float) -> float:
    return round(10 ** (db / 20.0), 4)


def preview_mix(
    asset_id: str,
    track: Track,
    *,
    profile: VideoSonicProfile | None = None,
    ducking: bool = True,
    bgm_db: float = -18,
    voice_db: float = -16,
    suggested_in_out: tuple[float, float] | None = None,
    settings: Settings | None = None,
) -> MixResult:
    """
    Build a low-res mixed preview + the ffmpeg recipe an editor can re-apply.

    Ducking uses sidechaincompress when the video has an audio track and ducking=True.
    """
    settings = settings or load_settings()
    which_ffmpeg()
    asset = load_asset(asset_id, settings)
    video = asset.local_path
    if asset.proxy_path and Path(asset.proxy_path).exists() and asset.has_audio:
        # Prefer the proxy only when it still carries audio; otherwise mix the original.
        video = asset.proxy_path
    if not video or not Path(video).exists():
        raise SonicError("ASSET_NOT_FOUND", "Asset has no local video to mix.")
    video_has_audio = bool(asset.has_audio)

    duration = float(asset.duration_sec)
    in_out = suggested_in_out
    if not in_out and profile:
        in_out = hook_slice(track, duration, profile.energy_mean)
    if not in_out:
        in_out = (0.0, min(track.duration_sec or 15.0, max(12.0, duration)))
    start, end = in_out
    has_remote = bool(
        (track.download_url or track.preview_url or "").startswith(("http://", "https://"))
    )
    if not has_remote:
        # Synthesized demo beds have no chorus; use the start of the bed.
        start, end = 0.0, min(max(12.0, duration), track.duration_sec or max(12.0, duration))
    slice_len = max(0.5, end - start)

    mix_id = hashlib.sha256(
        f"{asset_id}:{track.id}:{ducking}:{bgm_db}:{voice_db}:{start}:{end}".encode()
    ).hexdigest()[:12]
    out_dir = settings.cache_dir / "mix" / mix_id
    out_dir.mkdir(parents=True, exist_ok=True)
    bed = out_dir / "bed.wav"
    bed_needed = max(duration, slice_len, end - start) + 1.0
    if has_remote:
        bed_needed = max(bed_needed, end + 1.0)
    bgm_path, notes = _track_audio(track, bed, bed_needed, settings)

    speech = bool(profile and profile.speech_coverage > 0.25)
    use_duck = bool(ducking and video_has_audio and speech)
    if ducking and not video_has_audio:
        notes.append("ducking skipped: video has no audio track")
    elif ducking and not speech:
        notes.append("ducking skipped: speech_coverage is low")
        use_duck = False

    bg_vol = _db_to_volume(bgm_db)
    voice_vol = _db_to_volume(voice_db)

    # Build BGM that matches video length: trim hook then loop/crossfade.
    looped = out_dir / "bgm_loop.wav"
    # aloop then atrim to exact video duration.
    if slice_len + 0.05 >= duration:
        bgm_filter = (
            f"[1:a]atrim=start={start:.3f}:duration={duration:.3f},"
            f"asetpts=PTS-STARTPTS,volume={bg_vol}[bg]"
        )
    else:
        loop_samples = max(1024, int(slice_len * 48000))
        bgm_filter = (
            f"[1:a]atrim=start={start:.3f}:duration={slice_len:.3f},asetpts=PTS-STARTPTS,"
            f"aloop=loop=-1:size={loop_samples},atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,"
            f"volume={bg_vol}[bg]"
        )

    audio_out = out_dir / "preview.wav"
    video_out = out_dir / "preview.mp4"

    def _filters(duck: bool) -> tuple[str, str]:
        if duck:
            return (
                f"{bgm_filter};"
                f"[0:a]volume={voice_vol}[voice];"
                f"[bg][voice]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=250:makeup=2[ducked];"
                f"[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[aout]",
                "sidechain ducking under speech (ffmpeg sidechaincompress)",
            )
        if video_has_audio:
            return (
                f"{bgm_filter};"
                f"[0:a]volume={voice_vol}[voice];"
                f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[aout]",
                "simple mix, no ducking",
            )
        return (
            f"{bgm_filter};[bg]alimiter=limit=0.95[aout]",
            "BGM only (source had no audio)",
        )

    filter_complex, duck_note = _filters(use_duck)
    notes.append(duck_note)

    def _mix_cmd(fc: str) -> list[str]:
        return [
            which_ffmpeg(),
            "-y",
            "-i",
            video,
            "-i",
            str(bgm_path),
            "-filter_complex",
            fc,
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(video_out),
        ]

    cmd = _mix_cmd(filter_complex)
    try:
        run(cmd, timeout=180)
    except SonicError:
        if use_duck:
            notes.append("sidechaincompress unavailable; fell back to a simple mix")
            use_duck = False
            filter_complex, duck_note = _filters(False)
            notes.append(duck_note)
            cmd = _mix_cmd(filter_complex)
            run(cmd, timeout=180)
        else:
            raise

    # Audio-only preview (wav is always available; try mp3 if lame is present).
    mp3_out = out_dir / "preview.mp3"
    audio_cmd = [
        which_ffmpeg(),
        "-y",
        "-i",
        str(video_out),
        "-vn",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "4",
        str(mp3_out),
    ]
    try:
        run(audio_cmd, timeout=60)
        audio_out = mp3_out
    except SonicError:
        run(
            [
                which_ffmpeg(),
                "-y",
                "-i",
                str(video_out),
                "-vn",
                "-c:a",
                "pcm_s16le",
                str(audio_out),
            ],
            timeout=60,
        )
        notes.append("libmp3lame not available; preview audio is WAV")

    pretty = " ".join(quote_ffmpeg_path(c) if ("/" in c or "\\" in c) else c for c in cmd)
    mix_spec = {
        "asset_id": asset_id,
        "track_id": track.id,
        "video": video,
        "bgm": str(bgm_path),
        "bgm_in": start,
        "bgm_out": end,
        "video_duration": duration,
        "ducking": use_duck,
        "bgm_db": bgm_db,
        "voice_db": voice_db,
        "loop": True,
        "license": track.license,
        "attribution_required": track.attribution_required,
        "attribution_text": track.attribution_text,
        "filter_complex": filter_complex,
        "warning": (
            "This is NOT an Instagram/TikTok official music sticker. "
            "Keep the track license and attribution with the export."
        ),
    }
    if track.attribution_required:
        notes.append(f"attribution: {track.attribution_text}")
    notes.append(
        "Do not claim this track is cleared for Instagram's official sticker catalog."
    )

    # Keep looped path referenced so editors can inspect; file may not exist independently.
    _ = looped
    return MixResult(
        preview_audio_path=str(audio_out),
        preview_video_path=str(video_out),
        ffmpeg_command=pretty,
        mix_spec=mix_spec,
        notes=notes,
    )


def recommendation_mix_args(rec: Recommendation) -> dict:
    return {
        "track_id": rec.track.id,
        "suggested_in_out": rec.suggested_in_out,
        "ducking": rec.ducking == "recommended",
    }


def export_mix_spec(
    asset_id: str,
    track: Track,
    *,
    profile: VideoSonicProfile | None = None,
    ducking: bool = True,
    bgm_db: float = -18,
    voice_db: float = -16,
    render: bool = False,
    settings: Settings | None = None,
) -> MixResult:
    """Editor-shaped mix spec (ffmpeg + attribution + hook) without requiring a render.

    Set render=True to also write preview files via preview_mix.
    """
    if render:
        return preview_mix(
            asset_id,
            track,
            profile=profile,
            ducking=ducking,
            bgm_db=bgm_db,
            voice_db=voice_db,
            settings=settings,
        )
    settings = settings or load_settings()
    asset = load_asset(asset_id, settings)
    duration = float(asset.duration_sec)
    in_out = hook_slice(track, duration, profile.energy_mean if profile else 0.55)
    start, end = in_out
    speech = bool(profile and profile.speech_coverage > 0.25)
    use_duck = bool(ducking and asset.has_audio and speech)
    bg_vol = _db_to_volume(bgm_db)
    voice_vol = _db_to_volume(voice_db)
    slice_len = max(0.5, end - start)
    video = asset.local_path
    bgm = track.download_url or track.preview_url or "<bgm.wav>"
    if slice_len + 0.05 >= duration:
        fc = (
            f"[1:a]atrim=start={start:.3f}:duration={duration:.3f},"
            f"asetpts=PTS-STARTPTS,volume={bg_vol}[bg]"
        )
    else:
        loop_samples = max(1024, int(slice_len * 48000))
        fc = (
            f"[1:a]atrim=start={start:.3f}:duration={slice_len:.3f},asetpts=PTS-STARTPTS,"
            f"aloop=loop=-1:size={loop_samples},atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,"
            f"volume={bg_vol}[bg]"
        )
    if use_duck:
        fc += (
            f";[0:a]volume={voice_vol}[voice];"
            "[bg][voice]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=250:makeup=2[ducked];"
            "[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[aout]"
        )
    elif asset.has_audio:
        fc += (
            f";[0:a]volume={voice_vol}[voice];"
            "[voice][bg]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[aout]"
        )
    else:
        fc += ";[bg]alimiter=limit=0.95[aout]"
    cmd = (
        f"ffmpeg -y -i {quote_ffmpeg_path(video)} -i {quote_ffmpeg_path(str(bgm))} "
        f"-filter_complex {quote_ffmpeg_path(fc)} -map 0:v:0 -map [aout] "
        f"-t {duration:.3f} -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest out.mp4"
    )
    notes = [
        "Spec only — files were not rendered. Call preview_mix or export_mix_spec(render=true).",
        f"license {track.license}",
        "Do not claim this track is cleared for Instagram's official sticker catalog.",
    ]
    if track.attribution_required:
        notes.append(f"attribution: {track.attribution_text}")
    spec = {
        "asset_id": asset_id,
        "track_id": track.id,
        "video": video,
        "bgm": bgm,
        "bgm_in": start,
        "bgm_out": end,
        "video_duration": duration,
        "ducking": use_duck,
        "bgm_db": bgm_db,
        "voice_db": voice_db,
        "loop": True,
        "license": track.license,
        "attribution_required": track.attribution_required,
        "attribution_text": track.attribution_text,
        "filter_complex": fc,
        "rendered": False,
        "warning": (
            "This is NOT an Instagram/TikTok official music sticker. "
            "Keep the track license and attribution with the export."
        ),
    }
    return MixResult(
        preview_audio_path=None,
        preview_video_path=None,
        ffmpeg_command=cmd,
        mix_spec=spec,
        notes=notes,
    )
