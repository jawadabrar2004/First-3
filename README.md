# Response Dashboard

This repo has two parts:

1. **Drone dispatch console** (Python, below): the 911 dispatcher screen for the emergency-response drone. Runs on mock data, no drone needed.
2. **Call page** (Node.js, further down): the first-page call answer flow.

---

## Drone dispatch console

A full-screen 911 dispatcher console for a big wall display. It walks the dispatcher through one emergency:

1. **Incoming call:** press **Answer**.
2. **On the call:** the live transcript fills the screen. Type the address in the box below it, then pick the drone to send: **EpiPen**, **AED** or **Bleeding control kit**. The drone launches immediately.
3. **En route:** the camera shows blurred behind a big **ETA** countdown (10 seconds for the demo).
4. **On scene:** the camera fills the screen as **Feed 1** with almost nothing on it: just two small drop-down boxes on its left edge, **Telemetry** and **Live call & status**, Telemetry starts open and Live call & status starts closed. Click a box's title bar (**Hide** / **Show**) to fold or unfold it, or press **T** for Telemetry. **Drop payload** and **Hold to talk** are in a thin bar under the camera, and **Return to base** is in the header next to LIVE.

Everything is mocked: the scripted caller is one of three emergencies (allergic reaction, cardiac arrest, severe bleeding), picked at random for each call. Your laptop webcam stands in for the drone camera.

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

Open **http://localhost:8000**. Allow microphone access (and camera access in mock mode) when the browser asks. Press **Ctrl+C** to stop.

`--reload` restarts the server whenever you save a Python file. **Restart demo** in the header starts a new call. Press **F11** for full screen on the big display.

### Demo tips

- The caller waits for you: after describing the emergency they pause until a drone is dispatched, then react when it arrives and when the payload lands.
- **Drop payload** needs a second click (**Confirm drop**) so it can't happen by accident.
- Hold **Hold to talk** (or focus it and hold Space) to record a message for the person giving aid; release to send it. Each clip adds a line to the status feed and is saved in `recordings/`.
- To change the 10-second ETA, edit `DEMO_ETA_SECONDS` in `drone_interface.py`.

### Raspberry Pi cameras (Day + IR)

The video panel shows the Pi 5's live cameras, streamed by MediaMTX. Setting up the Pi itself is covered in [pi/README.md](pi/README.md).

On the on-scene screen both cameras show **side by side**: **DAY CAM** on the left, **IR CAM** on the right (each labeled in its top-right corner). The **CAM** dot in the header is green when the Pi is reachable and red when it isn't. While the Pi is unreachable, both panes show **CAMERA OFFLINE - check Pi / Wi-Fi**, and it reconnects on its own when the Pi comes back (checked every 5 s).

**Pi or mock video:** in `static/config.js`, set

```js
const VIDEO_MODE = "pi";    // live Pi cameras
const VIDEO_MODE = "mock";  // no Pi: laptop webcam in both panes (the IR pane in grey)
```

then reload the page.

**Pointing at the Pi (`PI_HOST`):** the default is `raspberrypi.local`. On a phone hotspot that name can resolve to IPv6, where WebRTC may fail (the page loads but the video stays black). Use the Pi's IPv4 address instead (`hostname -I` on the Pi). Change it in **two places** so they match:

1. `static/config.js`: `const PI_HOST = "172.20.10.14";` (the browser uses this for the video), then reload the page.
2. The server, which uses it for the CAM status dot. Stop the server and start it with the variable set:
   - Windows (PowerShell): `$env:PI_HOST = "172.20.10.14"; python -m uvicorn main:app --reload`
   - Mac: `PI_HOST=172.20.10.14 python -m uvicorn main:app --reload`

The RTSP streams for computer vision are `rtsp://PI_HOST:8554/cam` and `rtsp://PI_HOST:8554/ir` (also listed as `PI_STREAMS.dayRtsp` / `irRtsp` in `config.js`).

### Swapping in real parts later

| To change | Edit | What to do |
|---|---|---|
| Video source | `static/config.js` | `VIDEO_MODE = "pi"` for the Pi cameras (see above). In mock mode, `VIDEO_SOURCE` can be the webcam, `mjpeg`, `webrtc` or a `file`. |
| Real drone | `drone_interface.py` | Fill in `RealDrone` with pymavlink (same methods as `MockDrone`), then start with `DRONE_MODE=real`. |
| Speech-to-text | `transcriber.py` | Write a class with the same `poll()` and `reset()` as `MockTranscriber`, then use it in `main.py`. |

### How it fits together

```
browser  <── WebSocket /ws (call state, telemetry, transcript) ──────────  main.py (FastAPI)
browser  ── POST /api/answer, /api/dispatch, /api/drop, /api/talk, /api/rth ─>  │
browser  ── GET /api/camera-status (every 5 s) ──────────────────────────>  │  (TCP check to PI_HOST:8889)
browser  <── video: iframe straight from MediaMTX on the Pi (http://PI_HOST:8889/cam or /ir)
                                                                              ├─ drone_interface.py  MockDrone / RealDrone
                                                                              └─ transcriber.py      MockTranscriber
```

### Files

    main.py              Web server: serves static/, runs the simulation loop, WebSocket + API endpoints
    drone_interface.py   All drone I/O: MockDrone (simulator) and RealDrone (MAVLink, to do)
    transcriber.py       MockTranscriber: the three scripted 911 calls
    requirements.txt     Python packages
    static/index.html    The console page (all 4 screens)
    static/style.css     Console styles (Midnight Command theme, scales up on big screens)
    static/config.js     VIDEO_MODE (pi / mock), PI_HOST and stream URLs, mock VIDEO_SOURCE
    static/camera.js     Pi cameras side by side (Day + IR), connecting/offline messages, CAM status dot, T key
    static/app.js        WebSocket connection, picks the screen, ETA countdown, transcript
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
