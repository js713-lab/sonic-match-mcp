from __future__ import annotations

import pytest

from sonicmatch.errors import SonicError
from sonicmatch.ingest import ingest_video
from sonicmatch.policy import looks_like_trending_request, ytdlp_extractor_failed
from sonicmatch.ssrf import parse_source_url
from sonicmatch.tools import configure, generate_bed, recommend_bgm, search_music, status


def test_https_only_remote():
    with pytest.raises(SonicError) as exc:
        parse_source_url("http://example.com/clip.mp4")
    assert exc.value.code == "SSRF_REJECTED"
    assert "HTTPS" in exc.value.message


def test_platform_url_disabled_by_default(settings):
    configure(settings)
    with pytest.raises(SonicError) as exc:
        ingest_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", settings=settings)
    assert exc.value.code in {"YTDLP_DISABLED", "BAD_URL"}
    if exc.value.code == "BAD_URL":
        pytest.skip("DNS unavailable for youtube.com")
    assert exc.value.code == "YTDLP_DISABLED"


def test_generate_bed_requires_ack(settings):
    configure(settings)
    out = generate_bed(prompt="warm cafe", duration_sec=8, bpm=108)
    assert out["ok"] is False
    assert out["code"] == "GENERATED_TERMS"


def test_search_trending_returns_empty(settings):
    configure(settings)
    out = search_music("trending tiktok sound for reels")
    assert out["ok"] is True
    assert out["tracks"] == []
    assert out.get("trending_available") is False
    assert out.get("code") == "TRENDING_UNAVAILABLE"


def test_recommend_never_claims_trending_or_content_id_clearance(settings):
    configure(settings)
    out = recommend_bgm(mood="warm", catalog="seed", max_results=3, platform_hint="instagram_reel")
    assert out["ok"] is True
    assert out["trending_available"] is False
    assert "content_id_warning" in out
    assert "Content ID" in out["content_id_warning"]
    for rec in out["recommendations"]:
        assert rec["content_id_risk"] in {"unknown", "likely"}
        assert rec["content_id_risk"] != "cleared"


def test_status_exposes_day1_gates(settings):
    configure(settings)
    out = status()
    assert out["ok"] is True
    assert out["ytdlp_enabled"] is False
    risks = out["day1_risks"]
    assert risks["trending"]["available"] is False
    assert risks["generated_audio"]["requires_ack"] is True
    assert risks["ytdlp"]["enabled"] is False


def test_trending_detector():
    assert looks_like_trending_request("get me a trending sound")
    assert looks_like_trending_request("official sticker audio")
    assert not looks_like_trending_request("warm acoustic cafe bed")


def test_extractor_failure_detector():
    assert ytdlp_extractor_failed("ERROR: Unsupported URL: https://tiktok.com/x")
    assert ytdlp_extractor_failed("Unable to extract webpage")
    assert not ytdlp_extractor_failed("some unrelated ffmpeg note")
