"""Tool implementations used by the MCP server. Return dicts, never stack traces."""

from __future__ import annotations

import shutil
from collections import Counter
from typing import Any, Optional

from sonicmatch import __version__
from sonicmatch.analyze.merge import analyze_video_music as _analyze
from sonicmatch.analyze.merge import load_profile
from sonicmatch.brand import apply_brand_kit, list_brand_kits, load_brand_kit, save_brand_kit
from sonicmatch.config import Settings, load_settings
from sonicmatch.cuts import suggest_cuts as _suggest_cuts
from sonicmatch.errors import SonicError, fail, ok
from sonicmatch.ingest import ingest_video as _ingest
from sonicmatch.mix import export_mix_spec as _export_mix_spec
from sonicmatch.mix import preview_mix as _preview_mix
from sonicmatch.models import BrandKit, CATALOG_CHOICES, VideoSonicProfile
from sonicmatch.models import SearchQuery
from sonicmatch.music.generate import generate_bed as _generate_bed
from sonicmatch.music.hub import MusicHub
from sonicmatch.music.rank import rank_tracks, stub_profile_from_prefs

_settings: Settings | None = None
_hub: MusicHub | None = None


def configure(settings: Settings | None = None) -> Settings:
    global _settings, _hub
    _settings = settings or load_settings()
    _hub = MusicHub(_settings)
    return _settings


def get_settings() -> Settings:
    return _settings or configure()


def hub() -> MusicHub:
    if _hub is None:
        configure()
    assert _hub is not None
    return _hub


def _catch(fn):
    try:
        return fn()
    except SonicError as exc:
        return exc.to_dict()
    except Exception as exc:  # noqa: BLE001
        return fail("UNAVAILABLE", f"{type(exc).__name__}: {exc}")


def status() -> dict[str, Any]:
    """Which binaries and optional adapters are actually available."""

    def _run() -> dict[str, Any]:
        s = get_settings()
        h = hub()
        return ok(
            version=__version__,
            ffmpeg=bool(shutil.which("ffmpeg")),
            ffprobe=bool(shutil.which("ffprobe")),
            yt_dlp=bool(shutil.which("yt-dlp")),
            gemini=s.has_gemini,
            jamendo=s.has_jamendo,
            freesound=s.has_freesound,
            user_library_tracks=len(h.library.all()),
            seed_tracks=len(h.seed.all()),
            index_tracks=h.index.count(),
            cache_dir=str(s.cache_dir),
            brand_kits=list_brand_kits(s),
            note=(
                "v0 demos offline with the seed catalog. Missing keys degrade; "
                "they never invent Instagram/TikTok official music."
            ),
        )

    return _catch(_run)


def ingest_video(source: str, max_seconds: int = 180) -> dict[str, Any]:
    """Ingest a local video path or public URL. Returns metadata + asset_id, never bytes."""

    def _run() -> dict[str, Any]:
        asset = _ingest(source, max_seconds=max_seconds, settings=get_settings())
        payload = asset.model_dump(mode="json")
        payload["probe_json"] = {
            k: payload.get("probe_json", {}).get(k)
            for k in ("format", "n_streams")
        }
        return ok(
            asset=payload,
            hint=(
                "Call analyze_video_music next with this asset_id. "
                "Do not ask the user to paste video bytes."
            ),
        )

    return _catch(_run)


def analyze_video_music(
    asset_id: str,
    platform_hint: str = "generic",
    extra_notes: str = "",
) -> dict[str, Any]:
    """Build a VideoSonic profile (mood, energy curve, hook, BPM, search queries)."""

    def _run() -> dict[str, Any]:
        profile = _analyze(
            asset_id,
            platform_hint=platform_hint,
            extra_notes=extra_notes,
            settings=get_settings(),
        )
        notes = []
        if "gemini-disabled" in profile.degraded:
            notes.append(
                "GEMINI_API_KEY not set; used local ffmpeg/audio heuristics. "
                "Install google-genai and set the key for real video understanding."
            )
        if any(d.startswith("gemini:") for d in profile.degraded):
            notes.append("Gemini path failed; fell back to local heuristics.")
        return ok(profile=profile.model_dump(mode="json"), notes=notes)

    return _catch(_run)


