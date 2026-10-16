"""GeoJSON output shared by every tracklog format (IGC, GPX, FIT, TCX).

The frontend replays any track given as one Feature: a LineString of
[lon, lat, alt] plus properties including per-point times.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timezone


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


def samples_to_points(
    samples: Iterable[tuple[datetime, float, float, float | None]],
) -> list[tuple[datetime, float, float, float]]:
    """Turn raw (time, lon, lat, elevation or None) samples, as any format gives them, into
    track_feature points: one per instant, in time order, in UTC, with gaps in elevation filled.

    Raises ValueError with a user-facing message if they can't be replayed.
    """
    by_time: dict[datetime, tuple[float, float, float | None]] = {}
    for t, lon, lat, ele in samples:
        by_time.setdefault(_utc(t), (lon, lat, ele))
    times = sorted(by_time)
    if len(times) < 2:
        raise ValueError("The track has no timestamped points, so it can't be replayed")
    elevations = _fill_elevations(times, [by_time[t][2] for t in times])
    return [(t, *by_time[t][:2], ele) for t, ele in zip(times, elevations)]


def _utc(t: datetime) -> datetime:
    """Times should be UTC; treat ones without a zone as UTC."""
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _fill_elevations(times: list[datetime], elevations: list[float | None]) -> list[float]:
    """Interpolate missing elevations in time; copy the nearest value at the ends."""
    known = [i for i, e in enumerate(elevations) if e is not None]
    if not known:
        raise ValueError("The track has no elevation data, so it can't be shown in 3D")
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
