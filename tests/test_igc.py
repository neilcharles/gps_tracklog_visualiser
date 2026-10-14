from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from backend.igc import load_igc, parse_igc

SAMPLE = Path(__file__).resolve().parent.parent / "test.igc"


@pytest.fixture(scope="module")
def flight():
    return load_igc(SAMPLE)


def test_headers(flight):
    assert flight.date == date(2026, 8, 7)
    assert flight.pilot == "Benjamin Dry"
    assert flight.glider == "Niviuk Peak 6"


def test_fix_count(flight):
    assert len(flight.fixes) == 15234


def test_first_fix(flight):
    f = flight.fixes[0]
    assert f.time == datetime(2026, 8, 7, 10, 6, 3, tzinfo=timezone.utc)
    assert f.lat == pytest.approx(51 + 21.486 / 60)
    assert f.lon == pytest.approx(-(1 + 29.074 / 60))
    assert f.valid
    assert f.pressure_alt == 278
    assert f.gnss_alt == 277
    assert f.extensions == {"FXA": 1, "VXA": 10, "GSP": 0, "CCO": 253, "HDT": 167}


def test_task_and_events(flight):
    assert len(flight.task) == 6
    assert flight.task[2].name.endswith("TURNAREA Waypoint")
    assert [e.code for e in flight.events].count("TPC") == 4


def test_geojson(flight):
    gj = flight.to_geojson()
    assert gj["geometry"]["type"] == "LineString"
    assert len(gj["geometry"]["coordinates"]) == 15234
    assert gj["properties"]["duration_s"] == (18 * 3600 + 33 * 60 + 7) - (10 * 3600 + 6 * 60 + 3)


def test_midnight_rollover_and_negative_alt():
    text = "\n".join([
        "HFDTE311226",
        "B2359585407121N00249342WA-001500421",
        "B0000025407121S00249342EV0028000000",
    ])
    f = parse_igc(text)
    assert f.fixes[0].time == datetime(2026, 12, 31, 23, 59, 58, tzinfo=timezone.utc)
    assert f.fixes[1].time == datetime(2027, 1, 1, 0, 0, 2, tzinfo=timezone.utc)
    assert f.fixes[0].pressure_alt == -15
    assert f.fixes[1].lat < 0 and f.fixes[1].lon > 0
    assert not f.fixes[1].valid


def test_new_style_date_header():
    f = parse_igc("HFDTEDATE:070826,01\nB1006035121486N00129074WA0027800277")
    assert f.date == date(2026, 8, 7)


def test_geojson_times(flight):
    gj = flight.to_geojson()
    times = gj["properties"]["times"]
    assert len(times) == len(gj["geometry"]["coordinates"])
    assert times[0] == 0
    assert times[-1] == 30424
    assert all(b >= a for a, b in zip(times, times[1:]))