def _resolve_profile(
    asset_id: Optional[str],
    profile: Optional[dict[str, Any]],
    *,
    genre: Optional[str],
    mood: Optional[str],
    instrumental_only: Optional[bool],
    platform_hint: Optional[str],
    brand_kit: Optional[str],
) -> VideoSonicProfile:
    if profile:
        resolved = VideoSonicProfile.model_validate(profile)
    elif asset_id:
        cached = load_profile(asset_id, get_settings())
        resolved = cached or _analyze(asset_id, settings=get_settings())
    else:
        resolved = stub_profile_from_prefs(
            mood=mood,
            genre=genre,
            instrumental_only=bool(instrumental_only),
            platform_hint=platform_hint or "generic",
        )
    if platform_hint:
        resolved.platform_hint = platform_hint  # type: ignore[assignment]
    if brand_kit:
        kit = load_brand_kit(brand_kit, get_settings())
        resolved = apply_brand_kit(resolved, kit)
    return resolved


def recommend_bgm(
    asset_id: Optional[str] = None,
    profile: Optional[dict[str, Any]] = None,
    genre: Optional[str] = None,
    mood: Optional[str] = None,
    instrumental_only: Optional[bool] = None,
    max_results: int = 5,
    catalog: str = "auto",
    platform_hint: Optional[str] = None,
    brand_kit: Optional[str] = None,
) -> dict[str, Any]:
    """Rank 3–7 license-safe tracks with reasons, hook in/out, and ducking hint."""

    def _run() -> dict[str, Any]:
        if catalog not in CATALOG_CHOICES:
            raise SonicError("BAD_ARGS", f"catalog must be one of {', '.join(CATALOG_CHOICES)}")
        n = max(3, min(int(max_results or 5), 7))
        resolved = _resolve_profile(
            asset_id,
            profile,
            genre=genre,
            mood=mood,
            instrumental_only=instrumental_only,
            platform_hint=platform_hint,
            brand_kit=brand_kit,
        )
        inst = instrumental_only
        if inst is None:
            inst = resolved.speech_coverage > 0.25 or resolved.has_speech
        tracks, notes = hub().collect(
            resolved,
            catalog=catalog,
            limit=n,
            instrumental_only=bool(inst),
            genre=genre,
            mood=mood,
        )
        recs = rank_tracks(
            tracks,
            resolved,
            instrumental_only=bool(inst),
            genre=genre,
            mood=mood,
            max_results=n,
        )
        warning = (
            "Track licenses are independent of this MCP server's MIT license. "
            "Nothing here is an official Instagram / TikTok / YouTube Music sticker. "
            "Do not recommend commercial pop unless the adapter is a user-owned library."
        )
        return ok(
            recommendations=[r.model_dump(mode="json") for r in recs],
            instrumental_only=bool(inst),
            platform_hint=resolved.platform_hint,
            notes=notes,
            license_warning=warning,
        )

    return _catch(_run)


def search_music(
    query: str,
    bpm_min: Optional[int] = None,
    bpm_max: Optional[int] = None,
    instrumental: Optional[bool] = None,
    duration_min: Optional[float] = None,
    duration_max: Optional[float] = None,
    limit: int = 10,
    catalog: str = "auto",
) -> dict[str, Any]:
    """Free-text catalog search (seed always; Jamendo/Freesound/library if configured)."""

    def _run() -> dict[str, Any]:
        q = SearchQuery(
            query=query or "",
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            instrumental=instrumental,
            duration_min=duration_min,
            duration_max=duration_max,
            limit=max(1, min(int(limit or 10), 25)),
        )
        tracks, notes = hub().search(q, catalog)
        return ok(tracks=[t.model_dump(mode="json") for t in tracks], notes=notes)

    return _catch(_run)


