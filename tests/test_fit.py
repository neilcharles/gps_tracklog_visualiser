from datetime import datetime, timezone

import pytest

from backend.fit import is_fit, parse_fit
from tests.fitfile import fit_file


def t(seconds):
    return datetime(2025, 6, 1, 10, 0, seconds, tzinfo=timezone.utc)


def test_records_become_track():
    f = parse_fit(fit_file([
        (t(0), 46.0, 7.0, 1500.0),
        (t(1), None, None, 1501.0),  # no GPS fix yet: skipped
        (t(2), 46.001, 7.002, None),  # altitude missing: interpolated
        (t(4), 46.002, 7.004, 1510.0),
    ]))
    coords = f["geometry"]["coordinates"]
    assert [[round(lon, 6), round(lat, 6), round(alt, 1)] for lon, lat, alt in coords] == [
        [7.0, 46.0, 1500.0], [7.002, 46.001, 1505.0], [7.004, 46.002, 1510.0]]
    p = f["properties"]
    assert p["times"] == [0, 2, 4]
    assert p["start_time"] == t(0).isoformat()
    assert (p["pilot"], p["date"]) == (None, "2025-06-01")


def test_detection():
    assert is_fit(fit_file([(t(0), 1, 1, 1)]))
    assert not is_fit(b"<gpx/>") and not is_fit(b"AXXX igc file")


def test_without_positions_is_rejected():
    with pytest.raises(ValueError, match="no GPS positions"):
        parse_fit(fit_file([(t(0), None, None, 100.0), (t(1), None, None, 101.0)]))


def test_truncated_file_is_rejected():
    data = fit_file([(t(s), 46.0, 7.0, 1500.0) for s in range(5)])
    with pytest.raises(ValueError, match="Not a valid FIT file"):
        parse_fit(data[:40])
