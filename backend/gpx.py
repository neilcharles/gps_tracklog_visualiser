"""GPX tracklog loading (Strava, Garmin, phone apps, varios), via gpxpy."""

from __future__ import annotations

from datetime import datetime, timezone

import gpxpy
import gpxpy.gpx

from backend.tracks import track_feature


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

    # Replay needs times; keep one point per instant, in time order, all in UTC.
    by_time: dict[datetime, gpxpy.gpx.GPXTrackPoint] = {}
    for pt in raw:
        if pt.time is not None:
            by_time.setdefault(_utc(pt.time), pt)
    times = sorted(by_time)
    if len(times) < 2:
        raise ValueError("GPX has no timestamped track points, so it can't be replayed")

    elevations = _fill_elevations(times, [by_time[t].elevation for t in times])
    points = [
        (t, by_time[t].longitude, by_time[t].latitude, ele)
        for t, ele in zip(times, elevations)
    ]
    name = gpx.author_name or next((trk.name for trk in gpx.tracks if trk.name), None)
    return track_feature(points, name, None, times[0].date())


def _utc(t: datetime) -> datetime:
    """GPX times should be UTC; treat ones without a zone as UTC."""
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _fill_elevations(times: list[datetime], elevations: list[float | None]) -> list[float]:
    """Interpolate missing elevations in time; copy the nearest value at the ends."""
    known = [i for i, e in enumerate(elevations) if e is not None]
    if not known:
        raise ValueError("GPX has no elevation data, so the track can't be shown in 3D")
    filled: list[float] = []
    k = 0  # index into known of the last known point at or before i
    for i, e in enumerate(elevations):
        if e is not None:
            filled.append(e)
            continue
        while k + 1 < len(known) and known[k + 1] < i:
            k += 1
        before, after = known[k], (known[k + 1] if k + 1 < len(known) else None)
        if i < before or after is None:  # before the first / after the last known point
            filled.append(elevations[before])
        else:
            span = (times[after] - times[before]).total_seconds()
            frac = (times[i] - times[before]).total_seconds() / span
            filled.append(elevations[before] + (elevations[after] - elevations[before]) * frac)
    return filled
