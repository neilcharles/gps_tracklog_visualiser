"""TCX tracklog loading (Garmin Training Center XML, still exported by Strava and others)."""

from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree

from backend.tracks import samples_to_points, track_feature

NS = {"tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}


def is_tcx(data: bytes) -> bool:
    """Whether XML bytes look like TCX rather than GPX, from the root element near the start."""
    return b"TrainingCenterDatabase" in data[:4096]


def parse_tcx(data: bytes) -> dict:
    """Parse TCX bytes into the shared track Feature (see backend.tracks).

    Raises ValueError with a user-facing message if the file can't be replayed.
    """
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as e:
        raise ValueError(f"Not a valid TCX file: {e}") from None

    samples = []
    for tp in root.iterfind(".//tcx:Trackpoint", NS):
        time = tp.findtext("tcx:Time", namespaces=NS)
        lat = tp.findtext("tcx:Position/tcx:LatitudeDegrees", namespaces=NS)
        lon = tp.findtext("tcx:Position/tcx:LongitudeDegrees", namespaces=NS)
        if not (time and lat and lon):
            continue  # e.g. heart-rate-only points before the GPS had a fix
        alt = tp.findtext("tcx:AltitudeMeters", namespaces=NS)
        try:
            samples.append((
                datetime.fromisoformat(time.strip().replace("Z", "+00:00")),
                float(lon), float(lat), float(alt) if alt else None,
            ))
        except ValueError:
            continue  # skip a malformed point rather than reject the file
    if not samples:
        raise ValueError("TCX file has no GPS positions (an indoor activity?), so it can't be replayed")
    points = samples_to_points(samples)
    return track_feature(points, None, None, points[0][0].date())
