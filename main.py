"""
main.py - the web server for the dispatcher console.

What it does:
  * serves the web page (everything in the static/ folder)
  * runs the mock drone + mock 911 call in the background
  * pushes live updates to the browser over a WebSocket at /ws
  * handles the dispatcher's actions:
      /api/answer   pick up the incoming call
      /api/dispatch send a drone (address + payload type)
      /api/drop     drop the payload
      /api/talk     push-to-talk audio clip
      /api/rth      return to home
      /api/reset    start the demo over
  * reports whether the Raspberry Pi camera server is reachable (/api/camera-status)
  * works out the search zone (caller's reported location + uncertainty radius)
    and starts the machine vision when the drone enters it (vision_manager.py):
      /api/vision/start, /api/vision/stop, /api/vision/status, /api/vision/incidents

Run it with:   python -m uvicorn main:app --reload
Then open:     http://localhost:8000

Messages sent to the browser over /ws (all JSON):
  {"type": "snapshot",  ...}  full state: sent on connect and whenever the call changes
  {"type": "telemetry", "data": {...}, "mission_seconds": 42}
      data includes distance_to_caller, distance_to_zone, in_search_zone, cameras_active
  {"type": "incident", "incident": {...}}   a machine vision alert (new, or confirmed/dismissed)
  {"type": "transcript", "line": {"t": 12, "speaker": "CALLER", "text": "..."}}
"""

import asyncio
import os
import re
import socket
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from drone_interface import (CALLER_LOCATION, HOME, PAYLOADS, SEARCH_RADIUS_M, MockDrone, RealDrone,
                             distance_to_search_zone)
from transcriber import MockTranscriber
from vision_manager import IncidentLog, VisionManager

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
RECORDINGS_DIR = BASE_DIR / "recordings"
TICK_SECONDS = 0.25  # how often the simulation updates (4 times per second)



def frontend_setting(name, default):
    """Read `const NAME = "value";` (or a number) from static/config.js, so the
    page and the server share one settings file. Returns default if not found."""
    try:
        text = (STATIC_DIR / "config.js").read_text(encoding="utf-8")
    except OSError:
        return default
    m = re.search(r'^const\s+' + name + r'\s*=\s*(?:"([^"]*)"|(\d+))\s*;', text, re.MULTILINE)
    if not m:
        return default
    return m.group(1) if m.group(1) is not None else int(m.group(2))


# Raspberry Pi running MediaMTX (the camera server). Taken from PI_HOST in
# static/config.js, so the page and the server always agree. To override it
# without editing files, set the environment variable, e.g. PowerShell:
#   $env:PI_HOST = "192.168.43.120"
PI_HOST = os.getenv("PI_HOST") or frontend_setting("PI_HOST", "raspberrypi.local")
PI_WEBRTC_PORT = 8889  # MediaMTX WebRTC pages:  http://PI_HOST:8889/cam  and  /ir
PI_RTSP_PORT = 8554    # MediaMTX RTSP (for computer vision later):  rtsp://PI_HOST:8554/cam  and  /ir
PI_CHECK_TIMEOUT = 3.0  # seconds; looking up raspberrypi.local on a hotspot can be slow

# PI_HOST looked up to an IP address once and remembered. Looking the name up
# on every check was the slow, flaky part (see api_camera_status). It is only
# looked up again after a failed connection, in case the Pi got a new address.
_pi_ip = None
_resolve_task = None  # the lookup in progress; it keeps going even if a check times out

# Machine vision (machine_vision/monitor.py), started when the drone enters the search zone.
#   Pi mode:   reads the Pi's day camera from MediaMTX over RTSP
#   Mock mode: the browser already uses the laptop webcam, so it reads a video file instead
VISION_PORT = int(os.getenv("VISION_PORT") or frontend_setting("VISION_PORT", 8100))
VISION_MOCK_SOURCE = os.getenv("VISION_MOCK_SOURCE") or str(BASE_DIR / "machine_vision" / "test_clip.mp4")
vision = VisionManager(VISION_PORT)
incidents = IncidentLog()


def video_mode():
    """'pi' or 'mock': the VIDEO_MODE env var, else the one in static/config.js."""
    return os.getenv("VIDEO_MODE") or frontend_setting("VIDEO_MODE", "pi")


