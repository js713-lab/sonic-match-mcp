"""Heuristic / local-VLM VideoSonic profile. Works with ffmpeg + stdlib only."""

from __future__ import annotations

import wave
from pathlib import Path

from sonicmatch.audio import peak_window, probe_audio
from sonicmatch.ffmpeg_util import scene_cut_times
from sonicmatch.models import EnergyPoint, SceneBeat, VideoAsset, VideoSonicProfile
from sonicmatch.models import PlatformHint


def _platform_from_aspect(aspect: str, hint: PlatformHint | str) -> PlatformHint:
    if hint and hint != "generic":
        return hint  # type: ignore[return-value]
    if aspect == "9:16":
        return "instagram_reel"
    if aspect == "1:1":
        return "instagram_story"
    if aspect == "16:9":
        return "youtube_long"
    return "generic"


def _pacing_from_cuts(n_cuts: int, duration: float) -> str:
    if duration <= 0:
        return "medium"
    cps = n_cuts / duration
    if cps >= 0.45:
        return "fast-cut"
    if cps <= 0.12:
        return "slow"
    return "medium"


def _bpm_from_pacing(pacing: str, cut_times: list[float], duration: float) -> tuple[int, int]:
    if pacing == "fast-cut":
        return (108, 132)
    if pacing == "slow":
        return (72, 96)
    if duration > 0 and len(cut_times) >= 3:
        # median cut interval → 2 beats per cut as a rough motion BPM
        gaps = [b - a for a, b in zip(cut_times, cut_times[1:]) if b > a]
        if gaps:
            gaps.sort()
            med = gaps[len(gaps) // 2]
            bpm = int(max(70, min(140, (60.0 / med) * 2)))
            return (max(60, bpm - 12), min(160, bpm + 12))
    return (90, 118)


def _content_type(notes: str, duration: float, aspect: str, speech: float) -> str:
    blob = notes.lower()
    mapping = [
        ("product", "product"),
        ("shopee", "product"),
        ("unbox", "product"),
        ("podcast", "podcast_clip"),
        ("talking head", "podcast_clip"),
        ("travel", "travel"),
        ("vlog", "vlog"),
        ("wedding", "event"),
        ("event", "event"),
        ("concert", "event"),
        ("sport", "sports"),
        ("cafe", "lifestyle"),
        ("food", "lifestyle"),
    ]
    for needle, label in mapping:
        if needle in blob:
            return label
    if speech > 0.55 and duration < 90:
        return "podcast_clip"
    if aspect == "9:16" and duration <= 30:
        return "lifestyle"
    return "lifestyle"


def _moods(
    *,
    speech: float,
    energy_mean: float,
    pacing: str,
    content_type: str,
    notes: str,
) -> list[str]:
    moods: list[str] = []
    blob = notes.lower()
    for token in (
        "warm",
        "playful",
        "dark",
        "cinematic",
        "chill",
        "hype",
        "cozy",
        "sad",
        "upbeat",
        "tropical",
        "elegant",
        "lofi",
        "lo-fi",
    ):
        if token in blob and token not in moods:
            moods.append("lo-fi" if token in {"lofi", "lo-fi"} else token)
    if not moods:
        if content_type == "product":
            moods = ["upbeat", "clean"]
        elif content_type == "podcast_clip":
            moods = ["calm", "warm"]
        elif content_type == "event":
            moods = ["upbeat", "celebratory"]
        elif content_type == "travel":
            moods = ["warm", "adventurous"]
        elif energy_mean >= 0.65 or pacing == "fast-cut":
            moods = ["upbeat", "playful"]
        elif energy_mean <= 0.3:
            moods = ["calm", "warm"]
        else:
            moods = ["warm", "playful"]
    if speech > 0.4 and "calm" not in moods:
        moods.append("understated")
    return moods[:4]


def _search_queries(
    moods: list[str],
    content_type: str,
    bpm: tuple[int, int],
    instrumental: bool,
    pacing: str,
    notes: str,
) -> list[str]:
    mood = " ".join(moods[:2])
    inst = "instrumental no vocals" if instrumental else ""
    bpm_s = f"{bpm[0]}-{bpm[1]}bpm"
    q = [
        f"{mood} {content_type} {inst}".strip(),
        f"{mood} {pacing} bed {inst} {bpm_s}".strip(),
        f"{'lo-fi' if 'lo-fi' in moods or 'chill' in moods else 'indie'} {content_type} {inst}".strip(),
    ]
    if notes.strip():
        q.append(notes.strip()[:80] + (" instrumental" if instrumental else ""))
    # unique, non-empty
    seen: set[str] = set()
    out: list[str] = []
    for item in q:
        key = " ".join(item.split()).lower()
        if key and key not in seen:
            seen.add(key)
            out.append(" ".join(item.split()))
    return out[:4]


def _avoid(speech: float, energy_mean: float, content_type: str) -> list[str]:
    avoid = ["lyrics-dense"]
    if speech > 0.25:
        avoid.append("aggressive trap")
        avoid.append("busy EDM drop")
    if energy_mean < 0.4:
        avoid.append("stadium anthem")
    if content_type in {"lifestyle", "travel"}:
        avoid.append("dark cinematic drone")
    if content_type == "podcast_clip":
        avoid.extend(["heavy drums", "vocal chops"])
    return avoid


def _scenes_from_cuts(
    duration: float,
    cuts: list[float],
    curve_lookup,
    speech: float,
) -> list[SceneBeat]:
    bounds = [0.0] + [t for t in cuts if 0.15 < t < duration - 0.15] + [duration]
    # merge tiny slices
    merged: list[tuple[float, float]] = []
    start = bounds[0]
    for t in bounds[1:]:
        if t - start < 1.2 and t != bounds[-1]:
            continue
        merged.append((start, t))
        start = t
    if not merged:
        merged = [(0.0, duration)]
    scenes: list[SceneBeat] = []
    for i, (a, b) in enumerate(merged[:10]):
        e = curve_lookup((a + b) / 2)
        desc = f"scene {i + 1}"
        if i == 0:
            desc = "opening"
        elif b >= duration - 0.3:
            desc = "closing"
        tags = []
        if e > 0.7:
            tags.append("peak")
        if speech > 0.4:
            tags.append("speech")
        scenes.append(
            SceneBeat(
                start=round(a, 2),
                end=round(b, 2),
                description=desc,
                energy=round(e, 3),
                tags=tags,
            )
        )
    return scenes


def analyze_local(
    asset: VideoAsset,
    *,
    platform_hint: PlatformHint | str = "generic",
    extra_notes: str = "",
) -> VideoSonicProfile:
    duration = asset.duration_sec
    curve = []
    energy_mean = 0.45
    speech_cov = 0.0
    has_speech = False
    existing_music = False
    stats: dict = {}

    if asset.audio_path and Path(asset.audio_path).exists():
        stats = _audio_stats(asset)
        curve = stats.get("energy_curve") or []
        energy_mean = float(stats.get("energy_mean") or 0.45)
        speech_hint = float(stats.get("speech_hint") or 0.0)
        music_hint = float(stats.get("music_hint") or 0.0)
        silence = float(stats.get("silence_ratio") or asset.silence_ratio or 0.0)
        speech_cov = max(0.0, min(1.0, speech_hint * (1.0 - silence * 0.5)))
        # Silero VAD only when the probe already thinks someone might be talking.
        # Steady music used to load a full Whisper model on every analyze.
        if speech_hint >= 0.2:
            measured = _vad_coverage(asset.audio_path, duration)
            if measured is not None:
                speech_cov = measured
        has_speech = speech_cov > 0.12
        existing_music = (not has_speech and music_hint > 0.35) or (
            music_hint > 0.5 and speech_cov < 0.3
        )
    elif asset.has_audio:
        energy_mean = 0.4

    cuts: list[float] = []
    src = asset.proxy_path or asset.local_path
    if asset.scene_cuts is not None:
        cuts = list(asset.scene_cuts)
    else:
        cuts = _scenedetect_cuts(src) or []
        if not cuts:
            try:
                cuts = scene_cut_times(src)
            except Exception:
                cuts = []

    pacing = _pacing_from_cuts(len(cuts), duration)
    bpm = _bpm_from_pacing(pacing, cuts, duration)
    platform = _platform_from_aspect(asset.aspect, platform_hint)
    content_type = _content_type(extra_notes, duration, asset.aspect, speech_cov)
    moods = _moods(
        speech=speech_cov,
        energy_mean=energy_mean,
        pacing=pacing,
        content_type=content_type,
        notes=extra_notes,
    )
    instrumental = speech_cov > 0.25
    queries = _search_queries(moods, content_type, bpm, instrumental, pacing, extra_notes)

    def lookup(t: float) -> float:
        if not curve:
            return energy_mean
        best = curve[0]
        for pt in curve:
            if abs(pt.t - t) < abs(best.t - t):
                best = pt
        return best.energy

    scenes = _scenes_from_cuts(duration, cuts, lookup, speech_cov)
    hook = peak_window(curve, duration, width=min(6.0, max(3.0, duration * 0.35)))
    # IG-like: if the peak is at the very start of a talking clip, prefer a smile/action beat later.
    if has_speech and duration > 8 and hook[0] < 1.0:
        later = peak_window(
            [p for p in curve if p.t >= duration * 0.25] or curve,
            duration,
            width=min(6.0, duration * 0.3),
        )
        if later[1] > hook[1]:
            hook = later

    degraded = list(asset.degraded)
    if not curve:
        degraded.append("audio-heuristics-weak")
    if not cuts:
        degraded.append("scene-cuts-weak")

    return VideoSonicProfile(
        asset_id=asset.asset_id,
        duration_sec=duration,
        aspect=asset.aspect,
        content_type=content_type,
        has_speech=has_speech,
        speech_coverage=round(speech_cov, 3),
        existing_music=existing_music,
        overall_mood=moods,
        energy_mean=round(energy_mean, 3),
        energy_curve=curve[:24],
        pacing=pacing,  # type: ignore[arg-type]
        scenes=scenes,
        hook_window=hook,
        suggested_bpm=bpm,
        avoid=_avoid(speech_cov, energy_mean, content_type),
        search_queries=queries,
        platform_hint=platform,
        analyzer="local",
        degraded=degraded,
    )


def _audio_stats(asset: VideoAsset) -> dict:
    raw = asset.audio_stats or {}
    if raw.get("energy_curve") or "energy_mean" in raw:
        curve = [
            EnergyPoint(t=float(pt.get("t") or 0.0), energy=float(pt.get("energy") or 0.0))
            for pt in (raw.get("energy_curve") or [])
            if isinstance(pt, dict)
        ]
        stats = dict(raw)
        stats["energy_curve"] = curve
        return stats
    if asset.audio_path:
        return probe_audio(asset.audio_path)
    return {}


def _vad_coverage(audio_path: str, duration: float) -> float | None:
    """Speech fraction from Silero VAD. Does not load a Whisper model."""
    if duration <= 0:
        return None
    try:
        import numpy as np
        from faster_whisper.vad import VadOptions, get_speech_timestamps
    except Exception:
        return None
    try:
        with wave.open(audio_path, "rb") as wf:
            rate = wf.getframerate() or 16000
            channels = wf.getnchannels() or 1
            if wf.getsampwidth() != 2:
                return None
            raw = wf.readframes(wf.getnframes())
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        if channels > 1:
            usable = (audio.size // channels) * channels
            audio = audio[:usable].reshape(-1, channels).mean(axis=1)
        if rate != 16000 and audio.size:
            new_len = max(1, int(audio.size * 16000 / rate))
            src_x = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
            dst_x = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
            audio = np.interp(dst_x, src_x, audio).astype(np.float32)
        stamps = get_speech_timestamps(
            audio,
            VadOptions(
                max_speech_duration_s=30,
                min_silence_duration_ms=160,
                min_speech_duration_ms=200,
                speech_pad_ms=80,
            ),
            sampling_rate=16000,
        )
        spoken = 0.0
        for seg in stamps:
            spoken += max(0.0, (float(seg["end"]) - float(seg["start"])) / 16000.0)
        return max(0.0, min(1.0, spoken / duration))
    except Exception:
        return None


def _scenedetect_cuts(src: str) -> list[float] | None:
    """Optional PySceneDetect; None if the extra is not installed or it fails."""
    try:
        from scenedetect import SceneManager, open_video  # type: ignore
        from scenedetect.detectors import ContentDetector  # type: ignore
    except Exception:
        return None
    try:
        video = open_video(src)
        manager = SceneManager()
        manager.add_detector(ContentDetector(threshold=27.0))
        manager.detect_scenes(video)
        scenes = manager.get_scene_list()
        times = [round(float(pair[0].get_seconds()), 3) for pair in scenes]
        return [t for t in times if t > 0.12]
    except Exception:
        return None



