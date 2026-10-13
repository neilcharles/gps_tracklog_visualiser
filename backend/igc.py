"""Parser for IGC flight recorder files.

Follows the FAI/IGC "Technical Specification for IGC-approved GNSS Flight
Recorders", Appendix A. Byte positions in comments are 1-based, as in the spec.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend.tracks import track_feature

# B record fixed fields occupy bytes 1-35; extensions start at byte 36.
_B_FIXED_LEN = 35
_DTE_RE = re.compile(r"(\d{6})")


@dataclass
class Fix:
    time: datetime  # UTC
    lat: float
    lon: float
    valid: bool  # True for a 3D fix ("A"), False for 2D / no fix ("V")
    pressure_alt: int  # metres, ISA 1013.25 hPa datum
    gnss_alt: int  # metres above WGS84 ellipsoid
    extensions: dict[str, int | str] = field(default_factory=dict)


@dataclass
class Waypoint:
    lat: float
    lon: float
    name: str


@dataclass
class Event:
    time: datetime
    code: str
    text: str


@dataclass
class Flight:
    date: date | None
    headers: dict[str, str]
    fixes: list[Fix]
    task: list[Waypoint]
    events: list[Event]
    logger_id: str = ""

    @property
    def pilot(self) -> str | None:
        return self.headers.get("PLT")

    @property
    def glider(self) -> str | None:
        return self.headers.get("GTY")

    def to_geojson(self) -> dict:
        points = [(f.time, f.lon, f.lat, _altitude(f)) for f in self.fixes]
        return track_feature(points, self.pilot, self.glider, self.date)


def _altitude(fix: Fix) -> int:
    """GNSS altitude when available, otherwise pressure altitude."""
    return fix.gnss_alt if fix.gnss_alt else fix.pressure_alt


def _parse_coord(digits: str, hemi: str) -> float:
    """Decode DDMMmmm / DDDMMmmm plus hemisphere letter to signed decimal degrees."""
    deg = int(digits[:-5])
    milli_minutes = int(digits[-5:])
    value = deg + milli_minutes / 60000
    return -value if hemi in "SW" else value


def _parse_time(hhmmss: str) -> tuple[int, int, int]:
    return int(hhmmss[0:2]), int(hhmmss[2:4]), int(hhmmss[4:6])


def _parse_int(s: str) -> int | str:
    try:
        return int(s)
    except ValueError:
        return s


def _parse_date(value: str) -> date | None:
    # Old style "HFDTE070826", new style "HFDTEDATE:070826,01".
    m = _DTE_RE.search(value)
    if not m:
        return None
    dd, mm, yy = int(m[1][0:2]), int(m[1][2:4]), int(m[1][4:6])
    # IGC uses 2-digit years; assume 1980-2079.
    year = 2000 + yy if yy < 80 else 1900 + yy
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def _parse_header(line: str, headers: dict[str, str]) -> None:
    code = line[2:5]
    rest = line[5:]
    # Long name before ":" is only a human-readable label; the value follows it.
    value = rest.split(":", 1)[1] if ":" in rest else rest
    headers.setdefault(code, value.strip())


def _parse_extensions(line: str) -> list[tuple[int, int, str]]:
    count = int(line[1:3])
    exts = []
    for i in range(count):
        chunk = line[3 + i * 7 : 10 + i * 7]
        if len(chunk) < 7:
            break
        exts.append((int(chunk[0:2]), int(chunk[2:4]), chunk[4:7]))
    return exts


class _Clock:
    """Turns successive HHMMSS stamps into datetimes, rolling over at UTC midnight."""

    def __init__(self) -> None:
        self.day: date | None = None
        self.last: datetime | None = None

    def __call__(self, hhmmss: str) -> datetime:
        h, m, s = _parse_time(hhmmss)
        base = self.day or date(1970, 1, 1)
        t = datetime(base.year, base.month, base.day, h, m, s, tzinfo=timezone.utc)
        if self.last is not None:
            while t < self.last - timedelta(hours=12):
                t += timedelta(days=1)
        self.last = t
        return t


def parse_igc(text: str) -> Flight:
    headers: dict[str, str] = {}
    extensions: list[tuple[int, int, str]] = []
    fixes: list[Fix] = []
    task: list[Waypoint] = []
    events: list[Event] = []
    logger_id = ""
    flight_date: date | None = None
    clock = _Clock()
    seen_task_header = False

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        kind = line[0]

        if kind == "B":
            if len(line) < _B_FIXED_LEN:
                continue
            try:
                fix = Fix(
                    time=clock(line[1:7]),
                    lat=_parse_coord(line[7:14], line[14]),
                    lon=_parse_coord(line[15:23], line[23]),
                    valid=line[24] == "A",
                    pressure_alt=int(line[25:30]),
                    gnss_alt=int(line[30:35]),
                )
            except ValueError:
                continue
            for start, end, code in extensions:
                chunk = line[start - 1 : end]
                if chunk:
                    fix.extensions[code] = _parse_int(chunk)
            fixes.append(fix)

        elif kind == "H":
            _parse_header(line, headers)
            if line[2:5] == "DTE" and flight_date is None:
                flight_date = _parse_date(line[5:])
                clock.day = flight_date

        elif kind == "I":
            extensions = _parse_extensions(line)

        elif kind == "C":
            # First C line is the declaration header; the rest are waypoints.
            if not seen_task_header:
                seen_task_header = True
                continue
            try:
                task.append(
                    Waypoint(
                        lat=_parse_coord(line[1:8], line[8]),
                        lon=_parse_coord(line[9:17], line[17]),
                        name=line[18:].strip(),
                    )
                )
            except (ValueError, IndexError):
                continue

        elif kind == "E":
            if len(line) >= 10:
                events.append(Event(time=clock(line[1:7]), code=line[7:10], text=line[10:].strip()))

        elif kind == "A":
            logger_id = line[1:7]

        # G (security), L (comments), J/K (low-rate data) are ignored.

    return Flight(
        date=flight_date,
        headers=headers,
        fixes=fixes,
        task=task,
        events=events,
        logger_id=logger_id,
    )


def decode_igc(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def load_igc(path: str | Path) -> Flight:
    return parse_igc(decode_igc(Path(path).read_bytes()))