def vision_source():
    """What monitor.py should watch: (source, is_file)."""
    if video_mode() == "mock":
        return VISION_MOCK_SOURCE, True
    host = _pi_ip or PI_HOST  # the looked-up IP if we have it (faster, avoids IPv6)
    if ":" in host:
        host = f"[{host}]"    # IPv6 addresses need brackets in a URL
    return f"rtsp://{host}:{PI_RTSP_PORT}/cam", False


async def start_vision(reason):
    if vision.active:
        return True, "Machine vision is already running"
    source, is_file = vision_source()
    incidents.new_session()
    ok, message = vision.start(source, is_file)
    await add_transcript_line("SYSTEM", f"Machine vision started ({reason})" if ok
                              else f"Machine vision NOT started: {message}")
    return ok, message


async def stop_vision(reason):
    if vision.stop():
        await add_transcript_line("SYSTEM", f"Machine vision stopped ({reason})")

# ---------------------------------------------------------------------------
# Pick the pieces. Swap these lines to use real hardware / real services.
# ---------------------------------------------------------------------------
drone = RealDrone() if os.getenv("DRONE_MODE") == "real" else MockDrone()
transcriber = MockTranscriber()


class Mission:
    """Everything we remember about the current call."""

    def __init__(self):
        self.answered_at = None  # time the call was answered (None = still ringing)
        self.address = None      # typed in by the dispatcher
        self.transcript = []     # list of {"t", "speaker", "text"}
        self.zone_entered = False  # has the drone reached the search zone? (cameras + vision on)

    def seconds(self):
        """Seconds since the call was answered (0 while ringing)."""
        if self.answered_at is None:
            return 0
        return int(time.monotonic() - self.answered_at)


mission = Mission()


# ---------------------------------------------------------------------------
# WebSocket connections: keep a list of open browsers and send to all of them
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.clients = set()

    async def connect(self, ws):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws):
        self.clients.discard(ws)

    async def broadcast(self, message):
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)  # browser went away


manager = ConnectionManager()


def snapshot():
    """The full current state, for a browser that just connected."""
    return {
        "type": "snapshot",
        "call": {
            "answered": mission.answered_at is not None,
            "caller_number": transcriber.caller_number,
            "address": mission.address,
        },
        "mission": {
            "home": HOME,
            # Caller's reported location (like wireless 911): a point + uncertainty radius
            "caller": {**CALLER_LOCATION, "radius_m": SEARCH_RADIUS_M},
        },
        "telemetry": telemetry_with_zone(),
        "mission_seconds": mission.seconds(),
        "incidents": incidents.items,
        "transcript": mission.transcript,
    }


async def add_transcript_line(speaker, text):
    """Store a transcript / status line and send it to every browser."""
    line = {"t": mission.seconds(), "speaker": speaker, "text": text}
    mission.transcript.append(line)
    await manager.broadcast({"type": "transcript", "line": line})


mission_last_incident_check = [0.0]  # when we last read incidents.jsonl


def telemetry_with_zone():
    """Drone telemetry plus where it is relative to the search zone.
    Done here (not in the drone class) so it works the same for the real drone."""
    t = drone.get_telemetry()
    to_caller, to_zone = distance_to_search_zone(t["lat"], t["lon"])
    t["distance_to_caller"] = round(to_caller)
    t["distance_to_zone"] = round(to_zone)            # 0 once inside
    t["in_search_zone"] = to_caller <= SEARCH_RADIUS_M
    t["cameras_active"] = mission.zone_entered        # stays on until the next call
    t["vision_active"] = vision.active
    return t


