import gzip
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend import app as app_module
from backend.app import config, health, parse_tracklog
from tests.fitfile import fit_file


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
    igc = Path(__file__).resolve().parent.parent / "test.igc"
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


TCX = b"""<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
<Activities><Activity><Lap><Track>
<Trackpoint><Time>2025-01-01T00:00:00Z</Time><Position><LatitudeDegrees>1</LatitudeDegrees><LongitudeDegrees>1</LongitudeDegrees></Position><AltitudeMeters>1</AltitudeMeters></Trackpoint>
<Trackpoint><Time>2025-01-01T00:00:01Z</Time><Position><LatitudeDegrees>1</LatitudeDegrees><LongitudeDegrees>2</LongitudeDegrees></Position><AltitudeMeters>2</AltitudeMeters></Trackpoint>
</Track></Lap></Activity></Activities></TrainingCenterDatabase>"""
FIT = fit_file([(datetime(2025, 1, 1, 0, 0, s, tzinfo=timezone.utc), 1.0, 1.0 + s, 1.0) for s in range(3)])


@pytest.mark.parametrize("data, fixes", [(TCX, 2), (FIT, 3)])
def test_fit_and_tcx_detected_from_content(data, fixes):
    assert parse_tracklog(data)["properties"]["num_fixes"] == fixes


def test_gzipped_files_are_unpacked():
    igc = (Path(__file__).resolve().parent.parent / "test.igc").read_bytes()
    assert parse_tracklog(gzip.compress(igc))["properties"]["num_fixes"] == 15234
    assert parse_tracklog(gzip.compress(FIT))["properties"]["num_fixes"] == 3


def test_fit_without_positions_is_422():
    no_gps = fit_file([(datetime(2025, 1, 1, 0, 0, s, tzinfo=timezone.utc), None, None, 1.0) for s in range(2)])
    with pytest.raises(HTTPException) as e:
        parse_tracklog(no_gps)
    assert e.value.status_code == 422 and "no GPS positions" in e.value.detail


@pytest.mark.parametrize("data, status, message", [
    (b"\x1f\x8bnot really gzip", 422, "Not a valid .gz"),
    (gzip.compress(TCX)[:-20], 422, "incomplete"),
    (gzip.compress(b" " * 2000), 413, "too large"),
])
def test_bad_gzip(monkeypatch, data, status, message):
    monkeypatch.setattr(app_module, "MAX_UNZIPPED_BYTES", 1000)
    with pytest.raises(HTTPException) as e:
        parse_tracklog(data)
    assert e.value.status_code == status and message in e.value.detail
