# Tracklog Viewer

View IGC and GPX tracklogs (paragliding flights, hike-and-fly, walks, rides) in 3D over
real terrain and satellite imagery, in your browser.

## Quick start

You need **Python 3.10 or newer** ([python.org](https://www.python.org/downloads/); on
Windows, tick *"Add python.exe to PATH"* in the installer) and a free map key (step 3).

**1. Download the code**

```bash
git clone https://github.com/neilcharles/gps_tracklog_visualiser.git
cd gps_tracklog_visualiser
```

(Or use **Code → Download ZIP** on GitHub, unzip it, and open a terminal in that folder.)

**2. Install the dependencies** into a virtual environment

| Windows (PowerShell)                          | Linux / macOS                              |
|-----------------------------------------------|--------------------------------------------|
| `py -m venv .venv`                            | `python3 -m venv .venv`                    |
| `.venv\Scripts\Activate.ps1`                  | `source .venv/bin/activate`                |
| `python -m pip install -r requirements.txt`   | `python -m pip install -r requirements.txt` |

If PowerShell refuses to run `Activate.ps1`, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

**3. Add your map key**

Copy `.env.example` to `.env` (or skip this: the first run creates it for you), open it in a
text editor and fill in **one** of the keys:

```ini
MAPTILER_KEY=your-maptiler-key
```

See [Choosing a map key](#choosing-a-map-key) below for where to get one.

**4. Run it**

```bash
python run.py
```

Your browser opens at <http://localhost:8000>. Drag tracklogs onto the page to add them.
Press `Ctrl+C` in the terminal to stop.

Next time, you only need to activate the virtual environment (step 2, second line) and run
`python run.py`. Options: `--port 9000` to use another port, `--no-browser` to not open a tab.

## Choosing a map key

The key only controls where terrain and imagery come from. If both are set, MapTiler is used;
with neither, the map is flat.

| | **MapTiler** (default) | **Cesium ion** |
|---|---|---|
| Get a key | [cloud.maptiler.com/account/keys](https://cloud.maptiler.com/account/keys/) | [ion.cesium.com/tokens](https://ion.cesium.com/tokens) |
| `.env` setting | `MAPTILER_KEY=` | `CESIUM_ION_TOKEN=` |
| Quality | Slightly lower | Higher |
| Free usage | More generous: 100k tiles a month, then pauses until next month (no charges) | Lower allowance |
| Where to use it | Locally or deployed | **Locally only.** The free tier is for personal, non-commercial use, so don't use it on a public server |

If you restrict your MapTiler key to certain websites (*Allowed HTTP origins*), add
`localhost` to the list or the map will stay flat.

## Troubleshooting

- **"Dependencies aren't installed"**: the virtual environment isn't active, or step 2 was
  skipped. Activate it and run the `pip install` line again.
- **Flat map, no terrain**: no key was found. `run.py` says which map provider it's using when
  it starts. Check that the key is in `.env` (not `.env.example`), then restart.
- **Port already in use**: `python run.py --port 9000`.

## Development and deployment

```bash
python -m pip install -r requirements-dev.txt
pytest
```

To deploy to Google Cloud Run, see [DEPLOY.md](DEPLOY.md).
