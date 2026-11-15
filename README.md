# First 3 — Emergency Response Drone + Dispatcher Dashboard

> **The first 3 minutes change lives.** First 3 sends a drone to a 911 caller before ground units arrive. It gives the dispatcher eyes and a voice on scene and drops medical supplies to the people who need them.

<!-- TODO: add a photo of the drone and a screenshot of the dispatcher dashboard here -->
<!-- ![Drone](assets/drone.jpg) ![Dashboard](assets/dashboard.png) -->

## The problem

When someone calls 911, the dispatcher only has what the caller can describe, and the first ambulance or police car can be minutes away. In a cardiac arrest, an overdose or a severe bleed, those minutes decide the outcome. We talked with 911 dispatch centers while designing this. The gap they described is information and first aid in the time before responders reach the scene.

## What it does

- **Dispatcher dashboard.** The dispatcher answers the call, sees the caller's number and location, and assigns one of three drones to the scene.
- **Eyes on scene.** The drone streams a live camera feed to the dashboard, with a **Day / IR toggle** for night and low visibility.
- **Computer vision.** The ground station runs detection on the drone feed to count people on scene and flag someone who is down or needs help.
- **Voice on scene.** The dispatcher talks to people at the scene through a speaker on the drone, for example to coach CPR or bleeding control.
- **Medical payload drop.** A servo release drops a crisis kit (for example a bleeding-control kit or naloxone) at the caller's location.
- **AI call transcription.** The 911 call is transcribed live on the dashboard, so the dispatcher can track the details without retyping them.
- **Notes.** A notes panel for the dispatcher during the call.

## How it works

```
 ┌─────────────────────────── DRONE ───────────────────────────┐
 │  Flight controller (MicoAir) ── servo payload release       │
 │  Raspberry Pi 5 ── Pi camera (day) + Pi IR camera (night)   │
 │  ESP32 camera + mic on the payload       Speaker            │
 └──────────────┬──────────────────────────────────▲───────────┘
                │ video + audio stream             │ dispatcher voice
                ▼                                  │
 ┌──────────────────────── GROUND STATION ─────────┴───────────┐
 │  Computer vision (people count, person down)                │
 │  Call transcription                                         │
 │  Dispatcher dashboard (this repo): call, drones, feed, notes│
 └─────────────────────────────────────────────────────────────┘
```

The Pi only streams the camera feeds. **All heavy computation (CV and transcription) runs on the ground station**, so the drone stays light and its battery lasts longer.

## Hardware

| Part | Use |
|---|---|
| 7" deadcat frame | Airframe, keeps the props out of the camera view |
| 1300KV motors | Lift for a 7" setup carrying a payload |
| MicoAir flight controller | Flight control |
| Raspberry Pi 5 | Onboard streaming computer |
| Pi camera module + Pi IR camera module | Day and night video |
| ESP32 camera module + microphone | Payload-mounted view and audio |
| Servo + release mechanism | Payload drop |
| Speaker | Dispatcher voice on scene |
<!-- TODO: add battery, ESCs, props, radio/telemetry link and anything else on the build -->

## Team

We're a hardware-focused team: half of us built the drone and half built the software.

| Name | Focus | Built |
|---|---|---|
| <!-- TODO --> | Hardware | <!-- e.g. airframe, wiring, payload drop --> |
| <!-- TODO --> | Hardware | <!-- e.g. flight controller setup, Pi + cameras --> |
| <!-- TODO --> | Software | <!-- e.g. dispatcher dashboard UI/UX, CV integration --> |
| <!-- TODO --> | Software | <!-- e.g. streaming, transcription --> |

## What we built vs. what we used

Everything here was built during the hackathon unless it's listed below. We used these open-source projects and libraries and give them full credit:

| Project | What it does for us | License | Link |
|---|---|---|---|
| <!-- TODO: CV project name --> | Person detection on the drone feed. We integrated it into the dashboard UI/UX we designed. | <!-- TODO --> | <!-- TODO: github link --> |
| <!-- TODO: flight firmware, e.g. ArduPilot / PX4 / Betaflight --> | Flight control firmware | <!-- TODO --> | <!-- TODO --> |
| <!-- TODO: transcription model/API --> | 911 call transcription | <!-- TODO --> | <!-- TODO --> |
| Node.js | Dashboard server | MIT | https://nodejs.org |

**Our own work:** the drone build and payload drop mechanism, the dispatcher dashboard (UI/UX design and code), connecting the Pi camera streams to the ground station, and wiring the CV output and transcription into the dispatcher's view.

## Run the dashboard

You need Node.js 18 or newer. There's no `npm install`.

- **Mac:** double-click `start-mac.command` (the first time, right-click it and choose **Open**)
- **Windows:** double-click `start-windows.bat`
- **Terminal:** `node server.js`

Then open **http://localhost:4000**. Press **Ctrl+C** to stop.

Right now the call is demo data (`CALL` at the top of `js/call.js`), and notes aren't saved. Reload the page to start over.

## What's next

- Live call data from a real CAD/911 system instead of demo data
- GPS-based auto-dispatch of the nearest drone to the caller's location
- Two-way audio over a long-range link
- Testing the payload drop with dispatch partners

---

## For the team: development notes

### Working together

1. `git pull` first, so you're on the latest version.
2. Make a branch: `git checkout -b my-change`.
3. Run `node server.js` and open http://localhost:4000.
4. Commit, push (`git push -u origin my-change`) and open a pull request.

### Theme: Midnight Command

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

- Status colours always come with a word, and Critical also gets an icon. Never colour alone.
- Timers, coordinates and counts use the monospace font (`.mono`), so changing numbers don't shift.
- Thin borders, 6–10 px corners, no flashing or glowing effects.

### Structure

    index.html          The call page: Answer, call details, drones, notes
    server.js           Serves the site on port 4000
    css/styles.css      Theme tokens and page styles
    js/call.js          Answer button, caller details, drone choice (demo data at the top)
    assets/             Icons and images
    pages/              Further pages go here
