"""GeoJSON output shared by every tracklog format (IGC, GPX).

The frontend replays any track given as one Feature: a LineString of
[lon, lat, alt] plus properties including per-point times.
"""

from __future__ import annotations

from datetime import date, datetime


def track_feature(
    points: list[tuple[datetime, float, float, float]],
    pilot: str | None,
    glider: str | None,
    day: date | None,
) -> dict:
    """Build the Feature from (UTC time, lon, lat, altitude in metres) points, in time order."""
    coords = [[lon, lat, alt] for _, lon, lat, alt in points]
    props: dict = {
        "pilot": pilot,
        "glider": glider,
        "date": day.isoformat() if day else None,
        "num_fixes": len(points),
    }
    if points:
        start, end = points[0][0], points[-1][0]
        props |= {
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "duration_s": int((end - start).total_seconds()),
            "max_alt": max(c[2] for c in coords),
            # Seconds since the first point, one per coordinate.
            "times": [int((t - start).total_seconds()) for t, *_ in points],
        }
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": props,
    }
