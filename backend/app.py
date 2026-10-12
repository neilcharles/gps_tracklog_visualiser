import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from backend.igc import decode_igc, parse_igc
from backend.places import PlacesError, fetch_places

ROOT = Path(__file__).resolve().parent.parent
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

app = FastAPI(title="Paragliding Analysis")


# Not /healthz: Cloud Run reserves some paths ending in "z".
@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/config")
def config() -> dict:
    return {"cesium_ion_token": os.environ.get("CESIUM_ION_TOKEN")}


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
    flight = parse_igc(decode_igc(data))
    if not flight.fixes:
        raise HTTPException(422, "No valid B-record fixes found; is this an IGC file?")
    return flight.to_geojson()


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
