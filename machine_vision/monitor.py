"""Watch a camera or video for emergencies and save a screenshot of each one.

Detects:
  person_down   someone lying on the ground
  choking       both hands held at the throat (weak signal, treat as "possible")
  waving        someone waving, or holding both arms up, for help
  fire          flames, nobody in view
  fire_people   flames with people in view, with a head count

Laptop webcam:   python monitor.py
A video clip:    python monitor.py --source clips/x.mp4 --fps 6
Pi camera sent to the laptop (run pi_camera_stream.sh on the Pi first):
                 python monitor.py --source tcp://<pi address>:8554 --serve 8000
On the Pi itself: python monitor.py --source picam --no-show --serve 8000
                 then open http://<pi address>:8000 on any device on the same network
"""
from __future__ import annotations

import argparse
import html
import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

import vision

ALERT_KINDS = ("person_down", "choking", "waving", "fire", "fire_people")


# --- Fire ----------------------------------------------------------------------

@dataclass
class Fire:
    box: tuple       # x1, y1, x2, y2 in frame pixels
    age_s: float     # how long it has been visible


class _Blob:
    def __init__(self, t):
        self.first = self.seen = t
        self.box = (0, 0, 0, 0)
        self.mask = None        # its outline at the last sample
        self.history = deque()  # (time, area, how much the outline changed since the last sample)
        self.proof = None       # last time it behaved like flames rather than a steady object
        self.person = None      # last time it sat on a person
        self.matched = False


def _shape_change(a, b):
    """How different two outlines are, 0 (same) to 1, after lining up their centres."""
    import cv2
    import numpy as np
    longest = max(a.shape + b.shape)
    if longest > 48:   # compare big regions on a coarser grid: faster, and less edge noise
        f = 48.0 / longest
        a, b = (cv2.resize(m.astype(np.uint8), None, fx=f, fy=f, interpolation=cv2.INTER_AREA) > 0
                for m in (a, b))
    if not a.any() or not b.any():
        return 1.0
    size = 2 * max(a.shape + b.shape) + 6

    def centred(m):
        ys, xs = np.nonzero(m)
        top, left = size // 2 - int(round(ys.mean())), size // 2 - int(round(xs.mean()))
        canvas = np.zeros((size, size), bool)
        canvas[top:top + m.shape[0], left:left + m.shape[1]] = m
        return canvas

    ca, cb = centred(a), centred(b)
    best = 0.0
    for dy in (-1, 0, 1):          # allow one pixel of slack in the line-up
        for dx in (-1, 0, 1):
            moved = np.roll(np.roll(cb, dy, 0), dx, 1)
            union = np.count_nonzero(ca | moved)
            best = max(best, np.count_nonzero(ca & moved) / union if union else 0.0)
    return 1.0 - best