async def simulation_loop():
    """Runs forever in the background: move the drone, play the call, send updates."""
    last = time.monotonic()
    mission_last_incident_check[0] = last
    while True:
        await asyncio.sleep(TICK_SECONDS)
        now = time.monotonic()
        dt, last = now - last, now

        try:
            drone.update(dt)
            telemetry = telemetry_with_zone()

            # Entering the search zone switches the cameras and machine vision on (once)
            flying_out = telemetry["phase"] in ("EN_ROUTE", "SEARCHING", "ON_SCENE")
            if telemetry["in_search_zone"] and flying_out and not mission.zone_entered:
                mission.zone_entered = True
                telemetry["cameras_active"] = True
                await start_vision("drone entered the search zone")
                telemetry["vision_active"] = vision.active
            # Heading home (dispatcher or automatic): machine vision off
            if vision.active and telemetry["phase"] in ("RETURNING", "LANDING", "LANDED"):
                await stop_vision("drone returning to base")
                telemetry["vision_active"] = False

            # Keep monitor.py running; pick up new incidents about once a second
            problem = vision.watchdog()
            if problem:
                await add_transcript_line("SYSTEM", problem)
            if vision.active and now - mission_last_incident_check[0] >= 1.0:
                mission_last_incident_check[0] = now
                for item in incidents.refresh(telemetry["lat"], telemetry["lon"]):
                    await manager.broadcast({"type": "incident", "incident": item})
                    await add_transcript_line("SYSTEM", f"Machine vision alert: {item['text']}")

            # Drone status messages show up in the feed as SYSTEM lines
            for event in drone.pop_events():
                await add_transcript_line("SYSTEM", event)

            # The caller only talks once the call has been answered
            if mission.answered_at is not None:
                for line in transcriber.poll(dt, telemetry):
                    await add_transcript_line(line["speaker"], line["text"])

            await manager.broadcast(
                {"type": "telemetry", "data": telemetry, "mission_seconds": mission.seconds()}
            )
        except Exception as err:  # keep the loop alive no matter what
            print("simulation error:", err)


@asynccontextmanager
async def lifespan(app):
    """Start the background loop when the server starts, stop it on shutdown."""
    drone.connect()
    task = asyncio.create_task(simulation_loop())
    yield
    task.cancel()
    vision.stop()  # never leave monitor.py running after the server stops


