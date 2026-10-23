from sonicmatch.hosted.timeline import build_timeline, section_count


def test_three_minute_clip_splits_into_several_music_sections():
    assert 5 <= section_count(180) <= 10
    profile = {
        "duration_sec": 180,
        "analyzer": "local",
        "overall_mood": ["warm", "calm"],
        "scenes": [
            {"start": 0, "end": 40, "energy": 0.3, "description": "opening", "tags": ["speech"]},
            {"start": 40, "end": 100, "energy": 0.8, "description": "scene 2", "tags": ["peak"]},
            {"start": 100, "end": 180, "energy": 0.4, "description": "closing", "tags": []},
        ],
        "energy_curve": [{"t": i * 10, "energy": 0.3 + (i % 3) * 0.2} for i in range(18)],
    }
    tracks = [
        {"reason": "fits the open", "track": {"id": "a", "title": "Latte", "license": "CC0-1.0", "artist": "A"}},
        {"reason": "fits the peak", "track": {"id": "b", "title": "Pulse", "license": "CC-BY-4.0", "artist": "B"}},
    ]
    timeline = build_timeline(profile, tracks, asset_id="abc123", duration_sec=180)
    assert timeline["frame_source"].startswith("ffmpeg")
    assert timeline["frames"]
    assert 5 <= len(timeline["sections"]) <= 10
    first = timeline["sections"][0]
    assert first["label"].startswith("0:00")
    assert first["bgm"]["title"] == "Latte"
    assert first["bgm"]["preview"] is False
    assert first["sfx"]
    assert first["sfx"][0]["reference_only"] is True
    assert timeline["sections"][-1]["name"] == "Closing"
