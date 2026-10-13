from datetime import datetime, timezone

import pytest

from backend.gpx import parse_gpx


def gpx(body: str, metadata: str = "") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
{metadata}{body}
</gpx>""".encode()


def pt(lat, lon, time=None, ele=None, tag="trkpt"):
    inner = (f"<ele>{ele}</ele>" if ele is not None else "") + (f"<time>{time}</time>" if time else "")
    return f'<{tag} lat="{lat}" lon="{lon}">{inner}</{tag}>'


def test_basic_track():
    f = parse_gpx(gpx(
        "<trk><name>Whernside Loop</name><trkseg>"
        + pt(54.2, -2.35, "2025-04-05T09:00:00Z", 290.8)
        + pt(54.21, -2.36, "2025-04-05T09:00:10Z", 300)
        + "</trkseg></trk>"))
    assert f["geometry"]["coordinates"] == [[-2.35, 54.2, 290.8], [-2.36, 54.21, 300]]
    p = f["properties"]
    assert p["pilot"] == "Whernside Loop"
    assert p["glider"] is None
    assert p["date"] == "2025-04-05"
    assert p["times"] == [0, 10]
    assert p["start_time"] == datetime(2025, 4, 5, 9, tzinfo=timezone.utc).isoformat()
    assert p["max_alt"] == 300


def test_author_name_preferred_over_track_name():
    f = parse_gpx(gpx(
        "<trk><name>Morning flight</name><trkseg>"
        + pt(1, 1, "2025-01-01T00:00:00Z", 1) + pt(1, 2, "2025-01-01T00:00:01Z", 1)
        + "</trkseg></trk>",
        metadata="<metadata><author><name>Jo Pilot</name></author></metadata>"))
    assert f["properties"]["pilot"] == "Jo Pilot"


def test_segments_merged_in_time_order_and_duplicates_dropped():
    f = parse_gpx(gpx(
        "<trk><trkseg>"
        + pt(1, 3, "2025-01-01T00:00:20Z", 30)
        + "</trkseg><trkseg>"
        + pt(1, 1, "2025-01-01T00:00:00Z", 10)
        + pt(1, 2, "2025-01-01T00:00:10Z", 20)
        + pt(1, 9, "2025-01-01T00:00:10Z", 99)
        + "</trkseg></trk>"))
    assert [c[0] for c in f["geometry"]["coordinates"]] == [1, 2, 3]
    assert f["properties"]["times"] == [0, 10, 20]


def test_offset_times_converted_to_utc():
    f = parse_gpx(gpx(
        "<trk><trkseg>"
        + pt(1, 1, "2025-06-01T10:00:00+02:00", 1) + pt(1, 2, "2025-06-01T10:00:05+02:00", 1)
        + "</trkseg></trk>"))
    assert f["properties"]["start_time"] == "2025-06-01T08:00:00+00:00"


def test_missing_elevations_interpolated_and_extended():
    f = parse_gpx(gpx(
        "<trk><trkseg>"
        + pt(1, 1, "2025-01-01T00:00:00Z")
        + pt(1, 2, "2025-01-01T00:00:10Z", 100)
        + pt(1, 3, "2025-01-01T00:00:20Z")
        + pt(1, 4, "2025-01-01T00:00:40Z", 400)
        + pt(1, 5, "2025-01-01T00:00:50Z")
        + "</trkseg></trk>"))
    assert [c[2] for c in f["geometry"]["coordinates"]] == [100, 100, 200, 400, 400]


def test_route_used_when_no_track():
    f = parse_gpx(gpx(
        "<rte>"
        + pt(1, 1, "2025-01-01T00:00:00Z", 5, tag="rtept")
        + pt(1, 2, "2025-01-01T00:00:05Z", 6, tag="rtept")
        + "</rte>"))
    assert f["properties"]["num_fixes"] == 2


def test_no_timestamps_rejected():
    with pytest.raises(ValueError, match="no timestamped"):
        parse_gpx(gpx("<trk><trkseg>" + pt(1, 1, ele=1) + pt(1, 2, ele=2) + "</trkseg></trk>"))


def test_no_elevation_rejected():
    with pytest.raises(ValueError, match="no elevation"):
        parse_gpx(gpx(
            "<trk><trkseg>"
            + pt(1, 1, "2025-01-01T00:00:00Z") + pt(1, 2, "2025-01-01T00:00:05Z")
            + "</trkseg></trk>"))


def test_invalid_xml_rejected():
    with pytest.raises(ValueError, match="Not a valid GPX"):
        parse_gpx(b"<gpx><trk>")