app = FastAPI(title="First 3 Drone Dispatch", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Web page + live data
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        await ws.send_json(snapshot())
        while True:
            await ws.receive_text()  # we don't expect messages; this just waits
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Dispatcher actions
# ---------------------------------------------------------------------------
@app.post("/api/answer")
async def api_answer():
    """Pick up the ringing call. The scripted caller starts talking."""
    if mission.answered_at is None:
        mission.answered_at = time.monotonic()
        await manager.broadcast(snapshot())
    return {"ok": True}


class DispatchRequest(BaseModel):
    address: str
    payload: str  # "epipen", "aed" or "bleed_kit"


@app.post("/api/dispatch")
async def api_dispatch(req: DispatchRequest):
    """Send a drone with the chosen payload to the address the dispatcher typed."""
    address = req.address.strip()
    if not address:
        return {"ok": False, "message": "Type the address first"}
    if req.payload not in PAYLOADS:
        return {"ok": False, "message": "Unknown payload"}

    ok, message = drone.dispatch(req.payload)
    if ok:
        mission.address = address
        await add_transcript_line("SYSTEM", f"Dispatcher sent the {PAYLOADS[req.payload]} drone to {address}")
        await manager.broadcast(snapshot())
    return {"ok": ok, "message": message}


@app.post("/api/drop")
async def api_drop():
    ok, message = drone.drop_payload()
    if ok:
        await add_transcript_line("SYSTEM", "Dispatcher confirmed payload drop")
    return {"ok": ok, "message": message, "payload": drone.get_telemetry()["payload"]}


@app.post("/api/rth")
async def api_rth():
    ok, message = drone.return_to_home()
    if ok:
        await stop_vision("return to base")
    return {"ok": ok, "message": message}


@app.post("/api/talk")
async def api_talk(audio: UploadFile = File(...), seconds: float = Form(0)):
    """Push-to-talk: save the recorded clip. Later: play it on the drone's speaker."""
    RECORDINGS_DIR.mkdir(exist_ok=True)
    # The browser usually records webm (Chrome/Firefox) or mp4 (Safari)
    ext = ".mp4" if "mp4" in (audio.content_type or "") else ".webm"
    filename = "talk-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ext
    data = await audio.read()
    (RECORDINGS_DIR / filename).write_bytes(data)

    await add_transcript_line(
        "SYSTEM", f"Dispatcher talked to the person giving aid ({seconds:.1f} s through drone speaker)"
    )
    return {"ok": True, "file": f"recordings/{filename}", "bytes": len(data)}


async def _resolve_pi_host():
    """Look up PI_HOST's IP address. IPv4 first: it's the reliable one on phone hotspots."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(PI_HOST, PI_WEBRTC_PORT, type=socket.SOCK_STREAM)
    infos.sort(key=lambda info: info[0] != socket.AF_INET)  # IPv4 addresses first
    return infos[0][4][0]


@app.get("/api/camera-status")
async def api_camera_status():
    """
    Can we open a TCP connection to the Pi's MediaMTX WebRTC port?

    Why it works this way: the first version looked up raspberrypi.local
    (mDNS) on every call with a 1 s timeout. On a Windows phone hotspot about
    1 in 4 lookups took longer than that, the check said "offline", and the
    page dropped and reloaded both video feeds. Now the IP is cached, the
    timeout is 3 s (a direct connection on the hotspot sometimes takes just over
    1 s), and the page only goes offline after 3 failed checks in a row.
    """
    global _pi_ip
    started = time.perf_counter()
    error = None

    async def check():
        global _pi_ip, _resolve_task
        if _pi_ip is None:
            # Looking up raspberrypi.local on Windows can take ~11 s. Run it as its
            # own task and shield it, so a check that times out doesn't cancel it;
            # a later check then picks up the finished result.
            if _resolve_task is None or (_resolve_task.done() and _resolve_task.exception() is not None):
                _resolve_task = asyncio.create_task(_resolve_pi_host())
            _pi_ip = await asyncio.shield(_resolve_task)
        _, writer = await asyncio.open_connection(_pi_ip, PI_WEBRTC_PORT)
        writer.close()

    try:
        await asyncio.wait_for(check(), timeout=PI_CHECK_TIMEOUT)
        online = True
    except (OSError, asyncio.TimeoutError) as err:  # name not found, refused, or too slow
        online = False
        error = f"{type(err).__name__}: {err}" if str(err) else type(err).__name__  # e.g. WinError code
    ip_used = _pi_ip
    if not online and _pi_ip is not None:
        _pi_ip = None          # connection failed: look the name up again next time,
        _resolve_task = None   # in case the Pi's address changed

    return {
        "online": online,
        "host": PI_HOST,
        "ip": ip_used,
        "port": PI_WEBRTC_PORT,
        "duration_ms": round((time.perf_counter() - started) * 1000),  # for debugging
        "error": error,
    }


# ---------------------------------------------------------------------------
# Machine vision
# ---------------------------------------------------------------------------
@app.post("/api/vision/start")
async def api_vision_start():
    ok, message = await start_vision("started by dispatcher")
    return {"ok": ok, "message": message, "status": vision.status()}


@app.post("/api/vision/stop")
async def api_vision_stop():
    await stop_vision("stopped by dispatcher")
    return {"ok": True, "status": vision.status()}


@app.get("/api/vision/status")
async def api_vision_status():
    source, _ = vision_source()
    return {**vision.status(), "mode": video_mode(), "next_source": source, "incidents": len(incidents.items)}


@app.get("/api/vision/incidents")
async def api_vision_incidents():
    """Incidents from this mission (read from machine_vision/incidents/incidents.jsonl)."""
    return {"incidents": incidents.items}


@app.get("/api/vision/incidents/{image}")
async def api_vision_incident_image(image: str):
    path = IncidentLog.image_path(image)
    if path is None:
        return Response(status_code=404)
    return FileResponse(path, media_type="image/jpeg")


@app.post("/api/vision/incidents/{incident_id}/{decision}")
async def api_vision_decide(incident_id: int, decision: str):
    """The dispatcher confirms or dismisses an alert (the drone never acts on its own)."""
    if decision not in ("confirm", "dismiss") or not 0 <= incident_id < len(incidents.items):
        return {"ok": False, "message": "Unknown incident or decision"}
    item = incidents.items[incident_id]
    item["decision"] = "confirmed" if decision == "confirm" else "dismissed"
    await add_transcript_line("SYSTEM", f"Dispatcher {item['decision']} alert: {item['text']}")
    await manager.broadcast({"type": "incident", "incident": item})
    return {"ok": True, "incident": item}


@app.post("/api/reset")
async def api_reset():
    """Start the demo over: drone back on the pad, a new call ringing."""
    global mission
    await stop_vision("demo restarted")
    drone.reset()
    transcriber.reset()
    mission = Mission()
    incidents.new_session()
    await manager.broadcast(snapshot())
    return {"ok": True}


# Everything in static/ (CSS, JS, images) is served under /static/...
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    # Lets you start the app with plain `python main.py` too
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
