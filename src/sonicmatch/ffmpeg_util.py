"""ffmpeg / ffprobe helpers. Never pass untrusted strings as filter args unsanitized."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from sonicmatch.errors import SonicError


def which_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise SonicError(
            "FFMPEG_MISSING",
            "ffmpeg is not on PATH. Install ffmpeg to ingest and mix video.",
        )
    return path


def which_ffprobe() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise SonicError(
            "FFPROBE_MISSING",
            "ffprobe is not on PATH. Install ffmpeg (includes ffprobe).",
        )
    return path


def run(
    args: Sequence[str],
    *,
    timeout: int = 120,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SonicError("BINARY_MISSING", f"Required binary not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SonicError("TIMEOUT", f"Command timed out: {args[0]}") from exc
    if check and proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = err[-8:] if err else ["unknown error"]
        raise SonicError(
            "FFMPEG_FAILED",
            f"{args[0]} failed (exit {proc.returncode}): " + " | ".join(tail),
        )
    return proc


def ffprobe(path: str | Path) -> dict[str, Any]:
    cmd = [
        which_ffprobe(),
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = run(cmd, timeout=60)
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SonicError("PROBE_FAILED", "ffprobe returned invalid JSON.") from exc


def aspect_label(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "unknown"
    ratio = width / height
    if abs(ratio - 9 / 16) < 0.08:
        return "9:16"
    if abs(ratio - 16 / 9) < 0.08:
        return "16:9"
    if abs(ratio - 1.0) < 0.08:
        return "1:1"
    if abs(ratio - 4 / 5) < 0.08:
        return "4:5"
    return f"{width}:{height}"


def extract_audio_wav(src: str | Path, dest: str | Path, max_seconds: int | None = None) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [which_ffmpeg(), "-y", "-i", str(src)]
    if max_seconds:
        cmd += ["-t", str(int(max_seconds))]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)]
    run(cmd, timeout=180)


def make_proxy(
    src: str | Path,
    dest: str | Path,
    *,
    max_seconds: int = 90,
    height: int = 360,
) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale=-2:{int(height)}"
    cmd = [
        which_ffmpeg(),
        "-y",
        "-i",
        str(src),
        "-t",
        str(int(max_seconds)),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ac",
        "1",
        "-b:a",
        "64k",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        str(dest),
    ]
    try:
        run(cmd, timeout=180)
    except SonicError:
        # Source may have no audio — retry video-only.
        cmd = [
            which_ffmpeg(),
            "-y",
            "-i",
            str(src),
            "-t",
            str(int(max_seconds)),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            str(dest),
        ]
        run(cmd, timeout=180)


def extract_scene_keyframes(
    src: str | Path,
    dest_dir: str | Path,
    *,
    max_frames: int = 12,
    threshold: float = 0.32,
) -> list[Path]:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    pattern = dest / "kf_%03d.jpg"
    cmd = [
        which_ffmpeg(),
        "-y",
        "-i",
        str(src),
        "-vf",
        f"select='gt(scene,{threshold})',scale=480:-2",
        "-vsync",
        "vfr",
        "-q:v",
        "5",
        str(pattern),
    ]
    run(cmd, timeout=180, check=False)
    frames = sorted(dest.glob("kf_*.jpg"))
    if len(frames) >= 3:
        return frames[:max_frames]
    # Uniform fallback so we always have pictures for local/VLM analysis.
    for old in frames:
        old.unlink(missing_ok=True)
    cmd = [
        which_ffmpeg(),
        "-y",
        "-i",
        str(src),
        "-vf",
        f"fps=1/{max(1, 8 // max(1, max_frames))},scale=480:-2",
        "-frames:v",
        str(max_frames),
        "-q:v",
        "5",
        str(pattern),
    ]
    run(cmd, timeout=180, check=False)
    frames = sorted(dest.glob("kf_*.jpg"))
    if not frames:
        # Last resort: first frame only.
        first = dest / "kf_001.jpg"
        run(
            [
                which_ffmpeg(),
                "-y",
                "-i",
                str(src),
                "-frames:v",
                "1",
                "-q:v",
                "5",
                str(first),
            ],
            timeout=60,
            check=False,
        )
        frames = sorted(dest.glob("kf_*.jpg"))
    return frames[:max_frames]


def scene_cut_times(src: str | Path, threshold: float = 0.32, max_seconds: int = 90) -> list[float]:
    """Parse ffmpeg showinfo timestamps for scene-change frames."""
    cmd = [
        which_ffmpeg(),
        "-t",
        str(int(max_seconds)),
        "-i",
        str(src),
        "-vf",
        f"select='gt(scene,{threshold})',showinfo",
        "-f",
        "null",
        "-",
    ]
    proc = run(cmd, timeout=60, check=False)
    times: list[float] = []
    blob = (proc.stderr or "") + (proc.stdout or "")
    for line in blob.splitlines():
        if "pts_time:" not in line:
            continue
        try:
            part = line.split("pts_time:", 1)[1].split()[0]
            times.append(float(part))
        except (IndexError, ValueError):
            continue
    return times


def synthesize_bed(
    dest: str | Path,
    *,
    duration_sec: float,
    bpm: int = 110,
    energy: float = 0.5,
) -> Path:
    """Generate a license-free demo bed (sine + tremolo) when a track has no audio file."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    duration_sec = max(1.0, float(duration_sec))
    freq = 196 + int(energy * 160)
    trem = max(0.5, min(4.0, bpm / 60.0))
    volume = 0.15 + 0.25 * energy
    dest = dest.with_suffix(".wav") if dest.suffix.lower() == ".mp3" else dest
    cmd = [
        which_ffmpeg(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={freq}:sample_rate=44100:duration={duration_sec:.3f},"
        f"tremolo=f={trem:.3f}:d=0.55,volume={volume:.3f}",
        "-c:a",
        "pcm_s16le",
        str(dest),
    ]
    run(cmd, timeout=60)
    return dest


def quote_ffmpeg_path(path: str) -> str:
    return "'" + path.replace("'", "'\\''") + "'"
