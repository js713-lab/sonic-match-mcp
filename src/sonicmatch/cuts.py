"""Beat-grid vs scene-cut suggestions (EDL-ish). Instagram-like matching is energy + hook."""

from __future__ import annotations

from sonicmatch.models import CutHint, CutPlan, VideoSonicProfile


def beat_times(bpm: float, duration: float) -> list[float]:
    if bpm <= 0 or duration <= 0:
        return [0.0]
    step = 60.0 / float(bpm)
    t = 0.0
    out: list[float] = []
    while t <= duration + 1e-6:
        out.append(round(t, 4))
        t += step
        if len(out) > 4000:
            break
    return out


def _nearest(t: float, grid: list[float]) -> tuple[float, float]:
    if not grid:
        return t, 0.0
    best = min(grid, key=lambda g: abs(g - t))
    return best, abs(best - t)


def _acts(profile: VideoSonicProfile) -> list[dict]:
    duration = profile.duration_sec
    if duration <= 20:
        return [
            {
                "name": "single",
                "t": [0.0, round(duration, 2)],
                "energy": profile.energy_mean,
                "hint": "one bed, 12–20s hook",
            }
        ]
    hook = profile.hook_window
    intro_end = min(duration * 0.25, max(3.0, hook[0] if hook[0] > 1 else duration * 0.2))
    outro_start = max(intro_end + 2, duration * 0.75)
    if hook[0] >= intro_end:
        peak = [round(hook[0], 2), round(min(hook[1], outro_start), 2)]
    else:
        peak = [round(intro_end, 2), round(outro_start, 2)]
    return [
        {
            "name": "intro",
            "t": [0.0, round(intro_end, 2)],
            "energy": round(max(0.05, profile.energy_mean - 0.15), 2),
            "hint": "calmer bed / fade in",
        },
        {
            "name": "peak",
            "t": peak,
            "energy": round(min(1.0, profile.energy_mean + 0.15), 2),
            "hint": "hook / chorus-like slice",
        },
        {
            "name": "outro",
            "t": [round(outro_start, 2), round(duration, 2)],
            "energy": round(max(0.05, profile.energy_mean - 0.1), 2),
            "hint": "resolve / lower energy",
        },
    ]


def suggest_cuts(profile: VideoSonicProfile, bpm: float | None = None) -> CutPlan:
    """Snap scene boundaries onto a beat grid derived from suggested_bpm or a track BPM."""
    if bpm is None:
        bpm = (profile.suggested_bpm[0] + profile.suggested_bpm[1]) / 2.0
    bpm = max(40.0, min(float(bpm), 220.0))
    duration = max(0.1, profile.duration_sec)
    grid = beat_times(bpm, duration)
    scene_cuts = sorted(
        {
            round(s.start, 3)
            for s in profile.scenes
            if 0.12 < s.start < duration - 0.12
        }
    )
    bar_len = 4 * 60.0 / bpm
    hints: list[CutHint] = []
    for t in scene_cuts:
        snapped, delta = _nearest(t, grid)
        bar = int(snapped / bar_len) + 1 if bar_len else 1
        hints.append(
            CutHint(
                scene_t=t,
                beat_t=round(snapped, 3),
                delta_sec=round(delta, 3),
                bar=bar,
                kind="scene-to-beat",
            )
        )
    bounds = [0.0] + [h.beat_t for h in hints] + [round(duration, 3)]
    # unique increasing
    clean: list[float] = []
    for b in bounds:
        if not clean or b - clean[-1] >= 0.25:
            clean.append(b)
    if clean[-1] < duration - 0.05:
        clean.append(round(duration, 3))
    edl = []
    for i, (a, b) in enumerate(zip(clean, clean[1:])):
        desc = "opening" if i == 0 else ("closing" if b >= duration - 0.05 else f"beat {i}")
        if i < len(profile.scenes):
            desc = profile.scenes[i].description or desc
        edl.append(
            {
                "index": i + 1,
                "start": round(a, 3),
                "end": round(b, 3),
                "duration": round(b - a, 3),
                "label": desc,
            }
        )
    notes = [
        f"BPM {bpm:.1f} → {60.0 / bpm:.3f}s per beat.",
        "Snap cuts to the nearest beat so BGM hits feel Instagram-like.",
        "This is NOT a Meta trending-audio graph — just energy + hook + cut density.",
    ]
    if not scene_cuts:
        notes.append("No scene cuts detected; EDL is a single span. Re-analyze with Gemini for better scenes.")
    return CutPlan(
        asset_id=profile.asset_id,
        bpm=round(bpm, 2),
        beat_grid=grid[:800],
        scene_cuts=scene_cuts,
        suggested_cuts=hints,
        acts=_acts(profile),
        edl=edl,
        notes=notes,
    )
