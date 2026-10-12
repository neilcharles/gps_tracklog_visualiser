"""Place names (cities, towns, villages, hamlets) from OpenStreetMap via Overpass."""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache

# The public Overpass servers are sometimes overloaded (504s from the main
# server, 500s from mirrors); try the main server twice, then community
# mirrors, pausing longer before each attempt.
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
RETRY_DELAYS_S = (0, 2, 4, 8)  # pause before each attempt in OVERPASS_URLS
REQUEST_TIMEOUT_S = 15
USER_AGENT = "paragliding-analysis/0.1 (flight replay place labels)"
PLACE_TYPES = ("city", "town", "village", "hamlet")
MAX_BBOX_DEGREES = 3.0
CACHE_GRID_DEGREES = 0.1


class PlacesError(Exception):
    """Overpass could not be reached or returned something unusable."""


def validate_bbox(south: float, west: float, north: float, east: float) -> None:
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise ValueError("Bounding box must have south < north and west < east, within valid lat/lon ranges")
    if north - south > MAX_BBOX_DEGREES or east - west > MAX_BBOX_DEGREES:
        raise ValueError(f"Bounding box may be at most {MAX_BBOX_DEGREES}° on each side")


def parse_overpass(data: dict) -> list[dict]:
    places = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if el.get("type") != "node" or not name or "lat" not in el or "lon" not in el:
            continue
        places.append({
            "id": el["id"],
            "name": name,
            "type": tags.get("place"),
            "lat": el["lat"],
            "lon": el["lon"],
        })
    return places


def fetch_places(south: float, west: float, north: float, east: float) -> list[dict]:
    validate_bbox(south, west, north, east)
    # Snap outwards to a coarse grid so nearby requests share a cache entry.
    g, eps = CACHE_GRID_DEGREES, 1e-9  # eps stops float error pushing exact grid values into the next cell
    return _fetch_cached(
        round(math.floor(south / g + eps) * g, 6), round(math.floor(west / g + eps) * g, 6),
        round(math.ceil(north / g - eps) * g, 6), round(math.ceil(east / g - eps) * g, 6),
    )


@lru_cache(maxsize=256)
def _fetch_cached(south: float, west: float, north: float, east: float) -> list[dict]:
    query = (
        f'[out:json][timeout:25];'
        f'node["place"~"^({"|".join(PLACE_TYPES)})$"]["name"]({south},{west},{north},{east});'
        f'out body;'
    )
    body = urllib.parse.urlencode({"data": query}).encode()
    failures = []
    for url, delay in zip(OVERPASS_URLS, RETRY_DELAYS_S):
        time.sleep(delay)
        req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                return parse_overpass(json.load(resp))
        except (OSError, ValueError) as e:  # URLError/HTTPError/timeouts are OSErrors; bad JSON is ValueError
            failures.append(f"{urllib.parse.urlparse(url).hostname}: {_describe(e)}")
    raise PlacesError("OpenStreetMap place servers are busy (" + "; ".join(failures) + ")")


def _describe(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        return str(e.reason)
    if isinstance(e, TimeoutError):
        return "timed out"
    if isinstance(e, ValueError):
        return "bad response"
    return str(e) or type(e).__name__