class FireDetector:
    """Finds flames by colour, glow and movement. No model needed.

    A region counts as fire when all of these hold:
      - it is flame-coloured with a white-hot middle,
      - it glows: it is much brighter than whatever surrounds it,
      - it is not on a person (badge, hi-vis clothing, sunlit skin),
      - it stays in view for a moment, and
      - when it is big enough to judge, its outline keeps changing the way flames do.

    Orange objects fail the glow test in a lit scene, and a steady lamp fails the
    last test. What can still fool it: small orange lights against a dark
    background (street lamps, indicators) and a screen showing fire, which DOES
    count; that is how you test this indoors (prop the screen up; held against
    your body it is treated as something you are wearing).

    sensitivity:
      low     only large flames whose outline visibly flickers
      normal  also small, distant fires that glow against dark surroundings
      high    reacts to fainter glow and to fire-coloured things on people
    """
    WIDTH = 640          # work on a copy at most this wide
    MAX_AREA = 0.35      # bigger than this is sky or a wall, not a fire
    CORE = 0.12          # this fraction of the region must be white-hot
    JUDGE_AREA = 0.0015  # regions this big (fraction of the frame) must show flicker
    SHAPE = 0.30         # outline change between samples that counts as flickering
    WINDOW_S = 2.0       # judge flicker over this much history
    SAMPLE_S = 0.15      # take at most one outline sample per this interval
    LATCH_S = 2.0        # stay confirmed this long after the last flicker
    PERSON_S = 2.0       # ignore a region this long after it was last on a person
    FORGET_S = 0.7
    LEVELS = {
        #           smallest flame    glow: surroundings at   seconds it   small steady    regions on
        #           (frame fraction)  most this bright        must stay    regions count   people count
        "low":    dict(min_area=0.0015, glow=0.45, hold_s=1.5, small_ok=False, on_person=False),
        "normal": dict(min_area=0.0004, glow=0.55, hold_s=1.5, small_ok=True, on_person=False),
        "high":   dict(min_area=0.00025, glow=0.75, hold_s=0.8, small_ok=True, on_person=True),
    }

    def __init__(self, sensitivity="normal"):
        level = self.LEVELS[sensitivity]
        self.min_area, self.glow, self.hold_s = level["min_area"], level["glow"], level["hold_s"]
        self.small_ok, self.on_person = level["small_ok"], level["on_person"]
        self.blobs = []

    def reset(self):
        self.blobs = []

    def candidates(self, frame):
        """Glowing flame-coloured regions in one frame, at the working scale.

        Returns ([(box, area, outline), ...], frame pixels per working pixel).
        """
        import cv2
        import numpy as np
        h, w = frame.shape[:2]
        width = min(self.WIDTH, w)
        small = frame if width == w else cv2.resize(
            frame, (width, max(1, round(h * width / w))), interpolation=cv2.INTER_AREA)
        hue, sat, val = cv2.split(cv2.cvtColor(small, cv2.COLOR_BGR2HSV))
        grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        flame = ((hue <= 35) | (hue >= 172)) & (sat >= 100) & (val >= 190)
        both = (flame | ((val >= 235) & (sat < 100))).astype(np.uint8)
        both = cv2.morphologyEx(both, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(both, 8)
        height, width = both.shape
        found = []
        for i in range(1, count):
            x, y, bw, bh, area = (int(v) for v in stats[i])
            if not self.min_area * both.size <= area <= self.MAX_AREA * both.size:
                continue
            part = labels[y:y + bh, x:x + bw] == i
            # Flame colour with a white-hot middle. White lamps and windows have no
            # flame colour; skin and orange plastic have no white-hot middle.
            if np.count_nonzero(flame[y:y + bh, x:x + bw] & part) < 0.15 * area:
                continue
            if np.count_nonzero((grey[y:y + bh, x:x + bw] >= 220) & part) < self.CORE * area:
                continue
            # Glow: fire lights its surroundings, it is not lit by them. Compare with
            # what lies around it, leaving out neighbouring flames.
            pad = max(3, int(0.75 * max(bw, bh)))
            x1, y1, x2, y2 = max(0, x - pad), max(0, y - pad), min(width, x + bw + pad), min(height, y + bh + pad)
            around = val[y1:y2, x1:x2][both[y1:y2, x1:x2] == 0]
            inside = float(val[y:y + bh, x:x + bw][part].mean())
            if around.size >= 8 and float(np.median(around)) > self.glow * inside:
                continue
            found.append(((x, y, x + bw, y + bh), float(area), part))
        return found, w / width

    @staticmethod
    def _overlap(a, b):
        margin = 0.3 * max(a[2] - a[0], a[3] - a[1])
        w = min(a[2], b[2]) - max(a[0], b[0]) + 2 * margin
        h = min(a[3], b[3]) - max(a[1], b[1]) + 2 * margin
        return w * h if w > 0 and h > 0 else 0.0

    @staticmethod
    def _on_person(box, people):
        """True if the region lies on a person and is small next to them."""
        area = max(1.0, (box[2] - box[0]) * (box[3] - box[1]))
        for p in people:
            w = min(box[2], p[2]) - max(box[0], p[0])
            h = min(box[3], p[3]) - max(box[1], p[1])
            if (w > 0 and h > 0 and w * h >= 0.7 * area
                    and area <= 0.5 * (p[2] - p[0]) * (p[3] - p[1])):
                return True
        return False

    def update(self, frame, t, people=()):
        """Return the confirmed fires in this frame. people: boxes of the people in it."""
        found, scale = self.candidates(frame)
        people = [tuple(v / scale for v in p) for p in people]
        frame_px = frame.shape[0] * frame.shape[1] / (scale * scale)
        for blob in self.blobs:
            blob.matched = False
        for box, area, outline in found:
            best, best_overlap = None, 0.0
            for blob in self.blobs:
                overlap = 0.0 if blob.matched else self._overlap(box, blob.box)
                if overlap > best_overlap:
                    best, best_overlap = blob, overlap
            if best is None:
                best = _Blob(t)
                self.blobs.append(best)
            best.matched = True
            best.box, best.seen = box, t
            if not self.on_person and self._on_person(box, people):
                best.person = t
            if best.mask is None:
                best.mask = outline
                best.history.append((t, area, None))
            elif t - best.history[-1][0] >= self.SAMPLE_S:
                best.history.append((t, area, _shape_change(best.mask, outline)))
                best.mask = outline
            while t - best.history[0][0] > self.WINDOW_S:
                best.history.popleft()
            areas = sorted(a for _, a, _ in best.history)
            changes = sorted(c for _, _, c in best.history if c is not None)
            if areas[len(areas) // 2] < self.JUDGE_AREA * frame_px:
                # Too small to judge its outline: a distant fire looks steady.
                if self.small_ok:
                    best.proof = t
            elif len(changes) >= 4 and changes[len(changes) // 2] >= self.SHAPE:
                best.proof = t
        self.blobs = [b for b in self.blobs if t - b.seen <= self.FORGET_S]
        fires = []
        for b in self.blobs:
            if (b.matched and t - b.first >= self.hold_s
                    and b.proof is not None and t - b.proof <= self.LATCH_S
                    and (b.person is None or t - b.person > self.PERSON_S)):
                fires.append(Fire(tuple(v * scale for v in b.box), t - b.first))
        return fires


class ModelFireDetector:
    """Uses a YOLO model trained on fire: any class with 'fire' or 'flame' in its name."""
    HOLD_S = 0.5

    def __init__(self, path, imgsz=640, conf=0.35):
        from ultralytics import YOLO
        self.model = YOLO(path)
        self.imgsz, self.conf = imgsz, conf
        self.ids = [i for i, name in self.model.names.items()
                    if "fire" in name.lower() or "flame" in name.lower()]
        if not self.ids:
            raise SystemExit(f"{path} has no fire class (it has: {list(self.model.names.values())})")
        self.timer = vision._Timer()

    def reset(self):
        self.timer = vision._Timer()

    def update(self, frame, t, people=()):
        r = self.model(frame, imgsz=self.imgsz, conf=self.conf, classes=self.ids, verbose=False)[0]
        boxes = r.boxes.xyxy.cpu().numpy().tolist() if r.boxes is not None else []
        held = self.timer.update(bool(boxes), t)
        return [Fire(tuple(b), held) for b in boxes] if held >= self.HOLD_S else []


class NoFire:
    def reset(self):
        pass

    def update(self, frame, t, people=()):
        return []


# --- Putting it together ---------------------------------------------------------

@dataclass
class Scene:
    people: list
    target: object
    fires: list
    alerts: dict      # kind -> sentence


class Monitor:
    def __init__(self, pose, fire, enhance=False):
        self.pose, self.fire, self.enhance = pose, fire, enhance

    def reset(self):
        """Forget everything seen so far, ready for a new clip."""
        self.pose.tracks = []
        self.fire.reset()

    def process(self, frame, t):
        target, people = self.pose.process(vision.enhance(frame) if self.enhance else frame, t)
        # Fire uses the true colours, not the enhanced copy. It is told where the
        # people are so that it can ignore what they wear and carry.
        fires = self.fire.update(frame, t, [p.box for p in people])
        return self.assess(target, people, fires)

    def assess(self, target, people, fires):
        hold = self.pose.hold_s
        alerts = {}
        down = sum(p.lying_s >= hold for p in people)
        if down:
            alerts["person_down"] = "Person down" if down == 1 else f"{down} people down"
        if any(p.choking_s >= vision.CHOKE_HOLD_S for p in people):
            alerts["choking"] = "Possible choking: hands at throat"
        if any(p.raised_s >= hold for p in people):
            alerts["waving"] = "Person signalling for help"
        if fires:
            n = len(people)
            if n:
                alerts["fire_people"] = f"Fire with {n} {'person' if n == 1 else 'people'} in view"
            else:
                alerts["fire"] = "Fire, nobody in view"
        return Scene(people, target, fires, alerts)


def annotate(frame, scene):
    """Draw people, fires and alert banners onto the frame."""
    import cv2
    font = cv2.FONT_HERSHEY_SIMPLEX
    vision.draw(frame, scene.people, scene.target, aim=False)
    for fire in scene.fires:
        x1, y1, x2, y2 = (int(v) for v in fire.box)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 80, 255), 3)
        cv2.putText(frame, "FIRE", (x1, max(18, y1 - 6)), font, 0.7, (0, 80, 255), 2)
    y = 30
    for text in scene.alerts.values():
        (tw, th), _ = cv2.getTextSize(text, font, 0.7, 2)
        cv2.rectangle(frame, (8, y - th - 8), (18 + tw, y + 8), (0, 0, 200), -1)
        cv2.putText(frame, text, (13, y), font, 0.7, (255, 255, 255), 2)
        y += th + 22
    cv2.putText(frame, f"people in view: {len(scene.people)}", (10, frame.shape[0] - 12),
                font, 0.6, (255, 255, 255), 2)
    return frame


class Incidents:
    """Saves a screenshot and a log line for each new alert."""
    UPDATE_S = 4.0   # shortest gap between head-count updates for the same fire

    def __init__(self, folder, cooldown_s=15.0):
        self.folder, self.cooldown_s = folder, cooldown_s
        os.makedirs(folder, exist_ok=True)
        self.log = os.path.join(folder, "incidents.jsonl")
        self.last = {}   # kind -> (time, people)

    def report(self, kind, text, image, people, t):
        """Save the incident unless the same kind was reported moments ago. Returns the file name."""
        import cv2
        last = self.last.get(kind)
        recent = last is not None and 0 <= t - last[0] < self.cooldown_s
        # More people arriving at a fire is news even inside the cooldown, but not
        # more often than every few seconds while the head count settles.
        update = (kind == "fire_people" and last is not None
                  and people > last[1] and t - last[0] >= self.UPDATE_S)
        if recent and not update:
            return None
        self.last[kind] = (t, people)
        now = datetime.now()
        name = f"{now:%Y%m%d-%H%M%S}-{now.microsecond // 1000:03d}_{kind}.jpg"
        cv2.imwrite(os.path.join(self.folder, name), image)
        entry = {"time": now.isoformat(timespec="seconds"), "kind": kind, "text": text,
                 "people": people, "image": name}
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return name


# --- Live page -------------------------------------------------------------------

def _page(folder):
    entries = []
    try:
        with open(os.path.join(folder, "incidents.jsonl"), encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
    except OSError:
        pass
    rows = "".join(
        f'<div class="i"><a href="{html.escape(e["image"])}"><img src="{html.escape(e["image"])}"></a>'
        f'<div><b>{html.escape(e["text"])}</b><br>{html.escape(e["time"])}'
        f'<br>people in view: {int(e["people"])}</div></div>'
        for e in reversed(entries[-30:]))
    return f"""<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="3">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Incidents</title>
<style>body{{font:16px system-ui,sans-serif;background:#111;color:#eee;margin:16px}}
img{{max-width:100%;border-radius:6px}}.live{{max-width:720px}}
.i{{display:flex;gap:12px;margin:12px 0;padding:10px;background:#1c1c1c;border-left:4px solid #d33;border-radius:6px}}
.i img{{width:220px}}h1{{font-size:20px}}</style>
<h1>Live view</h1><img class="live" src="latest.jpg?{int(time.time())}" alt="waiting for the first frame">
<h1>Incidents ({len(entries)})</h1>{rows or "<p>None yet.</p>"}"""


class Live:
    """The newest annotated picture and what is in it, for other programs to show.

    With --serve PORT a dashboard can use:
      http://<address>:PORT/stream.mjpg    live video with boxes and alerts, e.g. <img src="...">
      http://<address>:PORT/status.json    {"people": 2, "alerts": {"person_down": "Person down"}, ...}
      http://<address>:PORT/incidents.jsonl  one line per saved incident, next to its screenshot
    """
    RATE = 12.0   # send at most this many pictures per second

    def __init__(self):
        self.changed = threading.Condition()
        self.jpeg = None
        self.number = 0
        self.status = {"people": 0, "alerts": {}, "fires": 0, "time": None}
        self.last = 0.0

    def publish(self, frame, scene):
        import cv2
        now = time.monotonic()
        status = {"time": datetime.now().isoformat(timespec="seconds"), "people": len(scene.people),
                  "fires": len(scene.fires), "alerts": dict(scene.alerts)}
        jpeg = None
        if now - self.last >= 1.0 / self.RATE:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                jpeg, self.last = buf.tobytes(), now
        with self.changed:
            self.status = status
            if jpeg is not None:
                self.jpeg, self.number = jpeg, self.number + 1
                self.changed.notify_all()


def serve(folder, port, live=None):
    """Serve the incidents folder as a small auto-refreshing web page, plus the live feeds."""
    import functools
    import http.server

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self.reply(_page(folder).encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/status.json" and live is not None:
                with live.changed:
                    body = json.dumps(live.status).encode("utf-8")
                self.reply(body, "application/json")
            elif path == "/stream.mjpg" and live is not None:
                self.stream()
            else:
                super().do_GET()

        def reply(self, body, kind):
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")   # so a dashboard elsewhere may read it
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seen = 0
            try:
                while True:
                    with live.changed:
                        if not live.changed.wait_for(lambda: live.number != seen, timeout=10):
                            continue
                        seen, jpeg = live.number, live.jpeg
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
            except OSError:
                pass   # the viewer closed the page

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), functools.partial(Handler, directory=folder))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def write_latest(folder, frame):
    import cv2
    tmp = os.path.join(folder, "latest.tmp.jpg")
    cv2.imwrite(tmp, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    try:
        os.replace(tmp, os.path.join(folder, "latest.jpg"))
    except OSError:
        pass  # a browser was reading it; the next frame will do


# --- Command line ------------------------------------------------------------------

def add_detector_args(ap):
    ap.add_argument("--model", default="yolo11n-pose.pt", help="pose model file or exported folder")
    ap.add_argument("--imgsz", type=int, default=640,
                    help="size the people model works at. Bigger sees smaller, far-away people: use 1280 "
                         "on a laptop for a 720p drone feed. Smaller is faster: 416 or 320 on the Pi")
    ap.add_argument("--view", choices=("oblique", "topdown"), default="oblique",
                    help="oblique: camera tilted forward (default). topdown: camera pointing straight down")
    ap.add_argument("--hold", type=float, default=vision.HOLD_S, help="seconds a posture must persist")
    ap.add_argument("--enhance", action="store_true", help="brighten dark footage before detection")
    ap.add_argument("--fire-sensitivity", choices=tuple(FireDetector.LEVELS), default="normal",
                    help="low: only large flickering flames. normal: also small distant fires that glow. "
                         "high: fainter glow, and fire-coloured things on people")
    ap.add_argument("--fire-model", help="YOLO model trained on fire, instead of the colour rule")
    ap.add_argument("--no-fire", action="store_true", help="switch fire detection off")


def build_monitor(args):
    pose = vision.Detector(args.model, args.imgsz, hold_s=args.hold, view=args.view)
    if args.no_fire:
        fire = NoFire()
    elif args.fire_model:
        fire = ModelFireDetector(args.fire_model, args.imgsz)
    else:
        fire = FireDetector(getattr(args, "fire_sensitivity", "normal"))
    return Monitor(pose, fire, args.enhance)


def main():
    ap = argparse.ArgumentParser(description="Watch a camera or video for emergencies.")
    ap.add_argument("--source", default="0",
                    help="camera index, video file, 'picam', or a stream address such as tcp://jpi.local:8554")
    ap.add_argument("--fps", type=float, help="video files only: look at this many frames per second")
    ap.add_argument("--size", default="640x480", help="picam frame size, e.g. 1280x720")
    ap.add_argument("--save", help="write the annotated video to this file")
    ap.add_argument("--no-show", action="store_true", help="no preview window (needed on a headless Pi)")
    ap.add_argument("--incidents", default="incidents", help="folder for incident screenshots")
    ap.add_argument("--cooldown", type=float, default=15.0, help="seconds before the same alert repeats")
    ap.add_argument("--serve", type=int, metavar="PORT", help="show live view and incidents as a web page")
    add_detector_args(ap)
    args = ap.parse_args()

    import cv2
    monitor = build_monitor(args)
    incidents = Incidents(args.incidents, args.cooldown)
    rec = vision.Recorder(args.save) if args.save else None
    live = Live() if args.serve else None
    if args.serve:
        serve(args.incidents, args.serve, live)
        print(f"Live page on port {args.serve}: http://<this computer's address>:{args.serve}"
              f"   (video for a dashboard: /stream.mjpg, alerts: /status.json)")
    size = tuple(int(v) for v in args.size.lower().split("x"))

    n = 0
    started = mark = time.monotonic()
    mark_n = 0
    last_latest = 0.0
    active = set()
    counts = {}
    try:
        for frame, t in vision.frames(args.source, args.fps, size):
            scene = monitor.process(frame, t)
            n += 1
            annotate(frame, scene)
            for kind, text in scene.alerts.items():
                saved = incidents.report(kind, text, frame, len(scene.people), t)
                if saved:
                    counts[kind] = counts.get(kind, 0) + 1
                    print(f"INCIDENT {text}  ->  {os.path.join(args.incidents, saved)}")
            for kind in active - set(scene.alerts):
                print(f"cleared: {kind}")
            active = set(scene.alerts)

            now = time.monotonic()
            if live:
                live.publish(frame, scene)
            if args.serve and now - last_latest >= 1.0:
                write_latest(args.incidents, frame)
                last_latest = now
            if now - mark >= 5.0:
                print(f"{(n - mark_n) / (now - mark):.1f} frames/s, {len(scene.people)} people in view")
                mark, mark_n = now, n
            if rec:
                rec.write(frame, t)
            if not args.no_show:
                cv2.imshow("emergency monitor (q to quit)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        if rec:
            rec.close()
        if not args.no_show:
            cv2.destroyAllWindows()

    elapsed = time.monotonic() - started
    if n:
        summary = ", ".join(f"{k} x{v}" for k, v in counts.items()) or "none"
        print(f"{n} frames in {elapsed:.0f}s ({n / elapsed:.1f} frames/s). Incidents: {summary}")


if __name__ == "__main__":
    main()
