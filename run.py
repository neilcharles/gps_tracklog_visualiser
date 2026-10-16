"""Start Tracklog Viewer locally.

    python run.py                # http://localhost:8000, opens your browser
    python run.py --port 9000
    python run.py --no-browser

Map keys are read from a `.env` file next to this script (see `.env.example`).
Environment variables that are already set take precedence over `.env`.
"""

import argparse
import os
import shutil
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


def load_env_file(path: Path) -> None:
    """Copy KEY=value lines from `path` into os.environ, skipping blanks and comments."""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip().strip("\"'")
        if value and name not in os.environ:
            os.environ[name] = value


def report_map_provider() -> None:
    if os.environ.get("MAPTILER_KEY"):
        print("Map: MapTiler terrain and satellite imagery.")
    elif os.environ.get("CESIUM_ION_TOKEN"):
        print("Map: Cesium ion terrain and imagery.")
    else:
        print("Map: no key found, so the map will be flat (no terrain).")
        print(f"     Add MAPTILER_KEY or CESIUM_ION_TOKEN to {ENV_FILE} and restart.")


def report_strava() -> None:
    if os.environ.get("STRAVA_SESSION", "").strip():
        print("Strava: activity browser on (using your strava.com session cookie).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Tracklog Viewer locally.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        sys.exit(
            "Dependencies aren't installed. From this folder run:\n"
            "    python -m pip install -r requirements.txt\n"
            "(inside your virtual environment, if you made one), then try again."
        )

    if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
        shutil.copy(ENV_EXAMPLE, ENV_FILE)
        print(f"Created {ENV_FILE.name} from {ENV_EXAMPLE.name}; put your map key in it.")
    if ENV_FILE.exists():
        load_env_file(ENV_FILE)
    report_map_provider()
    report_strava()

    url = f"http://localhost:{args.port}"
    print(f"\nOpen {url} in your browser. Press Ctrl+C to stop.\n")
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [url]).start()

    os.chdir(ROOT)
    uvicorn.run("backend.app:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
