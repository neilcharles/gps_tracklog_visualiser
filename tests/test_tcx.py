import pytest

from backend.tcx import is_tcx, parse_tcx


def tcx(trackpoints: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
<Activities><Activity Sport="Other"><Id>2025-06-01T10:00:00Z</Id>
<Lap StartTime="2025-06-01T10:00:00Z"><Track>{trackpoints}</Track></Lap>
</Activity></Activities></TrainingCenterDatabase>""".encode()


def tp(time, lat=None, lon=None, alt=None):
    pos = f"<Position><LatitudeDegrees>{lat}</LatitudeDegrees><LongitudeDegrees>{lon}</LongitudeDegrees></Position>" if lat is not None else ""
    ele = f"<AltitudeMeters>{alt}</AltitudeMeters>" if alt is not None else ""
    return f"<Trackpoint><Time>{time}</Time>{pos}{ele}<HeartRateBpm><Value>90</Value></HeartRateBpm></Trackpoint>"


def test_trackpoints_become_track():
    f = parse_tcx(tcx(
        tp("2025-06-01T10:00:00Z")  # heart rate only, no fix yet: skipped
        + tp("2025-06-01T10:00:01Z", 46.0, 7.0, 1500.5)
        + tp("2025-06-01T10:00:03.000Z", 46.001, 7.001, 1502)))
    assert f["geometry"]["coordinates"] == [[7.0, 46.0, 1500.5], [7.001, 46.001, 1502.0]]
    assert f["properties"]["times"] == [0, 2]
    assert f["properties"]["date"] == "2025-06-01"


def test_detection():
    assert is_tcx(tcx(""))
    assert not is_tcx(b'<gpx version="1.1"></gpx>')


def test_without_positions_is_rejected():
    with pytest.raises(ValueError, match="no GPS positions"):
        parse_tcx(tcx(tp("2025-06-01T10:00:00Z") + tp("2025-06-01T10:00:01Z")))


def test_invalid_xml_is_rejected():
    with pytest.raises(ValueError, match="Not a valid TCX"):
        parse_tcx(b"<TrainingCenterDatabase><oops>")
