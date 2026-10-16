import os
import zlib
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from backend.fit import is_fit, parse_fit
from backend.gpx import parse_gpx
from backend.igc import decode_igc, parse_igc
from backend.places import PlacesError, fetch_places
from backend.strava import StravaAuthError, StravaError, download_track, is_configured, list_activities
from backend.tcx import is_tcx, parse_tcx

ROOT = Path(__file__).resolve().parent.parent
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_UNZIPPED_BYTES = 100 * 1024 * 1024  # stops a small .gz unpacking to fill memory

app = FastAPI(title="Tracklog Viewer")


# Not /healthz: Cloud Run reserves some paths ending in "z".
@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/config")
def config() -> dict:
    return {
        "cesium_ion_token": os.environ.get("CESIUM_ION_TOKEN"),
        # Preferred over Cesium ion for terrain and imagery when set.
        "maptiler_key": os.environ.get("MAPTILER_KEY"),
        "strava": is_configured(),
    }


@app.get("/api/places")
def places(south: float, west: float, north: float, east: float) -> dict:
    try:
        return {"places": fetch_places(south, west, north, east)}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except PlacesError as e:
        raise HTTPException(502, str(e))


@app.post("/api/flights/upload")
async def upload_flight(file: UploadFile) -> dict:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    return parse_tracklog(data)


def _strava_call(fn, *args):
    if not is_configured():
        raise HTTPException(404, "Strava isn't set up: add STRAVA_SESSION to .env")
    try:
        return fn(*args)
    except StravaAuthError as e:
        raise HTTPException(401, str(e))
    except StravaError as e:
        raise HTTPException(502, str(e))


@app.get("/api/strava/activities")
def strava_activities(page: int = 1, q: str = "") -> dict:
    return _strava_call(list_activities, max(page, 1), q)


@app.get("/api/strava/activities/{activity_id}/track")
def strava_track(activity_id: int) -> dict:
    # The original upload (often FIT) has the most detail; Strava's own GPX
    # export is the fallback when the original is missing or unreadable.
    try:
        return parse_tracklog(_strava_call(download_track, activity_id, "original", MAX_UPLOAD_BYTES))
    except HTTPException as e:
        if e.status_code == 401:
            raise
    return parse_tracklog(_strava_call(download_track, activity_id, "gpx", MAX_UPLOAD_BYTES))


def parse_tracklog(data: bytes) -> dict:
    """Parse an IGC, GPX, FIT or TCX file, optionally gzipped, told apart by content."""
    if data.startswith(b"\x1f\x8b"):  # gzip, as in Strava's bulk export (.fit.gz, .gpx.gz, .tcx.gz)
        data = _gunzip(data)
    try:
        if is_fit(data):
            return parse_fit(data)
        if data.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):  # XML: GPX or TCX
            return parse_tcx(data) if is_tcx(data) else parse_gpx(data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    flight = parse_igc(decode_igc(data))
    if not flight.fixes:
        raise HTTPException(422, "No valid track points found; is this an IGC, GPX, FIT or TCX file?")
    return flight.to_geojson()


def _gunzip(data: bytes) -> bytes:
    unzip = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)  # 16+: expect a gzip header
    try:
        out = unzip.decompress(data, MAX_UNZIPPED_BYTES)
    except zlib.error:
        raise HTTPException(422, "Not a valid .gz file") from None
    if unzip.unconsumed_tail or len(out) >= MAX_UNZIPPED_BYTES:
        raise HTTPException(413, "File too large once unzipped")
    if not unzip.eof:
        raise HTTPException(422, "The .gz file is incomplete (cut short while downloading?)")
    return out


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
