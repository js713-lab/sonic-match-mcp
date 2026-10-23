"""Turn a Sonicmatch profile into timed music sections.

Frame rows come from the scene cuts and energy curve this repo already
computes with ffmpeg. They are not a caption of every picture frame.
"""

from __future__ import annotations

from typing import Any


def clock(seconds: float) -> str:
    total = max(0, int(round(float(seconds))))
    return f"{total // 60}:{total % 60:02d}"


def section_count(duration: float) -> int:
    """A short clip stays one part. Around three minutes, aim for 5–10 parts."""
    duration = float(duration or 0)
    if duration < 25:
        return 1
    if duration < 90:
        return max(2, min(4, round(duration / 20)))
    return max(5, min(10, round(duration / 22)))


def _energy_at(curve: list[dict[str, Any]], t: float, fallback: float) -> float:
    if not curve:
        return fallback
    best = curve[0]
    for point in curve:
        if abs(float(point.get("t") or 0) - t) < abs(float(best.get("t") or 0) - t):
            best = point
    try:
        return float(best.get("energy") if best.get("energy") is not None else fallback)
    except (TypeError, ValueError):
        return fallback


def _bounds(duration: float, scenes: list[dict[str, Any]]) -> list[float]:
    count = section_count(duration)
    raw = [duration * i / count for i in range(count + 1)]
    cuts = []
    for scene in scenes:
        try:
            cuts.append(float(scene.get("start") or 0))
            cuts.append(float(scene.get("end") or 0))
        except (TypeError, ValueError):
            continue
    snapped = [0.0]
    for edge in raw[1:-1]:
        near = [cut for cut in cuts if abs(cut - edge) <= max(2.5, duration * 0.04)]
        choice = min(near, key=lambda cut: abs(cut - edge)) if near else edge
        if choice - snapped[-1] < 8 and count > 1:
            choice = edge
        snapped.append(round(choice, 2))
    snapped.append(round(duration, 2))
    # Keep the timeline in order if a snap jumped backwards.
    ordered = [0.0]
    for edge in snapped[1:]:
        ordered.append(edge if edge > ordered[-1] + 1 else ordered[-1])
    ordered[-1] = round(duration, 2)
    if ordered[-1] <= ordered[-2]:
        return raw
    return ordered


def _sfx(energy: float, tags: list[str], first: bool, last: bool) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if first:
        refs.append({"name": "soft swell", "role": "in", "reference_only": True})
    if "speech" in tags or energy < 0.35:
        refs.append({"name": "room tone", "role": "bed", "reference_only": True})
    elif energy > 0.7:
        refs.append({"name": "whoosh", "role": "transition", "reference_only": True})
    else:
        refs.append({"name": "light foley", "role": "texture", "reference_only": True})
    if last:
        refs.append({"name": "tail out", "role": "out", "reference_only": True})
    return refs[:2]


def _label_for(index: int, count: int, energy: float) -> str:
    if index == 0:
        return "Opening"
    if index == count - 1:
        return "Closing"
    if energy > 0.7:
        return "Peak"
    if energy < 0.35:
        return "Hold"
    return "Section"


def build_timeline(
    profile: dict[str, Any],
    tracks: list[dict[str, Any]],
    *,
    asset_id: str,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    duration = float(duration_sec or profile.get("duration_sec") or 0)
    if duration <= 0:
        duration = 1.0
    scenes = [scene for scene in (profile.get("scenes") or []) if isinstance(scene, dict)]
    curve = [point for point in (profile.get("energy_curve") or []) if isinstance(point, dict)]
    edges = _bounds(duration, scenes)
    moods = [str(item) for item in (profile.get("overall_mood") or [])]
    sections: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    for scene in scenes:
        frames.append(
            {
                "t": scene.get("start"),
                "end": scene.get("end"),
                "energy": scene.get("energy"),
                "description": scene.get("description") or "",
                "tags": scene.get("tags") or [],
                "source": "scene-cut",
            }
        )
    if not frames:
        for point in curve[:24]:
            frames.append(
                {
                    "t": point.get("t"),
                    "energy": point.get("energy"),
                    "description": "energy sample",
                    "source": "audio-energy",
                }
            )
    usable = [track for track in tracks if isinstance(track, dict) and (track.get("title") or track.get("track"))]
    flat_tracks: list[dict[str, Any]] = []
    for item in usable:
        track = item.get("track") if isinstance(item.get("track"), dict) else item
        flat_tracks.append({"item": item, "track": track})

    count = len(edges) - 1
    for index in range(count):
        start, end = edges[index], edges[index + 1]
        if end <= start:
            continue
        mid = (start + end) / 2
        scene_energy = None
        tags: list[str] = []
        for scene in scenes:
            try:
                if float(scene.get("start") or 0) <= mid <= float(scene.get("end") or 0):
                    scene_energy = float(scene.get("energy") or 0)
                    tags = [str(tag) for tag in (scene.get("tags") or [])]
                    break
            except (TypeError, ValueError):
                continue
        energy = scene_energy if scene_energy is not None else _energy_at(curve, mid, 0.5)
        picked = flat_tracks[index % len(flat_tracks)] if flat_tracks else None
        alt = flat_tracks[(index + 1) % len(flat_tracks)] if len(flat_tracks) > 1 else None
        if alt and picked and alt["track"].get("id") == picked["track"].get("id"):
            alt = None
        sections.append(
            {
                "index": index,
                "start": round(start, 2),
                "end": round(end, 2),
                "label": f"{clock(start)}–{clock(end)}",
                "name": _label_for(index, count, energy),
                "energy": round(energy, 3),
                "mood": moods[:2],
                "bgm": _public_pick(picked),
                "alt": _public_pick(alt),
                "sfx": _sfx(energy, tags, index == 0, index == count - 1),
            }
        )
    return {
        "ok": True,
        "asset_id": asset_id,
        "duration_sec": round(duration, 2),
        "duration_label": clock(duration),
        "analyzer": profile.get("analyzer") or "local",
        "frame_source": "ffmpeg scene cuts and audio energy from sonicmatch",
        "frames": frames,
        "sections": sections,
        "mood": moods,
    }


def _public_pick(picked: dict[str, Any] | None) -> dict[str, Any] | None:
    if not picked:
        return None
    track = picked["track"]
    item = picked["item"]
    return {
        "id": track.get("id"),
        "title": track.get("title"),
        "artist": track.get("artist"),
        "license": track.get("license"),
        "bpm": track.get("bpm"),
        "reason": item.get("reason") or "",
        "attribution_text": track.get("attribution_text") or "",
        "preview": _has_preview(track),
    }


def _has_preview(track: dict[str, Any]) -> bool:
    for key in ("preview_url", "download_url"):
        url = str(track.get(key) or "")
        if url.startswith("https://"):
            return True
    return False
