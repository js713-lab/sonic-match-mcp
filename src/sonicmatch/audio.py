"""Local audio heuristics from a 16 kHz mono PCM WAV (stdlib only)."""

from __future__ import annotations

import array
import math
import warnings
import wave
from pathlib import Path

from sonicmatch.models import EnergyPoint


def _empty_stats() -> dict:
    return {
        "has_audio": False,
        "duration": 0.0,
        "energy_curve": [],
        "energy_mean": 0.0,
        "energy_var": 0.0,
        "silence_ratio": 1.0,
        "zcr_mean": 0.0,
        "speech_hint": 0.0,
        "music_hint": 0.0,
    }


def _summarize(energies: list[float], zcrs: list[float], curve: list[EnergyPoint], duration: float) -> dict:
    mean = sum(energies) / len(energies) if energies else 0.0
    var = sum((e - mean) ** 2 for e in energies) / len(energies) if energies else 0.0
    zcr_mean = sum(zcrs) / len(zcrs) if zcrs else 0.0
    silent = sum(1 for e in energies if e < 0.06)
    silence_ratio = silent / len(energies) if energies else 1.0
    # Speech is bursty. A steady tone has a stable ZCR and must not look like speech.
    speech_hint = 0.0
    if mean > 0.05 and var > 0.008 and zcr_mean > 0.04:
        speech_hint = min(1.0, 0.35 + var * 8 + zcr_mean * 4)
    elif mean > 0.04 and zcr_mean > 0.08:
        speech_hint = min(1.0, 0.25 + zcr_mean * 5)
    music_hint = 0.0
    if mean > 0.12 and var < 0.02:
        music_hint = min(1.0, mean)
    if mean > 0.2 and zcr_mean < 0.06:
        music_hint = max(music_hint, min(1.0, mean + 0.1))
    return {
        "has_audio": True,
        "duration": duration,
        "energy_curve": curve,
        "energy_mean": round(mean, 4),
        "energy_var": round(var, 5),
        "silence_ratio": round(silence_ratio, 4),
        "zcr_mean": round(zcr_mean, 4),
        "speech_hint": round(speech_hint, 4),
        "music_hint": round(music_hint, 4),
    }


