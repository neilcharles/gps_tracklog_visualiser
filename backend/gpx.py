"""GPX tracklog loading (Strava, Garmin, phone apps, varios), via gpxpy."""

from __future__ import annotations

import gpxpy
import gpxpy.gpx

from backend.tracks import samples_to_points, track_feature


def parse_gpx(data: bytes) -> dict:
    """Parse GPX bytes into the shared track Feature (see backend.tracks).

    Raises ValueError with a user-facing message if the file can't be replayed.
    """
    try:
        gpx = gpxpy.parse(data)
    except (gpxpy.gpx.GPXException, UnicodeDecodeError) as e:
        raise ValueError(f"Not a valid GPX file: {e}") from None

    raw = [pt for trk in gpx.tracks for seg in trk.segments for pt in seg.points]
    if not raw:  # some apps export the path as a route instead of a track
        raw = [pt for rte in gpx.routes for pt in rte.points]

    points = samples_to_points(
        (pt.time, pt.longitude, pt.latitude, pt.elevation) for pt in raw if pt.time is not None
    )
    name = gpx.author_name or next((trk.name for trk in gpx.tracks if trk.name), None)
    return track_feature(points, name, None, points[0][0].date())

