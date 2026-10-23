from __future__ import annotations

from pathlib import Path

import math
import struct
import wave

from sonicmatch.analyze.local import analyze_local
from sonicmatch.audio import wav_stats
from sonicmatch.ingest import ingest_video
from sonicmatch.tools import analyze_video_music, configure
from tests.conftest import make_color_mp4


def test_local_analyze_fills_queries(color_mp4: Path, settings):
    asset = ingest_video(str(color_mp4), settings=settings)
    profile = analyze_local(asset, platform_hint="instagram_reel", extra_notes="cafe latte")
    assert profile.asset_id == asset.asset_id
    assert profile.search_queries
    assert profile.duration_sec > 0
    assert profile.hook_window[1] >= profile.hook_window[0]
    assert profile.analyzer == "local"


def test_trailing_blip_is_not_speech(tmp_path: Path):
    """A few silent samples after a steady tone must not look like speech."""
    path = tmp_path / "tone.wav"
    rate = 16000
    tone = rate * 2
    tail = 300
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for i in range(tone + tail):
            sample = int(9000 * math.sin(2 * math.pi * 440 * i / rate)) if i < tone else 0
            frames += struct.pack("<h", sample)
        wf.writeframes(bytes(frames))
    stats = wav_stats(path)
    assert stats["speech_hint"] < 0.2
    assert stats["energy_var"] < 0.006


def test_analyze_tool_degrades_without_gemini(tmp_path: Path, settings, ffmpeg_ok: bool):
    if not ffmpeg_ok:
        return
    clip = make_color_mp4(tmp_path / "reel.mp4", seconds=2.0, size="360x640")
    configure(settings)
    from sonicmatch.ingest import ingest_video as ing

    asset = ing(str(clip), settings=settings)
    out = analyze_video_music(asset.asset_id, platform_hint="instagram_reel")
    assert out["ok"] is True
    assert out["profile"]["search_queries"]
    assert out["profile"]["analyzer"] in {"local", "hybrid", "gemini"}
