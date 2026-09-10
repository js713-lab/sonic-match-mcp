"""Weighted ranking: mood/energy, instrumental, duration, BPM, license."""

from __future__ import annotations

from sonicmatch.models import Recommendation, Track, VideoSonicProfile
from sonicmatch.music.embed import cosine, embed_profile, embed_track

COMMERCIAL_OK = {
    "cc0",
    "cc0-1.0",
    "cc-by",
    "cc-by-4.0",
    "cc-by-3.0",
    "cc-by-sa",
    "cc-by-sa-4.0",
    "royalty-free",
    "rf",
    "public domain",
    "pd",
}
NONCOMMERCIAL = {"nc", "cc-by-nc", "cc-nc", "noncommercial", "non-commercial"}

# Instagram/TikTok official catalogs are NOT this tool. We never claim sticker clearance.
PLATFORM_NEEDS_COMMERCIAL = {
    "instagram_story",
    "instagram_reel",
    "tiktok",
    "youtube_short",
    "youtube_long",
    "generic",
}


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("_", " ").replace("-", " ").split())


def mood_overlap(track: Track, moods: list[str]) -> float:
    if not moods:
        return 0.5
    hay = {_norm(x) for x in track.moods + track.genres + track.tags + [track.title]}
    hits = 0
    for m in moods:
        nm = _norm(m)
        if not nm:
            continue
        if nm in hay or any(nm in h or h in nm for h in hay):
            hits += 1
    return hits / max(1, len(moods))


def energy_score(track: Track, target: float) -> float:
    return max(0.0, 1.0 - abs(float(track.energy) - float(target)) / 1.0)


def bpm_score(track: Track, window: tuple[int, int]) -> float:
    if not track.bpm:
        return 0.55
    lo, hi = window
    if lo <= track.bpm <= hi:
        return 1.0
    dist = min(abs(track.bpm - lo), abs(track.bpm - hi))
    return max(0.0, 1.0 - dist / 40.0)


def duration_score(track: Track, video_dur: float) -> float:
    if track.duration_sec <= 0:
        return 0.4
    if track.loopable or track.duration_sec + 1 >= video_dur:
        return 1.0 if track.duration_sec >= 12 else 0.7
    # short track under a long video without loop
    return max(0.2, track.duration_sec / max(video_dur, 1.0))


def license_ok(track: Track, platform_hint: str) -> bool:
    lic = _norm(track.license)
    if any(tok in lic for tok in NONCOMMERCIAL):
        return False
    if any(tok in lic for tok in COMMERCIAL_OK):
        # Still NOT "IG official sticker" — just "license-safe to use with attribution".
        return True
    if track.source == "seed":
        return True
    return False


def hook_slice(track: Track, video_dur: float, energy_mean: float) -> tuple[float, float]:
    """Prefer a 12–20s high-energy slice, not the whole song."""
    want = min(20.0, max(12.0, video_dur if video_dur > 0 else 15.0))
    want = min(want, max(8.0, track.duration_sec))
    if track.duration_sec <= want + 0.5:
        return (0.0, round(track.duration_sec, 2))
    # Drop-ish region: ~25–45% into the track for songs, start for loops/beds.
    if track.loopable and track.energy < 0.45:
        start = 0.0
    else:
        frac = 0.28 if energy_mean >= 0.5 else 0.12
        start = min(track.duration_sec - want, track.duration_sec * frac)
        start = max(0.0, start)
    end = min(track.duration_sec, start + want)
    return (round(start, 2), round(end, 2))


def _avoid_penalty(track: Track, avoid: list[str]) -> float:
    if not avoid:
        return 1.0
    hay = _norm(" ".join(track.moods + track.genres + track.tags + [track.title, track.license]))
    penalty = 1.0
    for a in avoid:
        na = _norm(a)
        if not na:
            continue
        tokens = [t for t in na.split() if len(t) > 2]
        if tokens and all(t in hay for t in tokens[:2]):
            penalty *= 0.35
        elif any(t in hay for t in tokens[:3]):
            penalty *= 0.7
    return penalty


