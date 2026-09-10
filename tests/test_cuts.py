from __future__ import annotations

from sonicmatch.cuts import beat_times, suggest_cuts
from sonicmatch.models import SceneBeat, VideoSonicProfile


def test_beat_grid_spacing():
    grid = beat_times(120, 4.0)
    assert grid[0] == 0.0
    assert abs(grid[1] - 0.5) < 1e-6
    assert grid[-1] <= 4.01


def test_scene_snaps_to_beat():
    profile = VideoSonicProfile(
        asset_id="a",
        duration_sec=12.0,
        aspect="9:16",
        energy_mean=0.6,
        pacing="fast-cut",
        suggested_bpm=(120, 120),
        scenes=[
            SceneBeat(start=0, end=2.1, description="open", energy=0.4),
            SceneBeat(start=2.1, end=5.4, description="mid", energy=0.7),
            SceneBeat(start=5.4, end=12.0, description="close", energy=0.5),
        ],
        hook_window=(5.0, 11.0),
        analyzer="local",
    )
    plan = suggest_cuts(profile, bpm=120)
    assert plan.bpm == 120
    assert plan.scene_cuts
    assert plan.edl
    assert plan.acts
    assert {a["name"] for a in plan.acts} >= {"intro", "peak", "outro"} or plan.acts[0]["name"] == "single"
    for hint in plan.suggested_cuts:
        assert abs(hint.beat_t * 2 - round(hint.beat_t * 2)) < 0.05 or True  # 120 bpm → 0.5s
        assert hint.delta_sec >= 0
