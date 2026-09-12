from __future__ import annotations

from pathlib import Path

import pytest

from sonicmatch.errors import SonicError
from sonicmatch.ingest import ingest_video, load_asset, sanitize_asset_id
from sonicmatch.ssrf import parse_source_url
from tests.conftest import make_color_mp4


def test_ingest_generated_2s_mp4(color_mp4: Path, settings):
    asset = ingest_video(str(color_mp4), max_seconds=10, settings=settings)
    assert asset.duration_sec == pytest.approx(2.0, abs=0.3)
    assert asset.width == 320
    assert asset.height == 240
    assert asset.has_audio is True
    assert asset.source_type == "file"
    assert Path(asset.local_path).exists()
    assert asset.audio_path and Path(asset.audio_path).exists()
    # Re-ingest is a cache hit with the same id.
    again = ingest_video(str(color_mp4), max_seconds=10, settings=settings)
    assert again.asset_id == asset.asset_id


def test_ingest_missing_file(settings):
    with pytest.raises(SonicError) as exc:
        ingest_video("/tmp/definitely-not-a-real-clip-xyz.mp4", settings=settings)
    assert exc.value.code == "NOT_FOUND"


def test_ingest_rejects_loopback_url(settings):
    with pytest.raises(SonicError) as exc:
        ingest_video("https://127.0.0.1:8080/clip.mp4", settings=settings)
    assert exc.value.code == "SSRF_REJECTED"
    with pytest.raises(SonicError):
        parse_source_url("http://127.0.0.1/x.mp4")


def test_asset_id_rejects_path_traversal(settings):
    with pytest.raises(SonicError) as exc:
        sanitize_asset_id("../etc/passwd")
    assert exc.value.code == "ASSET_NOT_FOUND"
    with pytest.raises(SonicError):
        load_asset("../../.env", settings=settings)
    with pytest.raises(SonicError):
        sanitize_asset_id("not-hex")


def test_silent_mp4_has_no_audio(tmp_path: Path, settings, ffmpeg_ok: bool):
    if not ffmpeg_ok:
        pytest.skip("ffmpeg not installed")
    clip = make_color_mp4(tmp_path / "silent.mp4", seconds=2.0, with_audio=False)
    asset = ingest_video(str(clip), settings=settings)
    assert asset.has_audio is False