def score_track(
    track: Track,
    profile: VideoSonicProfile,
    *,
    instrumental_only: bool,
    genre: str | None = None,
    mood: str | None = None,
) -> tuple[float, str, bool]:
    moods = list(profile.overall_mood)
    if mood:
        moods = [mood] + moods
    m = mood_overlap(track, moods)
    e = energy_score(track, profile.energy_mean)
    b = bpm_score(track, profile.suggested_bpm)
    d = duration_score(track, profile.duration_sec)
    inst = 1.0
    if instrumental_only:
        inst = 1.0 if track.instrumental else 0.05
    elif profile.speech_coverage > 0.25:
        inst = 1.0 if track.instrumental else 0.4
    ok = license_ok(track, profile.platform_hint)
    lic = 1.0 if ok else 0.25
    genre_s = 1.0
    if genre:
        ghay = _norm(" ".join(track.genres + track.tags + track.moods))
        genre_s = 1.0 if _norm(genre) in ghay else 0.35

    sim = cosine(embed_profile(profile), track.embed or embed_track(track))
    raw = (
        0.24 * m
        + 0.18 * e
        + 0.12 * b
        + 0.14 * inst
        + 0.10 * d
        + 0.08 * lic
        + 0.04 * genre_s
        + 0.10 * sim
    )
    raw *= _avoid_penalty(track, profile.avoid)
    raw = round(max(0.0, min(1.0, raw)), 4)

    bits = []
    if m >= 0.5 and moods:
        bits.append(f"mood overlap with {', '.join(moods[:2])}")
    if track.bpm:
        bits.append(f"{track.bpm} BPM vs suggested {profile.suggested_bpm[0]}–{profile.suggested_bpm[1]}")
    bits.append(f"energy {track.energy:.2f} vs video {profile.energy_mean:.2f}")
    if profile.speech_coverage > 0.25:
        bits.append("instrumental because speech_coverage>0.25" if track.instrumental else "HAS VOCALS — risky under speech")
    if profile.pacing:
        bits.append(f"pacing {profile.pacing}")
    bits.append(f"license {track.license}")
    if not ok:
        bits.append("not marked commercial-safe for this platform")
    reason = "; ".join(bits)
    return raw, reason, ok


def rank_tracks(
    tracks: list[Track],
    profile: VideoSonicProfile,
    *,
    instrumental_only: bool,
    genre: str | None = None,
    mood: str | None = None,
    max_results: int = 5,
) -> list[Recommendation]:
    scored: list[Recommendation] = []
    seen: set[str] = set()
    for track in tracks:
        if track.id in seen:
            continue
        seen.add(track.id)
        if instrumental_only and not track.instrumental:
            continue
        s, reason, ok = score_track(
            track,
            profile,
            instrumental_only=instrumental_only,
            genre=genre,
            mood=mood,
        )
        ducking: str = "recommended" if profile.speech_coverage > 0.25 else "off"
        scored.append(
            Recommendation(
                track=track,
                score=s,
                reason=reason,
                suggested_in_out=hook_slice(track, profile.duration_sec, profile.energy_mean),
                ducking=ducking,  # type: ignore[arg-type]
                license_ok_for_platform=ok,
                content_id_risk=track.content_id_risk if track.content_id_risk == "likely" else "unknown",
            )
        )
    scored.sort(key=lambda r: r.score, reverse=True)
    n = max(1, min(int(max_results), 7))
    return scored[:n]


def stub_profile_from_prefs(
    *,
    mood: str | None = None,
    genre: str | None = None,
    instrumental_only: bool = False,
    query: str = "",
    platform_hint: str = "generic",
) -> VideoSonicProfile:
    moods = [m for m in [mood] if m]
    queries = [q for q in [query, mood, genre] if q]
    return VideoSonicProfile(
        asset_id="prefs",
        duration_sec=15.0,
        aspect="9:16",
        content_type=genre or "lifestyle",
        has_speech=instrumental_only,
        speech_coverage=0.4 if instrumental_only else 0.0,
        overall_mood=moods or (query.split()[:3] if query else ["warm"]),
        energy_mean=0.55,
        search_queries=queries or ["instrumental bed"],
        platform_hint=platform_hint,  # type: ignore[arg-type]
        analyzer="local",
    )