def get_track(track_id: str) -> dict[str, Any]:
    """Fetch one track's metadata, license, and URLs."""

    def _run() -> dict[str, Any]:
        track = hub().get(track_id)
        if track is None:
            raise SonicError("NOT_FOUND", f"Unknown track_id: {track_id}")
        return ok(track=track.model_dump(mode="json"))

    return _catch(_run)


def preview_mix(
    asset_id: str,
    track_id: str,
    ducking: bool = True,
    bgm_db: float = -18,
    voice_db: float = -16,
) -> dict[str, Any]:
    """Trim/loop BGM to the video, optionally duck under speech, return preview paths + ffmpeg."""

    def _run() -> dict[str, Any]:
        t = hub().get(track_id)
        if t is None:
            raise SonicError("NOT_FOUND", f"Unknown track_id: {track_id}")
        profile = load_profile(asset_id, get_settings())
        result = _preview_mix(
            asset_id,
            t,
            profile=profile,
            ducking=ducking,
            bgm_db=bgm_db,
            voice_db=voice_db,
            settings=get_settings(),
        )
        return ok(**result.model_dump(mode="json"))

    return _catch(_run)


def export_mix_spec(
    asset_id: str,
    track_id: str,
    ducking: bool = True,
    bgm_db: float = -18,
    voice_db: float = -16,
    render: bool = False,
) -> dict[str, Any]:
    """Return mix spec + ffmpeg + attribution. Set render=true to also write preview files."""

    def _run() -> dict[str, Any]:
        t = hub().get(track_id)
        if t is None:
            raise SonicError("NOT_FOUND", f"Unknown track_id: {track_id}")
        profile = load_profile(asset_id, get_settings())
        result = _export_mix_spec(
            asset_id,
            t,
            profile=profile,
            ducking=ducking,
            bgm_db=bgm_db,
            voice_db=voice_db,
            render=render,
            settings=get_settings(),
        )
        return ok(**result.model_dump(mode="json"))

    return _catch(_run)


def suggest_cuts(
    asset_id: str,
    bpm: Optional[float] = None,
    track_id: Optional[str] = None,
) -> dict[str, Any]:
    """Snap scene cuts onto a beat grid. Returns EDL-ish spans + intro/peak/outro acts."""

    def _run() -> dict[str, Any]:
        profile = load_profile(asset_id, get_settings())
        if profile is None:
            profile = _analyze(asset_id, settings=get_settings())
        use_bpm = bpm
        if use_bpm is None and track_id:
            t = hub().get(track_id)
            if t and t.bpm:
                use_bpm = float(t.bpm)
        plan = _suggest_cuts(profile, bpm=use_bpm)
        return ok(**plan.model_dump(mode="json"))

    return _catch(_run)


def generate_bed(
    prompt: str,
    duration_sec: float = 16.0,
    bpm: int = 110,
    energy: float = 0.5,
    asset_id: Optional[str] = None,
) -> dict[str, Any]:
    """Generate a demo bed (local synth). Always marked source=generated — not catalog-cleared."""

    def _run() -> dict[str, Any]:
        s = get_settings()
        if asset_id:
            profile = load_profile(asset_id, s)
            if profile:
                bpm_use = int(sum(profile.suggested_bpm) / 2)
                energy_use = profile.energy_mean
                text = prompt or " ".join(profile.search_queries[:1])
                track = _generate_bed(
                    prompt=text,
                    duration_sec=profile.duration_sec or duration_sec,
                    bpm=bpm_use,
                    energy=energy_use,
                    settings=s,
                )
            else:
                track = _generate_bed(
                    prompt=prompt,
                    duration_sec=duration_sec,
                    bpm=bpm,
                    energy=energy,
                    settings=s,
                )
        else:
            track = _generate_bed(
                prompt=prompt,
                duration_sec=duration_sec,
                bpm=bpm,
                energy=energy,
                settings=s,
            )
        hub().index.upsert([track])
        return ok(
            track=track.model_dump(mode="json"),
            warning=(
                "Generated audio is NOT a licensed catalog track. "
                "Suno / Stable Audio / Lyria commercial terms are messy — "
                "do not ship this in ads without reading those terms. "
                "The local fallback is a sine-tremolo demo bed."
            ),
        )

    return _catch(_run)


