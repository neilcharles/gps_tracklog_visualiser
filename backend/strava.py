"""Your own Strava activities via your strava.com login cookie (local use only).

Strava's official API needs a paid subscription to register an app, so this
uses the same pages strava.com's own training log uses, signed in with the
`_strava4_session` cookie copied from your browser. It is unofficial (and
against Strava's terms), so it may break; it is off unless STRAVA_SESSION is
set, and only fetches what you click on.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://www.strava.com"
REQUEST_TIMEOUT_S = 30
PER_PAGE = 20
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) tracklog-viewer/0.1"
SESSION_COOKIE = "_strava4_session"
EXPIRED = f"Strava session expired: copy a fresh {SESSION_COOKIE} value into .env as STRAVA_SESSION"


class StravaError(Exception):
    """Strava could not be reached or returned something unusable."""


class StravaAuthError(StravaError):
    """The login cookie is missing, malformed or no longer accepted."""


def session_cookies() -> dict[str, str] | None:
    """Cookies from STRAVA_SESSION: a bare _strava4_session value, or a whole
    Cookie header ("a=1; b=2") copied from the browser. None if not set."""
    value = os.environ.get("STRAVA_SESSION", "").strip()
    if not value:
        return None
    if "=" not in value:
        return {SESSION_COOKIE: value}
    pairs = (part.strip().split("=", 1) for part in value.removeprefix("Cookie:").split(";"))
    return {name.strip(): v.strip() for name, v in (p for p in pairs if len(p) == 2) if name.strip()}


def is_configured() -> bool:
    return session_cookies() is not None


def parse_activity_list(data: dict, page: int) -> dict:
    """Trim the training-log JSON to what the activity picker shows."""
    models = data.get("models")
    if not isinstance(models, list):
        raise StravaError("Unexpected reply from Strava's activity list")
    activities = []
    for m in models:
        if not isinstance(m, dict) or "id" not in m:
            continue
        if m.get("trainer") or m.get("has_latlng") is False:  # no GPS track
            continue
        sport = m.get("sport_type") or m.get("type") or ""
        activities.append({
            "id": m["id"],
            "name": m.get("name") or "Untitled activity",
            "sport": m.get("display_type") or sport,
            "start": m.get("start_time") or m.get("start_date"),
            "distance_m": m.get("distance_raw", m.get("distance")),
            "duration_s": m.get("elapsed_time_raw", m.get("elapsed_time")),
        })
    total = data.get("total")
    per_page = data.get("perPage") or PER_PAGE
    more = page * per_page < total if isinstance(total, int) else len(models) >= per_page
    return {"activities": activities, "page": page, "more": more}


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Strava sends signed-out requests to its login page.
        if urllib.parse.urlparse(newurl).path.rstrip("/") in ("/login", "/session", "/onboarding"):
            raise StravaAuthError(EXPIRED)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def cookie_jar(cookies: dict[str, str]) -> http.cookiejar.CookieJar:
    """A jar holding the cookies for strava.com only, so they aren't sent on to
    the file storage that exports redirect to. It also keeps any session value
    Strava rotates in Set-Cookie."""
    jar = http.cookiejar.CookieJar()
    for name, value in cookies.items():
        jar.set_cookie(http.cookiejar.Cookie(
            0, name, value, None, False, ".strava.com", True, True, "/", True, True,
            None, False, None, None, {},
        ))
    return jar


_session: tuple[dict, urllib.request.OpenerDirector] | None = None  # (cookies, opener using them)


def _opener() -> urllib.request.OpenerDirector:
    global _session
    cookies = session_cookies()
    if cookies is None:
        raise StravaAuthError("STRAVA_SESSION isn't set")
    if _session is None or _session[0] != cookies:
        _session = (cookies, urllib.request.build_opener(
            _RedirectHandler, urllib.request.HTTPCookieProcessor(cookie_jar(cookies))))
    return _session[1]


def _get(path: str, max_bytes: int, accept: str, xhr: bool = False) -> bytes:
    opener = _opener()
    req = urllib.request.Request(BASE_URL + path, headers={"User-Agent": USER_AGENT, "Accept": accept})
    if xhr:
        req.add_unredirected_header("X-Requested-With", "XMLHttpRequest")
    try:
        with opener.open(req, timeout=REQUEST_TIMEOUT_S) as res:
            data = res.read(max_bytes + 1)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise StravaAuthError(EXPIRED) from None
        if e.code == 503:  # what Strava sends for a malformed session cookie
            raise StravaAuthError(f"Strava rejected the session cookie (or is down). {EXPIRED}") from None
        if e.code == 404:
            raise StravaError("Strava doesn't have that activity (or it isn't yours)") from None
        raise StravaError(f"Strava replied {e.code}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise StravaError(f"Couldn't reach Strava: {getattr(e, 'reason', e)}") from None
    if len(data) > max_bytes:
        raise StravaError("Strava's file is too large")
    return data


def list_activities(page: int = 1, keywords: str = "") -> dict:
    query = urllib.parse.urlencode({
        "keywords": keywords, "order": "start_date_local DESC", "page": page, "per_page": PER_PAGE,
    })
    body = _get(f"/athlete/training_activities?{query}", 5 * 1024 * 1024, "application/json, text/javascript", xhr=True)
    try:
        data = json.loads(body)
    except ValueError:
        # An HTML page instead of JSON is how a signed-out request often ends up.
        raise StravaAuthError(EXPIRED) from None
    if not isinstance(data, dict):
        raise StravaError("Unexpected reply from Strava's activity list")
    return parse_activity_list(data, page)


def download_track(activity_id: int, fmt: str, max_bytes: int) -> bytes:
    """The activity's file: fmt "original" (as uploaded: FIT, GPX, TCX…) or "gpx"."""
    data = _get(f"/activities/{activity_id}/export_{fmt}", max_bytes, "*/*")
    if data.lstrip()[:20].lower().startswith((b"<!doctype html", b"<html")):  # the sign-in page
        raise StravaAuthError(EXPIRED)
    return data
