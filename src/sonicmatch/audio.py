"""Local audio heuristics from a 16 kHz mono PCM WAV (stdlib only)."""

from __future__ import annotations

import array
import math
import wave
from pathlib import Path

from sonicmatch.models import EnergyPoint


def wav_stats(path: str | Path, window_sec: float = 1.0) -> dict:
    p = Path(path)
    if not p.exists() or p.stat().st_size < 64:
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

    with wave.open(str(p), "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate() or 16000
        nframes = wf.getnframes()
        sampwidth = wf.getsampwidth()
        raw = wf.readframes(nframes)

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
        # Treat as unsigned 8-bit
        samples = array.array("B")
        samples.frombytes(raw)
        peak = 128.0

    n = len(samples)
    duration = n / float(rate) if rate else 0.0
    win = max(1, int(rate * window_sec))
    curve: list[EnergyPoint] = []
    energies: list[float] = []
    zcrs: list[float] = []
    silent_windows = 0
    windows = 0

    for start in range(0, n, win):
        chunk = samples[start : start + win]
        if not chunk:
            continue
        windows += 1
        rms = math.sqrt(sum(float(s) * float(s) for s in chunk) / len(chunk))
        energy = min(1.0, rms / (peak * 0.35))
        energies.append(energy)
        curve.append(EnergyPoint(t=round(start / float(rate), 3), energy=round(energy, 4)))
        if energy < 0.06:
            silent_windows += 1
        # Zero-crossing rate (speech tends to be higher than pads).
        crossings = 0
        prev = chunk[0]
        for s in chunk[1:]:
            if (s >= 0 > prev) or (s < 0 <= prev):
                crossings += 1
            prev = s
        zcrs.append(crossings / len(chunk))

    mean = sum(energies) / len(energies) if energies else 0.0
    var = (
        sum((e - mean) ** 2 for e in energies) / len(energies) if energies else 0.0
    )
    zcr_mean = sum(zcrs) / len(zcrs) if zcrs else 0.0
    silence_ratio = silent_windows / windows if windows else 1.0

    # Crude speech vs music:
    # speech: bursty energy (higher var), higher ZCR, moderate mean
    # music: more constant energy, lower ZCR for pads, higher mean for bangers
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
