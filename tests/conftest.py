from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sonicmatch.config import Settings
from sonicmatch.tools import configure


def have_ffmpeg() -> bool:
    from shutil import which

    return bool(which("ffmpeg") and which("ffprobe"))


@pytest.fixture(scope="session")
def ffmpeg_ok() -> bool:
    return have_ffmpeg()


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    d = tmp_path / "cache"
    d.mkdir()
    return d


@pytest.fixture
def settings(cache_dir: Path) -> Settings:
    s = Settings(cache_dir=cache_dir)
    s.ensure_dirs()
    configure(s)
    return s


def make_color_mp4(
    path: Path,
    seconds: float = 2.0,
    *,
    color: str = "blue",
    size: str = "320x240",
    with_audio: bool = True,
    rate: int = 25,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s={size}:d={seconds}:r={rate}",
    ]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"]
    else:
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    cmd.append(str(path))
    subprocess.run(cmd, check=True, capture_output=True)
    return path


@pytest.fixture
def color_mp4(tmp_path: Path, ffmpeg_ok: bool) -> Path:
    if not ffmpeg_ok:
        pytest.skip("ffmpeg not installed")
    return make_color_mp4(tmp_path / "clip.mp4", seconds=2.0)
