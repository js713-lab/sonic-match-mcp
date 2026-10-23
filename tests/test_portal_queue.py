"""Hosted match queue and deletion of the upload or download."""

from __future__ import annotations

import time
from pathlib import Path

from sonicmatch.config import Settings
from sonicmatch.hosted import portal
from sonicmatch.ingest import _hash_id, discard_ingested_media


def test_sixth_match_waits_for_a_slot():
    portal.reset_match_slots()
    first = __import__("threading").Event()
    second = __import__("threading").Event()

    def fake(source: str, platform: str) -> dict:
        if source == "job-5":
            second.wait(5)
        else:
            first.wait(5)
        return {"ok": True}

    original = portal.match_source
    portal.match_source = fake
    try:
        ids = [portal.start_match(f"job-{i}", "instagram_reel") for i in range(6)]
        queued = ""
        deadline = time.time() + 2
        while time.time() < deadline:
            states = {job_id: (portal.match_job(job_id) or {}).get("status") for job_id in ids}
            if list(states.values()).count("working") == 5 and list(states.values()).count("queued") == 1:
                queued = next(job_id for job_id, status in states.items() if status == "queued")
                break
            time.sleep(0.02)
        assert queued
        assert portal.match_job(queued)["ahead"] == 5
        first.set()
        deadline = time.time() + 2
        while time.time() < deadline and (portal.match_job(queued) or {}).get("status") != "working":
            time.sleep(0.02)
        assert portal.match_job(queued)["status"] == "working"
        second.set()
        deadline = time.time() + 2
        while time.time() < deadline:
            if all((portal.match_job(job_id) or {}).get("status") == "done" for job_id in ids):
                break
            time.sleep(0.02)
        assert all((portal.match_job(job_id) or {}).get("status") == "done" for job_id in ids)
        assert portal._running == 0
    finally:
        first.set()
        second.set()
        portal.match_source = original
        deadline = time.time() + 2
        while time.time() < deadline and portal._running:
            time.sleep(0.02)
        portal.reset_match_slots()


def test_finished_match_deletes_upload_and_download(tmp_path: Path):
    cache = tmp_path / "cache"
    settings = Settings(cache_dir=cache)
    url = "https://cdn.example.com/clip.mp4"
    asset = cache / "assets" / _hash_id("url", url, "60")
    frames = asset / "frames"
    frames.mkdir(parents=True)
    (asset / "source.mp4").write_bytes(b"downloaded-video")
    (asset / "proxy.mp4").write_bytes(b"proxy-video")
    (asset / "audio.wav").write_bytes(b"wav")
    (frames / "0001.jpg").write_bytes(b"jpg")
    (asset / "profile.json").write_text("{}", encoding="utf-8")
    (asset / "index.json").write_text("{}", encoding="utf-8")
    upload = cache / "portal" / "portal-abc.mp4"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"uploaded-video")
    outside = tmp_path / "mine.mp4"
    outside.write_bytes(b"keep-me")
    timeline = cache / "timelines" / "keep.json"
    timeline.parent.mkdir(parents=True)
    timeline.write_text("{}", encoding="utf-8")

    discard_ingested_media(url, 60, keep_profile=True, settings=settings)
    assert not (asset / "source.mp4").exists()
    assert not (asset / "proxy.mp4").exists()
    assert not (asset / "audio.wav").exists()
    assert not (frames / "0001.jpg").exists()
    assert (asset / "profile.json").exists()
    assert (asset / "index.json").exists()
    assert timeline.exists()

    discard_ingested_media(str(upload), 60, keep_profile=False, settings=settings)
    assert not upload.exists()
    discard_ingested_media(str(outside), 60, keep_profile=False, settings=settings)
    assert outside.read_bytes() == b"keep-me"


def test_cleanup_does_not_follow_a_symlink_outside_the_cache(tmp_path: Path):
    cache = tmp_path / "cache"
    settings = Settings(cache_dir=cache)
    outside = tmp_path / "original.mp4"
    outside.write_bytes(b"original")
    upload = cache / "portal" / "portal-link.mp4"
    upload.parent.mkdir(parents=True)
    upload.symlink_to(outside)
    # The id is taken from the resolved target, matching ingest. The link itself is what we drop.
    asset_id = _hash_id(
        "file",
        str(outside.resolve()),
        str(outside.stat().st_mtime_ns),
        str(outside.stat().st_size),
        "60",
    )
    asset = cache / "assets" / asset_id
    asset.mkdir(parents=True)
    (asset / "profile.json").write_text("{}", encoding="utf-8")
    (asset / "source.mp4").symlink_to(outside)

    discard_ingested_media(str(upload), 60, keep_profile=True, settings=settings)
    assert outside.read_bytes() == b"original"
    assert not upload.exists()
    assert not (asset / "source.mp4").exists()
    assert (asset / "profile.json").exists()
