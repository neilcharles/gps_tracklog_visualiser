from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.app import config, health, parse_tracklog


def test_health():
    assert health() == {"ok": True}


def test_config_reads_keys_from_environment(monkeypatch):
    monkeypatch.setenv("CESIUM_ION_TOKEN", "ion-token")
    monkeypatch.setenv("MAPTILER_KEY", "maptiler-key")
    assert config() == {"cesium_ion_token": "ion-token", "maptiler_key": "maptiler-key"}


def test_config_without_keys(monkeypatch):
    monkeypatch.delenv("CESIUM_ION_TOKEN", raising=False)
    monkeypatch.delenv("MAPTILER_KEY", raising=False)
    assert config() == {"cesium_ion_token": None, "maptiler_key": None}


def test_tracklog_format_detected_from_content():
    igc = Path(__file__).resolve().parent.parent / "DryB-2026-08-07.igc"
    assert parse_tracklog(igc.read_bytes())["properties"]["num_fixes"] == 15234
    gpx = b"""\xef\xbb\xbf
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
<trkpt lat="1" lon="1"><ele>1</ele><time>2025-01-01T00:00:00Z</time></trkpt>
<trkpt lat="1" lon="2"><ele>2</ele><time>2025-01-01T00:00:01Z</time></trkpt>
</trkseg></trk></gpx>"""
    assert parse_tracklog(gpx)["properties"]["num_fixes"] == 2


@pytest.mark.parametrize("data, message", [
    (b"<gpx><trk>", "Not a valid GPX"),
    (b"just some text", "No valid track points"),
])
def test_unusable_tracklog_is_422(data, message):
    with pytest.raises(HTTPException) as e:
        parse_tracklog(data)
    assert e.value.status_code == 422 and message in e.value.detail
