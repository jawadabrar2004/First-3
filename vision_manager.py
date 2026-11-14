"""
vision_manager.py - runs the machine vision (machine_vision/monitor.py) for main.py.

  VisionManager  starts monitor.py as a separate process, stops it, and
                 restarts it if it stops while it should be running.
                 (A video file simply ends, so in mock mode this also loops
                 the test clip.)
  IncidentLog    reads the incidents monitor.py saves
                 (machine_vision/incidents/incidents.jsonl), remembers where
                 the drone was when each one appeared, and keeps the
                 dispatcher's Confirm / Dismiss decision for each.

monitor.py serves its live results on its own port (VISION_PORT, 8100):
  http://localhost:8100/stream.mjpg   video with boxes and alerts drawn in
  http://localhost:8100/status.json   people in view + current alerts
The page reads those two directly. Incidents and their screenshots go
through main.py (/api/vision/...), because monitor.py's file server doesn't
allow other pages to read them (no CORS header).
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

MV_DIR = Path(__file__).parent / "machine_vision"
INCIDENTS_DIR = MV_DIR / "incidents"           # monitor.py's default --incidents folder
INCIDENTS_LOG = INCIDENTS_DIR / "incidents.jsonl"
LOG_FILE = MV_DIR / "monitor.log"              # everything monitor.py prints goes here
RESTART_DELAY_S = 3                            # wait this long before restarting monitor.py
SAFE_IMAGE_NAME = re.compile(r"^[\w.-]+\.jpg$")  # incident screenshot names, nothing else


class VisionManager:
    """Start / stop / babysit machine_vision/monitor.py."""

    def __init__(self, port):
        self.port = port
        self.proc = None          # the running monitor.py (subprocess.Popen)
        self.active = False       # should it be running?
        self.source = None
        self.is_file = False
        self.restarts = 0
        self.error = None         # last problem, shown in the UI
        self.started_at = None
        self._restart_at = None   # when to restart after it stopped
        self._log = None

    def start(self, source, is_file):
        """Start watching `source` (an rtsp:// address or a video file)."""
        if self.active:
            return False, "Machine vision is already running"
        if is_file and not Path(source).exists():
            self.error = f"Test clip not found: {source}"
            return False, self.error
        self.active, self.source, self.is_file = True, str(source), is_file
        self.restarts, self.error, self._restart_at = 0, None, None
        self.started_at = time.time()
        self._launch()
        return True, f"Machine vision started on {self.source}"

    def stop(self):
        """Stop monitor.py (and anything it started)."""
        was_active = self.active
        self.active = False
        self._restart_at = None
        if self.proc and self.proc.poll() is None:
            if os.name == "nt":
                # On Windows the venv's python.exe is a launcher with the real
                # interpreter as a child: end the whole tree (monitor.py's only).
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if self._log:
            self._log.close()
            self._log = None
        return was_active

    def watchdog(self):
        """Call often. Restarts monitor.py if it stopped while it should run.
        Returns a message the first time it notices a stop (else None)."""
        if not self.active or self.proc is None:
            return None
        code = self.proc.poll()
        if code is None:
            return None                       # still running, all good
        now = time.monotonic()
        if self._restart_at is None:          # just noticed it stopped
            self._restart_at = now + RESTART_DELAY_S
            if self.is_file and code == 0:
                return None                   # the test clip finished: quietly play it again
            self.error = f"monitor.py stopped (exit code {code}); restarting. See {LOG_FILE.name}"
            return self.error
        if now >= self._restart_at:
            self._restart_at = None
            self.restarts += 1
            self._launch()
        return None

    def status(self):
        running = self.proc is not None and self.proc.poll() is None
        return {
            "active": self.active,            # should be running
            "running": running,               # is running right now
            "pid": self.proc.pid if running else None,
            "source": self.source,
            "port": self.port,
            "restarts": self.restarts,
            "error": self.error,
            "log": str(LOG_FILE.relative_to(MV_DIR.parent)),
        }

    def _launch(self):
        cmd = [sys.executable, "-u", "monitor.py",       # same Python that runs main.py
               "--source", self.source, "--imgsz", "1280", "--no-show", "--serve", str(self.port)]
        if self.is_file:
            cmd += ["--fps", "6"]                         # look at 6 frames per second of the clip
        env = dict(os.environ, PYTHONUNBUFFERED="1",
                   # RTSP over TCP: much more reliable than UDP on a phone hotspot
                   OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp")
        if self._log is None:
            self._log = open(LOG_FILE, "a", encoding="utf-8")
        self._log.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} starting: {' '.join(cmd)}\n")
        self._log.flush()
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0  # no extra console window
        self.proc = subprocess.Popen(cmd, cwd=MV_DIR, stdout=self._log, stderr=subprocess.STDOUT,
                                     env=env, creationflags=flags)


class IncidentLog:
    """Incidents from this mission, read from monitor.py's incidents.jsonl."""

    def __init__(self):
        self.items = []
        self._offset = 0          # how far into incidents.jsonl we've read

    def new_session(self):
        """Forget earlier incidents (older missions stay in the file, but aren't shown)."""
        self.items = []
        self._offset = INCIDENTS_LOG.stat().st_size if INCIDENTS_LOG.exists() else 0

    def refresh(self, lat, lon):
        """Read any new incident lines. Each one is tagged with where the drone is now."""
        if not INCIDENTS_LOG.exists():
            return []
        size = INCIDENTS_LOG.stat().st_size
        if size < self._offset:   # file was cleared
            self._offset = 0
        if size == self._offset:
            return []
        with open(INCIDENTS_LOG, "rb") as f:
            f.seek(self._offset)
            chunk = f.read()
        end = chunk.rfind(b"\n") + 1      # only complete lines; a half-written one waits
        self._offset += end
        new = []
        for raw in chunk[:end].splitlines():
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            item = {
                "id": len(self.items),
                "time": entry.get("time"),
                "kind": entry.get("kind"),
                "text": entry.get("text") or entry.get("kind"),
                "people": entry.get("people"),
                "image": entry.get("image"),
                "lat": lat,                # drone position when the incident appeared
                "lon": lon,
                "decision": None,          # "confirmed" / "dismissed" by the dispatcher
            }
            self.items.append(item)
            new.append(item)
        return new

    @staticmethod
    def image_path(name):
        """Full path of a screenshot, or None if the name looks wrong or it doesn't exist."""
        if not SAFE_IMAGE_NAME.match(name or ""):
            return None
        path = INCIDENTS_DIR / name
        return path if path.is_file() else None
