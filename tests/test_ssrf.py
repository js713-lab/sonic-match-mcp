from __future__ import annotations

import pytest

from sonicmatch.errors import SonicError
from sonicmatch.ssrf import classify_url, parse_source_url, resolve_and_check_host


def test_reject_loopback_literal():
    with pytest.raises(SonicError) as exc:
        parse_source_url("https://127.0.0.1/secret.mp4")
    assert exc.value.code == "SSRF_REJECTED"


def test_reject_plain_http():
    with pytest.raises(SonicError) as exc:
        parse_source_url("http://example.com/clip.mp4")
    assert exc.value.code == "SSRF_REJECTED"


def test_reject_localhost_name():
    with pytest.raises(SonicError) as exc:
        parse_source_url("https://localhost/clip.mp4")
    assert exc.value.code == "SSRF_REJECTED"


def test_reject_file_scheme():
    with pytest.raises(SonicError) as exc:
        parse_source_url("file:///etc/passwd")
    assert exc.value.code == "SSRF_REJECTED"


def test_reject_private_ip():
    with pytest.raises(SonicError):
        parse_source_url("https://192.168.1.10/v.mp4")
    with pytest.raises(SonicError):
        parse_source_url("https://10.0.0.2/v.mp4")


def test_reject_ipv6_loopback():
    with pytest.raises(SonicError):
        resolve_and_check_host("::1")


def test_youtube_classified_platform():
    assert classify_url("https://www.youtube.com/watch?v=aaaaaaaaaaa") == "platform"
    assert classify_url("https://youtu.be/aaaaaaaaaaa") == "platform"


def test_direct_mp4_classified():
    # 1.1.1.1 is public; this only classifies, it does not fetch.
    assert classify_url("https://example.com/media/clip.mp4") == "direct"
