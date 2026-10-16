"""Build small FIT files for tests, following the FIT protocol (header, definition and data
messages, CRCs), since there's no FIT writer among the dependencies."""

import struct
from datetime import datetime, timezone

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)
CRC_TABLE = (0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
             0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400)
RECORD = 20  # global message number of "record"
# (field number, size, base type): timestamp uint32, position_lat/long sint32, altitude uint16
FIELDS = ((253, 4, 0x86), (0, 4, 0x85), (1, 4, 0x85), (2, 2, 0x84))
NO_POSITION = 0x7FFFFFFF  # FIT's "invalid" sint32
NO_ALTITUDE = 0xFFFF  # FIT's "invalid" uint16


def crc(data: bytes, value: int = 0) -> int:
    for byte in data:
        for nibble in (byte & 0xF, byte >> 4):
            tmp = CRC_TABLE[value & 0xF]
            value = ((value >> 4) & 0x0FFF) ^ tmp ^ CRC_TABLE[nibble]
    return value


def fit_file(records: list[tuple[datetime, float | None, float | None, float | None]]) -> bytes:
    """A FIT file of record messages, each (UTC time, lat, lon, altitude in m); None for missing."""
    body = struct.pack("<BBBHB", 0x40, 0, 0, RECORD, len(FIELDS))
    body += b"".join(struct.pack("<BBB", *f) for f in FIELDS)
    for t, lat, lon, alt in records:
        def semicircles(deg):
            return NO_POSITION if deg is None else round(deg * 2**31 / 180)
        body += struct.pack(
            "<BIiiH", 0, int((t - FIT_EPOCH).total_seconds()), semicircles(lat), semicircles(lon),
            NO_ALTITUDE if alt is None else round((alt + 500) * 5),  # altitude: scale 5, offset 500 m
        )
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(body), b".FIT")
    header += struct.pack("<H", crc(header))
    return header + body + struct.pack("<H", crc(header + body))
