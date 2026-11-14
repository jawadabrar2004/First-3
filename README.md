# Response Dashboard

This repo has two parts:

1. **Drone dispatch console** (Python, below): the 911 dispatcher screen for the emergency-response drone. Runs on mock data, no drone needed.
2. **Call page** (Node.js, further down): the first-page call answer flow.

---

## Drone dispatch console

A full-screen 911 dispatcher console for a big wall display. It walks the dispatcher through one emergency:

1. **Incoming call:** press **Answer**.
2. **On the call:** the live transcript fills the screen. Type the address in the box below it, then pick the drone to send: **EpiPen**, **AED** or **Bleeding control kit**. The drone launches immediately.
3. **En route:** a big **ETA to search zone** countdown (10 seconds for the demo) with a **minimap** beside it: the caller's reported position, the **search zone** around it, the drone, its base and the flight path, plus a live **Distance to zone**.
4. **Search zone:** when the drone enters the zone, a banner says **ENTERING SEARCH ZONE - CAMERAS ACTIVE**, the cameras appear and **machine vision** starts looking for the person (see below).
5. **On scene:** the cameras fill the screen as **Feed 1** with almost nothing on them: just small drop-down boxes on the left edge: **Telemetry** (starts open), **Map** (open), **Alerts** (opens by itself on a new alert) and **Live call & status** (closed). Click a box's title bar (**Hide** / **Show**) to fold or unfold it, or press **T** for Telemetry. The machine vision **Scene** readout, **Drop payload**, **Record** and **Hold to talk** are in a thin bar under the cameras, and **Return to base** is in the header next to LIVE.

Everything is mocked: the scripted caller is one of three emergencies (allergic reaction, cardiac arrest, severe bleeding), picked at random for each call. Your laptop webcam stands in for the drone camera.

### Setup (once)