def _audioop():
    """Stdlib PCM helpers. Removed in Python 3.13."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import audioop
        return audioop
    except Exception:
        return None


def _stats_audioop(
    raw: bytes,
    *,
    channels: int,
    sampwidth: int,
    rate: int,
    window_sec: float,
) -> dict | None:
    audioop = _audioop()
    if audioop is None or sampwidth not in (1, 2) or rate <= 0:
        return None
    if channels == 2:
        raw = audioop.tomono(raw, sampwidth, 0.5, 0.5)
    elif channels != 1:
        return None
    width = sampwidth
    peak = 32768.0 if sampwidth == 2 else 128.0
    frame = max(1, int(rate * window_sec))
    min_samples = max(1, frame // 5)
    total = len(raw) // width
    energies: list[float] = []
    zcrs: list[float] = []
    curve: list[EnergyPoint] = []
    start = 0
    while start < total:
        end = min(start + frame, total)
        count = end - start
        # A few leftover samples at the tail are not a real window. They used to
        # inflate energy variance and force a speech model on steady music.
        if count < min_samples:
            break
        chunk = raw[start * width : end * width]
        rms = float(audioop.rms(chunk, width))
        crossings = float(audioop.cross(chunk, width))
        energy = min(1.0, rms / (peak * 0.35))
        energies.append(energy)
        zcrs.append(crossings / count)
        curve.append(EnergyPoint(t=round(start / float(rate), 3), energy=round(energy, 4)))
        start = end
    duration = total / float(rate)
    return _summarize(energies, zcrs, curve, duration)


def dump_audio_stats(stats: dict) -> dict:
    """JSON-safe copy of a probe, for storage on the asset."""
    curve = []
    for pt in stats.get("energy_curve") or []:
        if isinstance(pt, dict):
            t, energy = pt.get("t"), pt.get("energy")
        else:
            t, energy = pt.t, pt.energy
        curve.append({"t": float(t or 0.0), "energy": float(energy or 0.0)})
    keep = (
        "has_audio",
        "duration",
        "energy_mean",
        "energy_var",
        "silence_ratio",
        "zcr_mean",
        "speech_hint",
        "music_hint",
    )
    out = {key: stats.get(key) for key in keep}
    out["energy_curve"] = curve
    return out


def probe_audio(path: str | Path) -> dict:
    """One audio pass. Librosa when installed, otherwise the stdlib probe."""
    return _librosa_stats(path) or wav_stats(path)


def wav_stats(path: str | Path, window_sec: float = 1.0) -> dict:
    p = Path(path)
    if not p.exists() or p.stat().st_size < 64:
        return _empty_stats()

    with wave.open(str(p), "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate() or 16000
        sampwidth = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())

    fast = _stats_audioop(
        raw,
        channels=channels,
        sampwidth=sampwidth,
        rate=rate,
        window_sec=window_sec,
    )
    if fast is not None:
        return fast

    if sampwidth == 2:
        samples = array.array("h")
        samples.frombytes(raw)
        if channels > 1:
            samples = array.array(
                "h",
                (
                    int(sum(samples[i : i + channels]) / channels)
                    for i in range(0, len(samples) - channels + 1, channels)
                ),
            )
        peak = 32768.0
    else:
        samples = array.array("B")
        samples.frombytes(raw)
        peak = 128.0

    n = len(samples)
    duration = n / float(rate) if rate else 0.0
    win = max(1, int(rate * window_sec))
    min_samples = max(1, win // 5)
    curve: list[EnergyPoint] = []
    energies: list[float] = []
    zcrs: list[float] = []

    for start in range(0, n, win):
        chunk = samples[start : start + win]
        if len(chunk) < min_samples:
            continue
        rms = math.sqrt(sum(float(s) * float(s) for s in chunk) / len(chunk))
        energy = min(1.0, rms / (peak * 0.35))
        energies.append(energy)
        curve.append(EnergyPoint(t=round(start / float(rate), 3), energy=round(energy, 4)))
        crossings = 0
        prev = chunk[0]
        for s in chunk[1:]:
            if (s >= 0 > prev) or (s < 0 <= prev):
                crossings += 1
            prev = s
        zcrs.append(crossings / len(chunk))

    return _summarize(energies, zcrs, curve, duration)


def _librosa_stats(path: str | Path) -> dict | None:
    """Optional librosa energy curve. None when the extra is not installed."""
    try:
        import librosa  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return None
    try:
        y, sr = librosa.load(str(path), sr=16000, mono=True)
        if y.size == 0:
            return None
        hop = sr
        rms = librosa.feature.rms(y=y, frame_length=min(len(y), sr), hop_length=hop)[0]
        peak = float(np.max(rms)) or 1.0
        curve = [
            EnergyPoint(t=round(i * hop / sr, 3), energy=round(float(min(1.0, r / (peak * 0.9))), 4))
            for i, r in enumerate(rms)
        ]
        # Drop a zero-padded tail frame so it does not look like a silence burst.
        if len(curve) > 1 and (len(y) % hop) < hop // 5:
            curve = curve[:-1]
        mean = float(np.mean([p.energy for p in curve])) if curve else 0.0
        var = float(np.var([p.energy for p in curve])) if curve else 0.0
        zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))
        silence_ratio = float(np.mean([1.0 if p.energy < 0.06 else 0.0 for p in curve])) if curve else 1.0
        speech_hint = 0.0
        if mean > 0.05 and var > 0.008 and zcr > 0.04:
            speech_hint = min(1.0, 0.35 + var * 8 + zcr * 4)
        music_hint = 0.0
        if mean > 0.12 and var < 0.02:
            music_hint = min(1.0, mean)
        return {
            "has_audio": True,
            "duration": float(len(y) / sr),
            "energy_curve": curve,
            "energy_mean": round(mean, 4),
            "energy_var": round(var, 5),
            "silence_ratio": round(silence_ratio, 4),
            "zcr_mean": round(zcr, 4),
            "speech_hint": round(speech_hint, 4),
            "music_hint": round(music_hint, 4),
        }
    except Exception:
        return None


def peak_window(curve: list[EnergyPoint], duration: float, width: float = 6.0) -> tuple[float, float]:
    if not curve:
        end = min(duration, width) if duration else width
        return (0.0, round(end, 2))
    width = min(width, duration) if duration else width
    best_t = curve[0].t
    best = -1.0
    for i, pt in enumerate(curve):
        acc = 0.0
        n = 0
        for other in curve[i:]:
            if other.t - pt.t > width:
                break
            acc += other.energy
            n += 1
        avg = acc / n if n else 0.0
        if avg > best:
            best = avg
            best_t = pt.t
    start = max(0.0, best_t)
    end = min(duration or start + width, start + width)
    if end - start < 2 and duration > 2:
        end = min(duration, start + min(width, duration))
    return (round(start, 2), round(end, 2))
