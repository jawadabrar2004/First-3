"""
main.py - the web server for the dispatcher console.

What it does:
  * serves the web page (everything in the static/ folder)
  * runs the mock drone + mock 911 call in the background
  * pushes live updates to the browser over a WebSocket at /ws
  * handles the dispatcher's buttons: /api/drop, /api/rth, /api/talk

Run it with:   python -m uvicorn main:app --reload
Then open:     http://localhost:8000

Messages sent to the browser over /ws (all JSON):
  {"type": "snapshot",  ...}  full state, sent when a browser connects or the demo restarts
  {"type": "telemetry", "data": {...}, "mission_seconds": 42}
  {"type": "transcript", "line": {"t": 12, "speaker": "CALLER", "text": "..."}}
  {"type": "key_info",  "data": {...}}
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from drone_interface import HOME, INCIDENT, MockDrone, RealDrone
from key_info import KeywordExtractor
from transcriber import MockTranscriber

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
RECORDINGS_DIR = BASE_DIR / "recordings"
TICK_SECONDS = 0.25  # how often the simulation updates (4 times per second)

# ---------------------------------------------------------------------------
# Pick the pieces. Swap these lines to use real hardware / real services.
# ---------------------------------------------------------------------------
drone = RealDrone() if os.getenv("DRONE_MODE") == "real" else MockDrone()
transcriber = MockTranscriber()
extractor = KeywordExtractor()  # later: LLMExtractor()


class Mission:
    """Everything we remember about the current call."""

    def __init__(self):
        self.started = time.monotonic()
        self.transcript = []  # list of {"t", "speaker", "text"}
        self.key_info = extractor.extract([])

    def seconds(self):
        return int(time.monotonic() - self.started)


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
        "mission": {"home": HOME, "incident": INCIDENT},
        "telemetry": drone.get_telemetry(),
        "mission_seconds": mission.seconds(),
        "transcript": mission.transcript,
        "key_info": mission.key_info,
    }


async def add_transcript_line(speaker, text):
    """Store a transcript line, send it out, and refresh the key info if it changed."""
    line = {"t": mission.seconds(), "speaker": speaker, "text": text}
    mission.transcript.append(line)
    await manager.broadcast({"type": "transcript", "line": line})

    new_info = extractor.extract(mission.transcript)
    if new_info != mission.key_info:
        mission.key_info = new_info
        await manager.broadcast({"type": "key_info", "data": new_info})


async def simulation_loop():
    """Runs forever in the background: move the drone, play the call, send updates."""
    last = time.monotonic()
    while True:
        await asyncio.sleep(TICK_SECONDS)
        now = time.monotonic()
        dt, last = now - last, now

        try:
            drone.update(dt)
            telemetry = drone.get_telemetry()

            # Drone status messages show up in the transcript as SYSTEM lines
            for event in drone.pop_events():
                await add_transcript_line("SYSTEM", event)

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
# Dispatcher buttons
# ---------------------------------------------------------------------------
@app.post("/api/drop")
async def api_drop():
    ok, message = drone.drop_payload()
    if ok:
        await add_transcript_line("SYSTEM", "Dispatcher confirmed payload drop")
    return {"ok": ok, "message": message, "payload": drone.get_telemetry()["payload"]}


@app.post("/api/rth")
async def api_rth():
    ok, message = drone.return_to_home()
    return {"ok": ok, "message": message}


@app.post("/api/talk")
async def api_talk(audio: UploadFile = File(...)):
    """Push-to-talk: save the recorded clip. Later: play it on the drone's speaker."""
    RECORDINGS_DIR.mkdir(exist_ok=True)
    # The browser usually records webm (Chrome/Firefox) or mp4 (Safari)
    ext = ".mp4" if "mp4" in (audio.content_type or "") else ".webm"
    filename = "talk-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ext
    data = await audio.read()
    (RECORDINGS_DIR / filename).write_bytes(data)

    await add_transcript_line("SYSTEM", f"Dispatcher voice message sent to drone speaker ({filename})")
    return {"ok": True, "file": f"recordings/{filename}", "bytes": len(data)}


@app.post("/api/reset")
async def api_reset():
    """Start the demo over: drone back on the pad, call from the beginning."""
    global mission
    drone.reset()
    transcriber.reset()
    mission = Mission()
    await manager.broadcast(snapshot())
    return {"ok": True}


# Everything in static/ (CSS, JS, images) is served under /static/...
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    # Lets you start the app with plain `python main.py` too
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
