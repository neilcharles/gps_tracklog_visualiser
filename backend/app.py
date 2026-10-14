import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from backend.gpx import parse_gpx
from backend.igc import decode_igc, parse_igc
from backend.places import PlacesError, fetch_places

ROOT = Path(__file__).resolve().parent.parent
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

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


def parse_tracklog(data: bytes) -> dict:
    """Parse an IGC or GPX file, told apart by content: GPX is XML, IGC is plain text."""
    if data.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        try:
            return parse_gpx(data)
        except ValueError as e:
            raise HTTPException(422, str(e))
    flight = parse_igc(decode_igc(data))
    if not flight.fixes:
        raise HTTPException(422, "No valid track points found; is this an IGC or GPX file?")
    return flight.to_geojson()


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