def save_brand_kit_tool(
    name: str,
    bpm_min: Optional[int] = None,
    bpm_max: Optional[int] = None,
    moods: Optional[list[str]] = None,
    genres: Optional[list[str]] = None,
    instrumental_only: bool = True,
    avoid: Optional[list[str]] = None,
    notes: str = "",
) -> dict[str, Any]:
    """Persist a brand kit (BPM lock, no-vocals, mood whitelist) for recommend_bgm(brand_kit=...)."""

    def _run() -> dict[str, Any]:
        kit = BrandKit(
            name=name,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            moods=moods or [],
            genres=genres or [],
            instrumental_only=instrumental_only,
            avoid=avoid or [],
            notes=notes,
        )
        saved = save_brand_kit(kit, get_settings())
        return ok(kit=saved.model_dump(mode="json"), kits=list_brand_kits(get_settings()))

    return _catch(_run)


def analyze_batch(
    sources: list[str],
    platform_hint: str = "generic",
    extra_notes: str = "",
    max_seconds: int = 180,
) -> dict[str, Any]:
    """Analyze many clips, cluster moods, suggest one consistent mini-playlist for the series."""

    def _run() -> dict[str, Any]:
        if not sources:
            raise SonicError("BAD_ARGS", "sources must be a non-empty list of paths or URLs.")
        if len(sources) > 20:
            raise SonicError("BAD_ARGS", "analyze_batch is capped at 20 clips per call.")
        profiles: list[VideoSonicProfile] = []
        errors: list[dict[str, str]] = []
        for src in sources:
            try:
                asset = _ingest(src, max_seconds=max_seconds, settings=get_settings())
                profiles.append(
                    _analyze(
                        asset.asset_id,
                        platform_hint=platform_hint,
                        extra_notes=extra_notes,
                        settings=get_settings(),
                    )
                )
            except SonicError as exc:
                errors.append({"source": src, "code": exc.code, "error": exc.message})
        if not profiles:
            raise SonicError("BATCH_EMPTY", "No clips could be analyzed.", errors=errors)
        mood_counts = Counter(m for p in profiles for m in p.overall_mood)
        top_moods = [m for m, _n in mood_counts.most_common(3)]
        mean_energy = sum(p.energy_mean for p in profiles) / len(profiles)
        inst = any(p.speech_coverage > 0.25 for p in profiles)
        merged = VideoSonicProfile(
            asset_id="batch",
            duration_sec=sum(p.duration_sec for p in profiles) / len(profiles),
            aspect=profiles[0].aspect,
            content_type=Counter(p.content_type for p in profiles).most_common(1)[0][0],
            has_speech=any(p.has_speech for p in profiles),
            speech_coverage=max(p.speech_coverage for p in profiles),
            overall_mood=top_moods or ["warm"],
            energy_mean=mean_energy,
            pacing=Counter(p.pacing for p in profiles).most_common(1)[0][0],
            suggested_bpm=(
                min(p.suggested_bpm[0] for p in profiles),
                max(p.suggested_bpm[1] for p in profiles),
            ),
            avoid=list(dict.fromkeys(a for p in profiles for a in p.avoid)),
            search_queries=list(dict.fromkeys(q for p in profiles for q in p.search_queries))[:4],
            platform_hint=platform_hint,  # type: ignore[arg-type]
            analyzer="local",
        )
        recs = recommend_bgm(
            profile=merged.model_dump(mode="json"),
            instrumental_only=inst,
            max_results=5,
            catalog="seed",
            platform_hint=platform_hint,
        )
        return ok(
            n_ok=len(profiles),
            n_failed=len(errors),
            errors=errors,
            cluster_moods=top_moods,
            mean_energy=round(mean_energy, 3),
            shared_playlist=recs.get("recommendations") if recs.get("ok") else [],
            profiles=[{"asset_id": p.asset_id, "mood": p.overall_mood, "energy": p.energy_mean} for p in profiles],
            note="Assign this mini-playlist across the batch so the series sounds like one show.",
        )

    return _catch(_run)
