"""Optional Gemini video understanding path."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sonicmatch.config import Settings
from sonicmatch.errors import SonicError
from sonicmatch.models import SceneBeat, VideoAsset, VideoSonicProfile

GEMINI_PROMPT = """You are VideoSonic, a music supervisor for short-form video
(Instagram Reels / Stories / TikTok / YouTube Shorts / YouTube long).
Analyze the VIDEO itself (picture, motion, on-screen text, speech vs music) — not a script.

Return ONLY valid JSON matching this schema (no markdown, no commentary):
{
  "content_type": "lifestyle|product|vlog|event|podcast_clip|travel|cinematic|sports|other",
  "has_speech": true,
  "speech_coverage": 0.0,
  "existing_music": false,
  "overall_mood": ["warm", "playful"],
  "energy_mean": 0.62,
  "energy_curve": [{"t": 0.0, "energy": 0.3}, {"t": 4.0, "energy": 0.8}],
  "pacing": "slow|medium|fast-cut",
  "scenes": [
    {"start": 0.0, "end": 3.2, "description": "cafe exterior, golden hour", "energy": 0.4, "tags": ["cafe"]}
  ],
  "hook_window": [9.0, 15.0],
  "suggested_bpm": [95, 118],
  "avoid": ["dark cinematic drone", "aggressive trap", "lyrics-dense"],
  "search_queries": ["warm acoustic pop instrumental cafe", "upbeat indie folk no vocals 110bpm"],
  "platform_hint": "instagram_story|instagram_reel|tiktok|youtube_short|youtube_long|generic"
}

Rules:
- Instagram-like matching is energy + hook, not genre trivia.
- Prefer instrumental recommendations whenever people are talking (speech_coverage > 0.25).
- hook_window is the 4–8s span a viewer should hear the drop / chorus-like peak.
- Do NOT name copyrighted commercial pop songs.
- Do NOT claim anything is an official Instagram/TikTok/YouTube music sticker.
- search_queries must be 3 royalty-free catalog queries (mood + instrumentation + BPM).
- energy is 0–1. Timestamps in seconds.
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise SonicError("GEMINI_PARSE", "Gemini did not return JSON.")


def _norm_scenes(raw: Any, duration: float) -> list[SceneBeat]:
    if not isinstance(raw, list):
        return []
    out: list[SceneBeat] = []
    for item in raw[:16]:
        if not isinstance(item, dict):
            continue
        if "t" in item and isinstance(item["t"], (list, tuple)) and len(item["t"]) >= 2:
            start, end = float(item["t"][0]), float(item["t"][1])
        else:
            start = float(item.get("start") or 0.0)
            end = float(item.get("end") or start)
        desc = str(item.get("description") or item.get("desc") or "")
        tags = item.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        out.append(
            SceneBeat(
                start=max(0.0, start),
                end=min(duration or end, end),
                description=desc,
                energy=item.get("energy", 0.5),
                tags=[str(t) for t in tags],
            )
        )
    return out


def profile_from_gemini_json(
    data: dict[str, Any],
    asset: VideoAsset,
    *,
    platform_hint: str,
) -> VideoSonicProfile:
    scenes_raw = data.get("scenes") or []
    curve_raw = data.get("energy_curve") or []
    curve = []
    for pt in curve_raw:
        if isinstance(pt, dict):
            curve.append({"t": pt.get("t", 0), "energy": pt.get("energy", 0)})
        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
            curve.append({"t": pt[0], "energy": pt[1]})
    platform = data.get("platform_hint") or platform_hint
    return VideoSonicProfile(
        asset_id=asset.asset_id,
        duration_sec=asset.duration_sec,
        aspect=asset.aspect,
        content_type=str(data.get("content_type") or "lifestyle"),
        has_speech=bool(data.get("has_speech")),
        speech_coverage=data.get("speech_coverage", 0.0),
        existing_music=bool(data.get("existing_music")),
        overall_mood=[str(m) for m in (data.get("overall_mood") or [])][:6],
        energy_mean=data.get("energy_mean", 0.5),
        energy_curve=curve,
        pacing=data.get("pacing") or "medium",
        scenes=_norm_scenes(scenes_raw, asset.duration_sec),
        hook_window=data.get("hook_window") or (0.0, min(6.0, asset.duration_sec)),
        suggested_bpm=data.get("suggested_bpm") or (90, 120),
        avoid=[str(a) for a in (data.get("avoid") or [])],
        search_queries=[str(q) for q in (data.get("search_queries") or [])],
        platform_hint=platform,
        analyzer="gemini",
    )


def analyze_gemini(
    asset: VideoAsset,
    settings: Settings,
    *,
    platform_hint: str = "generic",
    extra_notes: str = "",
) -> VideoSonicProfile:
    if not settings.gemini_api_key:
        raise SonicError("GEMINI_DISABLED", "GEMINI_API_KEY is not set.")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise SonicError(
            "GEMINI_DISABLED",
            "google-genai is not installed. pip install 'sonicmatch-mcp[gemini]'",
        ) from exc

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = GEMINI_PROMPT
    if extra_notes.strip():
        prompt += f"\n\nUser notes / caption (optional, do not ignore the picture):\n{extra_notes.strip()[:800]}"
    prompt += (
        f"\n\nKnown probe: duration={asset.duration_sec}s aspect={asset.aspect} "
        f"has_audio={asset.has_audio} platform_hint={platform_hint}."
    )

    contents: Any
    uploaded = None
    original = (asset.original_source or "").lower()
    try:
        if original.startswith("http") and any(
            h in original for h in ("youtube.com", "youtu.be")
        ):
            contents = [
                types.Content(
                    parts=[
                        types.Part(file_data=types.FileData(file_uri=asset.original_source)),
                        types.Part(text=prompt),
                    ]
                )
            ]
        else:
            media = asset.proxy_path or asset.local_path
            if not media or not Path(media).exists():
                raise SonicError("ASSET_NOT_FOUND", "No local media for Gemini upload.")
            uploaded = client.files.upload(file=media)
            contents = [uploaded, prompt]

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        text = getattr(response, "text", None) or ""
        if not text and getattr(response, "candidates", None):
            cand = response.candidates[0]
            parts = getattr(getattr(cand, "content", None), "parts", None) or []
            text = "".join(getattr(p, "text", "") or "" for p in parts)
        if not text:
            raise SonicError("GEMINI_EMPTY", "Gemini returned an empty response.")
        data = _extract_json(text)
        return profile_from_gemini_json(data, asset, platform_hint=platform_hint)
    except SonicError:
        raise
    except Exception as exc:
        raise SonicError("GEMINI_FAILED", f"Gemini analysis failed: {type(exc).__name__}: {exc}") from exc
    finally:
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass
