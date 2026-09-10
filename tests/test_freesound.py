from __future__ import annotations

from sonicmatch.music.freesound import _map_sound, license_from_url


def test_license_mapping():
    name, attrib, ok = license_from_url("https://creativecommons.org/publicdomain/zero/1.0/")
    assert name == "CC0-1.0"
    assert attrib is False
    assert ok is True
    name, attrib, ok = license_from_url("https://creativecommons.org/licenses/by-nc/4.0/")
    assert "NC" in name
    assert ok is False
    name, attrib, ok = license_from_url("https://creativecommons.org/licenses/by/4.0/")
    assert name == "CC-BY"
    assert attrib is True


def test_map_sound_is_instrumental_bed():
    track = _map_sound(
        {
            "id": 99,
            "name": "Soft Pad Loop",
            "username": "bedmaker",
            "duration": 24.0,
            "license": "http://creativecommons.org/publicdomain/zero/1.0/",
            "tags": ["pad", "ambient", "loop"],
            "previews": {"preview-hq-mp3": "https://example.com/a.mp3"},
            "url": "https://freesound.org/s/99/",
        }
    )
    assert track.id == "freesound_99"
    assert track.source == "freesound"
    assert track.instrumental is True
    assert track.loopable is True
    assert track.license == "CC0-1.0"
    assert "Freesound" in track.attribution_text
