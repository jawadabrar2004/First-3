# Response Dashboard

This repo has two parts:

1. **Drone dispatch console** (Python, below): the 911 dispatcher screen for the emergency-response drone. Runs on mock data, no drone needed.
2. **Call page** (Node.js, further down): the first-page call answer flow.

---

## Drone dispatch console

A browser-based 911 dispatcher console: live drone video, telemetry, map, call transcript, key info pulled from the call, and drone controls (push-to-talk, payload drop, return to home).

Everything is mocked: the drone flies from a base to the University of Hartford, hovers, and comes home, while a scripted 911 call plays in the transcript. Your laptop webcam stands in for the drone camera.

### Setup (once)

You need **Python 3.10 or newer** ([python.org](https://www.python.org/downloads/)).

**Windows (PowerShell):**

```powershell
cd First-3
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell says running scripts is disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use Command Prompt and `.venv\Scripts\activate.bat`.

**Mac (Terminal):**

```bash
cd First-3
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run

With the venv activated (you'll see `(.venv)` in your prompt):

```
python -m uvicorn main:app --reload
```

Open **http://localhost:8000**. Allow camera and microphone access when the browser asks. Press **Ctrl+C** to stop.

`--reload` restarts the server whenever you save a Python file. **Restart demo** in the header starts the flight and call over.

### Demo walkthrough

1. The call starts and the drone takes off. Key Info fills in as the caller gives the address, situation and phone number.
2. When the drone reaches the scene (about 2 minutes), **Drop payload** turns on. Click it, then **Confirm drop**.
3. Hold **Hold to talk** (or focus it and hold Space) to record a message; release to send it. Clips are saved in `recordings/`.
4. **Return to home** sends the drone back to base.

### Swapping in real parts later

| To change | Edit | What to do |
|---|---|---|
| Video source | `static/config.js` | Set `VIDEO_SOURCE` to `mjpeg` (Pi / ESP32-CAM), `webrtc` (MediaMTX on the Pi) or `file`, with its `url`. Nothing else changes. |
| Real drone | `drone_interface.py` | Fill in `RealDrone` with pymavlink (same methods as `MockDrone`), then start with `DRONE_MODE=real`. |
| Speech-to-text | `transcriber.py` | Write a class with the same `poll()` and `reset()` as `MockTranscriber`, then use it in `main.py`. |
| Key info with an LLM | `key_info.py` | Fill in `LLMExtractor.extract()`, then use it in `main.py` instead of `KeywordExtractor`. Keep API keys in `.env` (it's git-ignored). |

### How it fits together

```
browser  <── WebSocket /ws (telemetry, transcript, key info) ──  main.py (FastAPI)
browser  ── POST /api/drop, /api/rth, /api/talk ──────────────>    │
                                                                   ├─ drone_interface.py  MockDrone / RealDrone
                                                                   ├─ transcriber.py      MockTranscriber
                                                                   └─ key_info.py         KeywordExtractor
```

### Files

    main.py              Web server: serves static/, runs the simulation loop, WebSocket + API endpoints
    drone_interface.py   All drone I/O: MockDrone (simulator) and RealDrone (MAVLink, to do)
    transcriber.py       MockTranscriber: the scripted 911 call
    key_info.py          Pulls address / emergency / patient status / callback number from the transcript
    requirements.txt     Python packages
    static/index.html    The console page
    static/style.css     Console styles (Midnight Command theme)
    static/config.js     VIDEO_SOURCE: where the drone video comes from
    static/app.js        WebSocket connection, header, transcript, key info
    static/video.js      Builds the video element for each VIDEO_SOURCE type
    static/telemetry.js  Telemetry tiles
    static/map.js        Leaflet map
    static/controls.js   Push-to-talk, payload drop, return to home

---

## Call page (Node.js)

An emergency response dashboard, built the same way as Doorstep: plain HTML, CSS and JavaScript plus a small Node.js server (`server.js`). No build step, no npm install.

## The page

1. **First 3 minutes changes lives** at the top.
2. **Answer** button. Clicking it shows the caller's phone number and, under **Location**, the latitude and longitude.
3. The responder then chooses **Drone 1**, **Drone 2** or **Drone 3** (one at a time; clicking another switches).
4. **Notes** on the right (under the call on a phone): a box the dispatcher types into during the call.

The call is demo data for now: `CALL` at the top of `js/call.js`. Notes are not saved yet. Reload the page to start over.

## Working on it together

1. Get a copy: `git clone <repo link>`, then `cd` into the folder.
2. Make a branch for your change: `git checkout -b my-change`.
3. Run it with `node server.js` and open http://localhost:4000.
4. Commit, push the branch (`git push -u origin my-change`) and open a pull request on GitHub.

Pull first (`git pull`) before you start, so you're working on the latest version.

## Run it

- **Mac:** double-click `start-mac.command` (the first time, right-click it and choose **Open**)
- **Windows:** double-click `start-windows.bat`
- **From a terminal:** run `node server.js` in this folder

Then open **http://localhost:4000**. It uses port 4000, so it can run at the same time as Doorstep (port 3000). Press **Ctrl+C** to stop it.

## Theme: Midnight Command

All colours are tokens at the top of `css/styles.css`. Each one has a single job:

| Token | Colour | Job |
|---|---|---|
| `--bg` | `#0B1220` | Page background |
| `--panel` | `#152238` | Panels |
| `--text` | `#F1F5F9` | Main text |
| `--muted` | `#94A3B8` | Secondary info; offline / unknown (always with a label) |
| `--accent` | `#22D3EE` | Selected item, active navigation, primary controls |
| `--critical` | `#F87171` | Critical alerts only |
| `--warning` | `#FBBF24` | Warnings, needs review |
| `--ok` | `#34D399` | Normal, available |

Rules that keep it readable:
- Status colours always come with a word, and Critical also gets an icon. Never colour alone.
- Timers, coordinates and counts use the monospace font (`.mono`), so changing numbers don't shift.
- Thin borders, 6–10 px corners, no flashing or glowing effects.

## Structure
    index.html          The call page (first page): Answer, call details, drones, notes
    server.js           Serves the site on port 4000
    css/styles.css      Theme tokens and the call page styles
    js/call.js          Answer button, caller details, drone choice (demo call data at the top)
    assets/favicon.svg  Tab icon
    pages/              Further pages go here
