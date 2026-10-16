import io
import json
import urllib.error
import urllib.request

import pytest

from backend import strava
from backend.strava import StravaAuthError, StravaError, cookie_jar, parse_activity_list, session_cookies


@pytest.mark.parametrize("value, cookies", [
    ("abc123", {"_strava4_session": "abc123"}),
    ("  abc123\n", {"_strava4_session": "abc123"}),
    ("Cookie: _strava4_session=abc; _currentH=d3d3; x=a=b", {"_strava4_session": "abc", "_currentH": "d3d3", "x": "a=b"}),
])
def test_session_cookies(monkeypatch, value, cookies):
    monkeypatch.setenv("STRAVA_SESSION", value)
    assert session_cookies() == cookies


def test_not_configured(monkeypatch):
    monkeypatch.setenv("STRAVA_SESSION", " ")
    assert session_cookies() is None and not strava.is_configured()


def test_cookie_only_sent_to_strava():
    jar = cookie_jar({"_strava4_session": "abc"})
    to_strava = urllib.request.Request("https://www.strava.com/athlete/training_activities")
    to_storage = urllib.request.Request("https://strava-uploads.s3.amazonaws.com/123.fit?sig=x")
    jar.add_cookie_header(to_strava)
    jar.add_cookie_header(to_storage)
    assert to_strava.get_header("Cookie") == "_strava4_session=abc"
    assert not to_storage.has_header("Cookie")


SAMPLE = {
    "models": [
        {"id": 1, "name": "Rock climbing", "sport_type": "RockClimbing", "has_latlng": False},
        {"id": 2, "name": "Hike and fly", "type": "Hike", "display_type": "Hike",
         "start_time": "2025-06-01T09:00:00+0000", "distance_raw": 12345.6, "elapsed_time_raw": 5400},
        {"id": 3, "name": "Turbo", "type": "Ride", "trainer": True},
        {"id": 4, "type": "Run"},
    ],
    "page": 1, "perPage": 20, "total": 45,
}


def test_parse_activity_list():
    result = parse_activity_list(SAMPLE, 1)
    assert result["more"] is True
    assert result["activities"] == [
        {"id": 2, "name": "Hike and fly", "sport": "Hike", "start": "2025-06-01T09:00:00+0000",
         "distance_m": 12345.6, "duration_s": 5400},
        {"id": 4, "name": "Untitled activity", "sport": "Run", "start": None, "distance_m": None, "duration_s": None},
    ]
    assert parse_activity_list(SAMPLE, 3)["more"] is False


def test_parse_activity_list_rejects_unexpected():
    with pytest.raises(StravaError):
        parse_activity_list({"error": "nope"}, 1)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setenv("STRAVA_SESSION", "abc123")
    requests = []

    def use(reply):
        def open_(req, timeout):
            requests.append(req)
            if isinstance(reply, Exception):
                raise reply
            return FakeResponse(reply)
        monkeypatch.setattr(strava._opener(), "open", open_)
        return requests
    return use


def test_list_activities_request(signed_in):
    requests = signed_in(json.dumps(SAMPLE).encode())
    assert [a["id"] for a in strava.list_activities(2, "fly")["activities"]] == [2, 4]
    req = requests[0]
    assert "page=2" in req.full_url and "keywords=fly" in req.full_url
    assert req.get_header("X-requested-with") == "XMLHttpRequest"


def test_html_reply_means_signed_out(signed_in):
    signed_in(b"<!DOCTYPE html><html>Log in</html>")
    with pytest.raises(StravaAuthError):
        strava.list_activities()
    with pytest.raises(StravaAuthError):
        strava.download_track(1, "gpx", 1000)


@pytest.mark.parametrize("code, error", [(401, StravaAuthError), (503, StravaAuthError), (404, StravaError), (500, StravaError)])
def test_http_errors(signed_in, code, error):
    signed_in(urllib.error.HTTPError("https://www.strava.com/x", code, "", {}, None))
    with pytest.raises(error):
        strava.download_track(1, "original", 1000)


def test_download_too_large(signed_in):
    signed_in(b"x" * 11)
    with pytest.raises(StravaError, match="too large"):
        strava.download_track(1, "original", 10)


def test_login_redirect_is_auth_error():
    handler = strava._RedirectHandler()
    with pytest.raises(StravaAuthError):
        handler.redirect_request(None, None, 302, "Found", {}, "https://www.strava.com/login")
