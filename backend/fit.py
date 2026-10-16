"""FIT tracklog loading (Garmin, Wahoo, Coros and others; Strava's "Export Original"), via fitdecode."""

from __future__ import annotations

import io

import fitdecode

from backend.tracks import samples_to_points, track_feature

SEMICIRCLE_DEGREES = 180 / 2**31  # FIT stores latitude and longitude in "semicircles"


def is_fit(data: bytes) -> bool:
    """FIT files have a 12- or 14-byte header with ".FIT" at bytes 8-11."""
    return len(data) >= 12 and data[0] in (12, 14) and data[8:12] == b".FIT"


def parse_fit(data: bytes) -> dict:
    """Parse FIT bytes into the shared track Feature (see backend.tracks).

    Raises ValueError with a user-facing message if the file can't be replayed.
    """
    samples = []
    try:
        with fitdecode.FitReader(io.BytesIO(data)) as fit:
            for frame in fit:
                if not (isinstance(frame, fitdecode.FitDataMessage) and frame.name == "record"):
                    continue
                lat = frame.get_value("position_lat", fallback=None)
                lon = frame.get_value("position_long", fallback=None)
                time = frame.get_value("timestamp", fallback=None)
                if lat is None or lon is None or time is None:
                    continue  # e.g. records logged before the GPS had a fix
                alt = frame.get_value("enhanced_altitude", fallback=None)
                if alt is None:
                    alt = frame.get_value("altitude", fallback=None)
                samples.append((time, lon * SEMICIRCLE_DEGREES, lat * SEMICIRCLE_DEGREES, alt))
    except fitdecode.FitError as e:
        raise ValueError(f"Not a valid FIT file: {e}") from None
    if not samples:
        raise ValueError("FIT file has no GPS positions (an indoor activity?), so it can't be replayed")
    points = samples_to_points(samples)
    return track_feature(points, None, None, points[0][0].date())
