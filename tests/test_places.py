import json
import urllib.error

import pytest

from backend.places import parse_overpass, validate_bbox

SAMPLE = {
    "elements": [
        {"type": "node", "id": 1, "lat": 51.40, "lon": -1.32, "tags": {"place": "town", "name": "Newbury"}},
        {"type": "node", "id": 2, "lat": 51.35, "lon": -1.48, "tags": {"place": "hamlet"}},  # no name
        {"type": "way", "id": 3, "tags": {"place": "village", "name": "Not a node"}},
        {"type": "node", "id": 4, "lat": 51.42, "lon": -1.52, "tags": {"place": "village", "name": "Inkpen"}},
    ]
}


def test_parse_overpass():
    assert parse_overpass(SAMPLE) == [
        {"id": 1, "name": "Newbury", "type": "town", "lat": 51.40, "lon": -1.32},
        {"id": 4, "name": "Inkpen", "type": "village", "lat": 51.42, "lon": -1.52},
    ]


def test_parse_overpass_empty():
    assert parse_overpass({}) == []


def test_validate_bbox_ok():
    validate_bbox(51.2, -2.3, 51.6, -1.2)


@pytest.mark.parametrize("bbox", [
    (51.6, -2.3, 51.2, -1.2),   # south > north
    (51.2, -1.2, 51.6, -2.3),   # west > east
    (50.0, -6.0, 51.0, -0.5),   # too wide
    (-95.0, 0.0, -89.0, 1.0),   # out of range
])
def test_validate_bbox_rejects(bbox):
    with pytest.raises(ValueError):
        validate_bbox(*bbox)


def test_fetch_places_snaps_to_shared_cache_cell(monkeypatch):
    import backend.places as places
    calls = []
    monkeypatch.setattr(places, "_fetch_cached", lambda *bbox: calls.append(bbox) or [])
    places.fetch_places(51.2, -2.3, 51.6, -1.2)
    places.fetch_places(51.25, -2.25, 51.55, -1.25)
    assert calls == [(51.2, -2.3, 51.6, -1.2)] * 2


class _FakeResponse:
    def __init__(self, data):
        self._data = json.dumps(data).encode()

    def read(self, *args):
        data, self._data = self._data, b""
        return data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "error", {}, None)


def test_overpass_falls_through_to_next_server(monkeypatch):
    import backend.places as places
    attempts = []

    def fake_urlopen(req, timeout):
        attempts.append(req.full_url)
        if len(attempts) < 3:
            raise _http_error(req.full_url, 504)
        return _FakeResponse(SAMPLE)

    sleeps = []
    monkeypatch.setattr(places.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(places.time, "sleep", sleeps.append)
    result = places._fetch_cached.__wrapped__(51.0, -2.0, 51.5, -1.5)
    assert [p["name"] for p in result] == ["Newbury", "Inkpen"]
    assert attempts == list(places.OVERPASS_URLS[:3])
    assert sleeps == list(places.RETRY_DELAYS_S[:3])


def test_overpass_error_lists_every_attempt(monkeypatch):
    import backend.places as places
    codes = iter([504, 504, 500, 500])
    monkeypatch.setattr(places.urllib.request, "urlopen",
                        lambda req, timeout: (_ for _ in ()).throw(_http_error(req.full_url, next(codes))))
    monkeypatch.setattr(places.time, "sleep", lambda s: None)
    with pytest.raises(places.PlacesError) as exc:
        places._fetch_cached.__wrapped__(51.0, -2.0, 51.5, -1.5)
    msg = str(exc.value)
    assert msg.count("overpass-api.de: HTTP 504") == 2
    assert "overpass.kumi.systems: HTTP 500" in msg
    assert "overpass.private.coffee: HTTP 500" in msg