You need **Python 3.10 or newer** ([python.org](https://www.python.org/downloads/)). The install includes the machine vision packages (PyTorch via `ultralytics`), about **1 GB** of downloads, so give it a few minutes the first time.

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

Open **http://localhost:8000**. Allow microphone access (and camera access in mock mode) when the browser asks. Press **Ctrl+C** to stop.

`--reload` restarts the server whenever you save a Python file. **Restart demo** in the header starts a new call. Press **F11** for full screen on the big display.

### Demo tips

- The caller waits for you: after describing the emergency they pause until a drone is dispatched, then react when it arrives and when the payload lands.
- **Drop payload** needs a second click (**Confirm drop**) so it can't happen by accident.
- Hold **Hold to talk** (or focus it and hold Space) to record a message for the person giving aid; release to send it. Each clip adds a line to the status feed and is saved in `recordings/`.
- To change the 10-second ETA, edit `DEMO_ETA_SECONDS` in `drone_interface.py`.

### The search zone

A wireless 911 call doesn't give an exact spot: the phone network reports a point plus an **uncertainty radius** (here 75 m). That circle is the **search zone**: the person is somewhere inside it.

- The caller's reported point and the radius are set in one place: `CALLER_LOCATION` and `SEARCH_RADIUS_M` in `drone_interface.py`. (The mock person is really at `INCIDENT`, about 45 m from the reported point.)
- The server works out the drone's distance to that point every update and sends `distance_to_caller`, `distance_to_zone` and `in_search_zone` with the telemetry (the reported point and radius go to the page with the rest of the mission).
- The drone flies straight to the zone (the ETA counts down to the zone's edge). Inside it, the mock drone slows down and searches (status **Searching the zone**): it checks the reported point first, then finds the person and hovers (**On scene**, where **Drop payload** turns on).
- The cameras stay off until the drone is in the zone (the ETA screen shows a blurred placeholder). On entering, the camera feeds load **once** and the machine vision starts. They stay on until **Return to base** or **Restart demo**.

### Machine vision

The people/fire detection from `machine_vision/` (see [machine_vision/README.md](machine_vision/README.md)) runs automatically: `main.py` starts `machine_vision/monitor.py` when the drone enters the search zone, and stops it on **Return to base** (or an automatic return) and **Restart demo**. If it crashes while it should be running, it's restarted after 3 seconds. Everything it prints goes to `machine_vision/monitor.log`.

What the dispatcher sees:

- **Day camera:** with machine vision on, the Day pane shows the analysed video (boxes and alerts drawn in). The small **CV ON | RAW** switch next to DAY CAM flips back to the plain feed. The IR pane is unchanged.
- **Scene** (bottom bar): people in view, plus a badge for each alert that's active right now: person down, waving, choking, fire, fire with people.
- **Alerts** drop-down: each new incident with its time, type, a screenshot (click to enlarge) and **Confirm** / **Dismiss**. A short beep plays, the box opens, and a marker is dropped on the maps where the drone was. The system never acts on an alert by itself: the dispatcher decides, and the decision goes into the status feed.

What it watches:

| `VIDEO_MODE` | Machine vision reads | Notes |
|---|---|---|
| `"pi"` | `rtsp://PI_HOST:8554/cam` (the Pi's day camera, from MediaMTX) | Don't run `machine_vision/pi_camera_stream.sh`: MediaMTX already has the camera. |
| `"mock"` | `machine_vision/test_clip.mp4` | The browser already uses the webcam, so machine vision can't. Make the clip once with `python machine_vision/make_test_clip.py` (no download: it uses sample photos that come with `ultralytics`; triggers **Person down**). Any other `.mp4` works too: save it as `machine_vision/test_clip.mp4`, or set the `VISION_MOCK_SOURCE` environment variable to its path. |

Ports:

| Port | What |
|---|---|
| 8000 | The dispatch console (`main.py`) |
| 8100 | Machine vision (`monitor.py`): `/stream.mjpg` (analysed video), `/status.json` (people + alerts). Set by `VISION_PORT` in `static/config.js`. |
| 8889 / 8554 | MediaMTX on the Pi: WebRTC pages (`/cam`, `/ir`) and RTSP |

API (all on port 8000): `POST /api/vision/start`, `POST /api/vision/stop`, `GET /api/vision/status`, `GET /api/vision/incidents` (this mission's alerts; screenshots at `/api/vision/incidents/<image>`) and `POST /api/vision/incidents/<id>/confirm` or `/dismiss`. Incident screenshots are saved in `machine_vision/incidents/`, which is never committed (they can show faces).

### Raspberry Pi cameras (Day + IR)

The video panel shows the Pi 5's live cameras, streamed by MediaMTX. Setting up the Pi itself is covered in [pi/README.md](pi/README.md).

On the on-scene screen both cameras show **side by side**: **DAY CAM** on the left, **IR CAM** on the right (each labeled in its top-right corner). The **CAM** dot in the header is green when the Pi is reachable and red when it isn't. While the Pi is unreachable, both panes show **CAMERA OFFLINE - check Pi / Wi-Fi**, and it reconnects on its own when the Pi comes back (checked every 5 s).

**Pi or mock video:** in `static/config.js`, set

```js
const VIDEO_MODE = "pi";    // live Pi cameras; machine vision reads the Pi's day camera
const VIDEO_MODE = "mock";  // no Pi: laptop webcam in both panes (the IR pane in grey);
                            // machine vision reads machine_vision/test_clip.mp4
```

then reload the page. The server reads the same file, so machine vision follows automatically.

**Pointing at the Pi (`PI_HOST`):** the default is `raspberrypi.local`. On a phone hotspot that name can resolve to IPv6, where WebRTC may fail (the page loads but the video stays black). Use the Pi's IPv4 address instead (`hostname -I` on the Pi):

1. In `static/config.js`: `const PI_HOST = "172.20.10.14";`
2. Restart the server (`Ctrl+C`, then `python -m uvicorn main:app --reload`) and reload the page.

The page and the server both read `PI_HOST` from `config.js`, so that's the only place to change. (To override it on the server only, set the `PI_HOST` environment variable before starting it, e.g. PowerShell `$env:PI_HOST = "172.20.10.14"`. The same works for `VIDEO_MODE`.)

The RTSP streams for computer vision are `rtsp://PI_HOST:8554/cam` and `rtsp://PI_HOST:8554/ir` (also listed as `PI_STREAMS.dayRtsp` / `irRtsp` in `config.js`).

### Swapping in real parts later

| To change | Edit | What to do |
|---|---|---|
| Video source | `static/config.js` | `VIDEO_MODE = "pi"` for the Pi cameras (see above). In mock mode, `VIDEO_SOURCE` can be the webcam, `mjpeg`, `webrtc` or a `file`. |
| Caller location | `drone_interface.py` | `CALLER_LOCATION` and `SEARCH_RADIUS_M` (later: from the real 911 location data). |
| Real drone | `drone_interface.py` | Fill in `RealDrone` with pymavlink (same methods as `MockDrone`), then start with `DRONE_MODE=real`. |
| Speech-to-text | `transcriber.py` | Write a class with the same `poll()` and `reset()` as `MockTranscriber`, then use it in `main.py`. |

### How it fits together

```
browser  <── WebSocket /ws (call state, telemetry, transcript) ──────────  main.py (FastAPI)
browser  ── POST /api/answer, /api/dispatch, /api/drop, /api/talk, /api/rth ─>  │
browser  ── GET /api/camera-status (every 5 s) ──────────────────────────>  │  (TCP check to PI_HOST:8889)
browser  <── video: iframe straight from MediaMTX on the Pi (http://PI_HOST:8889/cam or /ir)
browser  <── machine vision: http://localhost:8100/stream.mjpg + /status.json ── monitor.py
                                                                              ├─ drone_interface.py  MockDrone / RealDrone
                                                                              ├─ transcriber.py      MockTranscriber
                                                                              └─ vision_manager.py   starts monitor.py in the zone
                                                                                    └─ machine_vision/monitor.py  (reads rtsp://PI_HOST:8554/cam)
```

### Files

    main.py              Web server: serves static/, runs the simulation loop, WebSocket + API endpoints
    drone_interface.py   All drone I/O: MockDrone (simulator) and RealDrone (MAVLink, to do)
    transcriber.py       MockTranscriber: the three scripted 911 calls
    vision_manager.py    Starts / stops / restarts machine_vision/monitor.py; reads its incidents
    machine_vision/      People and fire detection (monitor.py, vision.py, models); make_test_clip.py
    requirements.txt     Python packages
    static/index.html    The console page (all 4 screens)
    static/style.css     Console styles (Midnight Command theme, scales up on big screens)
    static/config.js     VIDEO_MODE (pi / mock), PI_HOST and stream URLs, VISION_HOST/PORT, mock VIDEO_SOURCE
    static/camera.js     Pi cameras side by side (Day + IR), connecting/offline messages, CAM status dot, T key
    static/app.js        WebSocket connection, picks the screen, ETA countdown, zone banner, transcript
    static/map.js        Search-zone maps (ETA minimap + Map drop-down), incident markers
    static/vision.js     Machine vision view: CV ON / RAW, Scene readout, Alerts with Confirm / Dismiss
    static/video.js      Builds the video element for each VIDEO_SOURCE type
    static/telemetry.js  Telemetry drop-down on the on-scene screen
    static/controls.js   Dispatch, push-to-talk, payload drop, return to base
    pi/setup_mediamtx.sh Installs MediaMTX + both cameras as a service on the Pi
    pi/README.md         Pi camera setup and troubleshooting

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
