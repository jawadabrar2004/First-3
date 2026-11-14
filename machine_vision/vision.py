"""People detection rules: person lying down, signalling for help, hands at throat.

This is the library. Run monitor.py to watch a camera, evaluate.py to score clips.

Uses a pretrained pose model, so there is nothing to train.

Known limits:
- Tilted camera: a person lying with their head pointing straight away from the
  camera looks upright. Look from the side or from a second angle.
- Straight-down camera: use view="topdown". Only "lying" works in that view.
- Hands at throat is a weak signal (eating, praying and phone use can look alike).
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass

LYING_ANGLE_DEG = 50.0  # torso tilt from vertical above which a person counts as lying
MIN_KP_CONF = 0.4       # ignore body points the model is unsure about
HOLD_S = 1.0            # lying or signalling must persist this long before it counts
CHOKE_HOLD_S = 2.0      # hands at throat must persist this long
GAP_S = 0.6             # missed detections shorter than this do not reset a timer
FORGET_S = 1.5          # drop a person not seen for this long
WAVE_WINDOW_S = 1.5     # look this far back for sideways hand movement
WAVE_RANGE = 0.10       # hand must travel this fraction of the person's size to count as waving
THROAT_REACH = 0.12     # both wrists within this fraction of the person's size of the neck
ARM_REACH = 0.20        # a raised wrist must be this fraction of the person's size from its shoulder
TOPDOWN_STRETCH = 1.6   # top-down view: box this much longer than wide means lying
TOPDOWN_TORSO = 1.0     # top-down view: torso at least this many shoulder-widths long means lying

# Body point indices in the pose model's output (COCO order).
NOSE, L_SH, R_SH, L_WR, R_WR, L_HIP, R_HIP = 0, 5, 6, 9, 10, 11, 12


# --- Rules (plain Python, testable without a camera or model) ---------------

def _posture_topdown(kpts, kconf, box, frame):
    """Straight-down camera: a standing person is a compact blob, a lying one shows full length."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    long_box = max(w, h) / max(1.0, min(w, h)) >= TOPDOWN_STRETCH
    if not all(kconf[i] >= MIN_KP_CONF for i in (L_SH, R_SH, L_HIP, R_HIP)):
        return "lying" if long_box else "upright"
    sx = (kpts[L_SH][0] + kpts[R_SH][0]) / 2
    sy = (kpts[L_SH][1] + kpts[R_SH][1]) / 2
    hx = (kpts[L_HIP][0] + kpts[R_HIP][0]) / 2
    hy = (kpts[L_HIP][1] + kpts[R_HIP][1]) / 2
    torso = math.hypot(sx - hx, sy - hy)
    shoulders = math.hypot(kpts[L_SH][0] - kpts[R_SH][0], kpts[L_SH][1] - kpts[R_SH][1])
    # Seen from above, a standing person's torso is hidden under their shoulders.
    if torso < TOPDOWN_TORSO * max(shoulders, 1.0) and not long_box:
        return "upright"
    if frame:
        # Away from the centre of the picture a standing person leans outwards (feet
        # towards the centre, head away) and can pass for a short lying person.
        cx, cy = (x1 + x2) / 2 - frame[0] / 2, (y1 + y2) / 2 - frame[1] / 2
        off_centre = math.hypot(cx, cy)
        if off_centre > 0.35 * math.hypot(frame[0], frame[1]) / 2 and torso > 0:
            outward = ((sx - hx) * cx + (sy - hy) * cy) / (torso * off_centre)
            if outward > 0.87:  # head points within 30 degrees of straight outwards
                return "upright"
    return "lying"


def posture(kpts, kconf, box, view="oblique", frame=None):
    """Return 'lying', 'upright' or 'unknown' for one person. frame is (width, height)."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if view == "topdown":
        return _posture_topdown(kpts, kconf, box, frame)
    if all(kconf[i] >= MIN_KP_CONF for i in (L_SH, R_SH, L_HIP, R_HIP)):
        sx = (kpts[L_SH][0] + kpts[R_SH][0]) / 2
        sy = (kpts[L_SH][1] + kpts[R_SH][1]) / 2
        hx = (kpts[L_HIP][0] + kpts[R_HIP][0]) / 2
        hy = (kpts[L_HIP][1] + kpts[R_HIP][1]) / 2
        dx, dy = hx - sx, hy - sy
        if math.hypot(dx, dy) > 0.15 * max(w, h):
            # 0 = hips straight below shoulders, 90 = sideways, 180 = upside down
            tilt = math.degrees(math.atan2(abs(dx), dy))
            return "lying" if tilt > LYING_ANGLE_DEG else "upright"
    # Torso not visible or too foreshortened: fall back to the box shape.
    if w > 1.3 * h:
        return "lying"
    if h > 1.3 * w:
        return "upright"
    return "unknown"


def _head_line(kpts, kconf, box):
    """Image height of the top of the head, or None if it cannot be judged."""
    if kconf[NOSE] >= MIN_KP_CONF:
        return kpts[NOSE][1]
    ys = [kpts[i][1] for i in (L_SH, R_SH) if kconf[i] >= MIN_KP_CONF]
    if not ys:
        return None
    return min(ys) - 0.1 * max(box[2] - box[0], box[3] - box[1])


def arm_raised(kpts, kconf, box=(0, 0, 0, 0)):
    """True if at least one wrist is above the head."""
    line = _head_line(kpts, kconf, box)
    if line is None:
        return False
    return any(kconf[i] >= MIN_KP_CONF and kpts[i][1] < line for i in (L_WR, R_WR))


def arms(kpts, kconf, box):
    """Return (both_up, sides).

    An arm counts as raised when its wrist is clearly above the head and well away
    from its shoulder. A hand at the face (drinking, phone, eating) does not count.

    both_up: both arms are raised.
    sides:   for the left and right arm, the wrist's sideways position relative
             to the body if that arm is raised, otherwise None.
    """
    size = max(box[2] - box[0], box[3] - box[1])
    line = _head_line(kpts, kconf, box)
    shoulders = [kpts[i][0] for i in (L_SH, R_SH) if kconf[i] >= MIN_KP_CONF]
    mid_x = sum(shoulders) / len(shoulders) if shoulders else (box[0] + box[2]) / 2
    sides = []
    for wr, sh in ((L_WR, L_SH), (R_WR, R_SH)):
        up = (line is not None
              and kconf[wr] >= MIN_KP_CONF and kconf[sh] >= MIN_KP_CONF
              and kpts[wr][1] < line - 0.03 * size
              and math.hypot(kpts[wr][0] - kpts[sh][0], kpts[wr][1] - kpts[sh][1]) >= ARM_REACH * size)
        sides.append(kpts[wr][0] - mid_x if up else None)
    return all(s is not None for s in sides), sides


def hands_at_throat(kpts, kconf, box):
    """True if both wrists are held at the neck, the common choking sign."""
    if not all(kconf[i] >= MIN_KP_CONF for i in (L_SH, R_SH, L_WR, R_WR)):
        return False
    size = max(box[2] - box[0], box[3] - box[1])
    nx = (kpts[L_SH][0] + kpts[R_SH][0]) / 2
    ny = (kpts[L_SH][1] + kpts[R_SH][1]) / 2
    for i in (L_WR, R_WR):
        if math.hypot(kpts[i][0] - nx, kpts[i][1] - ny) > THROAT_REACH * size:
            return False
        if kpts[i][1] > ny + 0.04 * size:  # hands on the chest, not the throat
            return False
    return True


def _spread(values):
    return max(values) - min(values) if len(values) >= 3 else 0.0


class _Timer:
    """How long a condition has held, tolerating short gaps."""

    def __init__(self):
        self.since = None
        self.last = None

    def update(self, on, t):
        if on:
            if self.last is None or t - self.last > GAP_S:
                self.since = t
            self.last = t
        if self.last is None or t - self.last > GAP_S:
            return 0.0
        return t - self.since


class _Track:
    def __init__(self):
        self.cx = self.cy = self.seen = 0.0
        self.lying = _Timer()
        self.raised = _Timer()
        self.choke = _Timer()
        self.wave = deque()  # (time, [left side, right side]) for recent frames


@dataclass
class Person:
    box: tuple
    score: float
    posture: str
    x: float              # centre of the person in the frame, -1 left .. +1 right
    y: float              # -1 top .. +1 bottom
    lying_s: float        # how long they have been lying
    raised_s: float       # how long they have been signalling (waving or both arms up)
    choking_s: float = 0.0  # how long both hands have been at the throat


@dataclass
class Target:
    kind: str             # 'lying', 'choking' or 'signalling'
    x: float
    y: float
    person: Person


class Detector:
    """Turns camera frames into people with timers, and one confirmed target (or None)."""

    def __init__(self, model="yolo11n-pose.pt", imgsz=640, conf=0.35, hold_s=HOLD_S, view="oblique"):
        self.imgsz, self.conf, self.hold_s, self.view = imgsz, conf, hold_s, view
        self.tracks = []
        self.model = None
        if model:
            from ultralytics import YOLO
            self.model = YOLO(model, task="pose")

    def detect(self, frame):
        """Run the pose model. Returns [(box, kpts, kconf, score), ...]."""
        r = self.model(frame, imgsz=self.imgsz, conf=self.conf, verbose=False)[0]
        if r.boxes is None or r.keypoints is None or len(r.boxes) == 0:
            return []
        boxes = r.boxes.xyxy.cpu().numpy().tolist()
        scores = r.boxes.conf.cpu().numpy().tolist()
        kxy = r.keypoints.xy.cpu().numpy().tolist()
        if r.keypoints.conf is None:
            kconf = [[1.0] * len(k) for k in kxy]
        else:
            kconf = r.keypoints.conf.cpu().numpy().tolist()
        return list(zip(boxes, kxy, kconf, scores))

    def process(self, frame, t):
        return self.update(self.detect(frame), frame.shape[1], frame.shape[0], t)

    def update(self, dets, width, height, t):
        """Apply the rules and timers. Returns (target or None, people)."""
        self.tracks = [k for k in self.tracks if t - k.seen <= FORGET_S]
        free = list(self.tracks)
        people = []
        for box, kpts, kconf, score in sorted(dets, key=lambda d: -d[3]):
            x1, y1, x2, y2 = box
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            size = max(x2 - x1, y2 - y1, 1.0)
            # Match to the nearest person from earlier frames, so timers carry over. The
            # allowance covers a moving camera: from a drone, a small far-away person
            # shifts by a good part of their own size between two analysed pictures.
            track = min(free, key=lambda k: math.hypot(k.cx - cx, k.cy - cy), default=None)
            if track is None or math.hypot(track.cx - cx, track.cy - cy) > max(1.0 * size, 0.04 * width):
                track = _Track()
                self.tracks.append(track)
            else:
                free.remove(track)
            track.cx, track.cy, track.seen = cx, cy, t

            pose = posture(kpts, kconf, box, self.view, (width, height))
            signalling = choking = False
            if pose != "lying" and self.view == "oblique":
                both_up, sides = arms(kpts, kconf, box)
                track.wave.append((t, sides))
                while t - track.wave[0][0] > WAVE_WINDOW_S:
                    track.wave.popleft()
                # Waving: a raised hand that has moved sideways recently.
                waving = any(
                    sides[i] is not None
                    and _spread([s[i] for _, s in track.wave if s[i] is not None]) >= WAVE_RANGE * size
                    for i in (0, 1))
                signalling = both_up or waving
                choking = hands_at_throat(kpts, kconf, box)
            else:
                track.wave.clear()

            people.append(Person(
                box=tuple(box), score=score, posture=pose,
                x=(cx - width / 2) / (width / 2),
                y=(cy - height / 2) / (height / 2),
                lying_s=track.lying.update(pose == "lying", t),
                raised_s=track.raised.update(signalling, t),
                choking_s=track.choke.update(choking, t),
            ))

        # A person on the ground outranks choking, which outranks signalling.
        for kind, pick in (
            ("lying", lambda p: p.lying_s >= self.hold_s),
            ("choking", lambda p: p.choking_s >= CHOKE_HOLD_S),
            ("signalling", lambda p: p.raised_s >= self.hold_s),
        ):
            found = [p for p in people if pick(p)]
            if found:
                p = max(found, key=lambda p: p.score)
                return Target(kind, p.x, p.y, p), people
        return None, people


# --- Camera, drawing, recording ------------------------------------------------

class _Stream:
    """Reads a network video stream in the background and keeps only the newest frame.

    Without this, a computer that analyses 12 frames a second while the camera
    sends 25 falls further and further behind. It also reconnects by itself when
    the link drops, which a drone's Wi-Fi will do.
    """
    RETRY_S = 1.0

    def __init__(self, url):
        import threading
        self.url = url
        self.frame = None
        self.count = 0          # frames received so far
        self.taken = 0          # count at the last frame handed out
        self.lock = threading.Lock()
        self.fresh = threading.Event()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        import os
        import cv2
        # Ask the decoder not to queue video up. A setting you made yourself wins.
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                              "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay")
        waiting = False
        while not self.stop.is_set():
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG,
                                   [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000,
                                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
            if not cap.isOpened():
                cap.release()
                if not waiting:
                    print(f"Waiting for the camera stream at {self.url} ...", flush=True)
                    waiting = True
                self.stop.wait(self.RETRY_S)
                continue
            waiting = False
            first = True
            while not self.stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    break
                if first:
                    print(f"Camera stream connected: {frame.shape[1]}x{frame.shape[0]}", flush=True)
                    first = False
                with self.lock:
                    self.frame = frame
                    self.count += 1
                self.fresh.set()
            cap.release()
            if not self.stop.is_set():
                print("Camera stream lost, reconnecting ...", flush=True)
                self.stop.wait(self.RETRY_S)

    def latest(self, timeout=0.2):
        """The newest frame not handed out before, or None if nothing new arrived in time."""
        if not self.fresh.wait(timeout):
            return None
        with self.lock:
            self.fresh.clear()
            self.taken = self.count
            return self.frame

    def close(self):
        self.stop.set()
        self.thread.join(timeout=10)


def frames(source, sample_fps=None, size=(640, 480), max_width=1280):
    """Yield (frame, time_in_seconds) from a webcam index, a video file, 'picam', or a
    network stream address such as tcp://jpi.local:8554 or rtsp://...

    For video files, sample_fps keeps only that many frames per second of video,
    which is what a slower computer such as the Pi would actually get to see.
    A network stream is live: you always get the newest picture, and older ones
    that arrived while the last one was being analysed are skipped.
    """
    if "://" in str(source):
        import cv2
        stream = _Stream(source)
        try:
            while True:
                frame = stream.latest()
                if frame is None:
                    # Nothing new (link down or slow): keep any preview window alive.
                    try:
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            return
                    except cv2.error:
                        pass   # no window support on this computer (headless Pi)
                    continue
                if frame.shape[1] > max_width:
                    scale = max_width / frame.shape[1]
                    frame = cv2.resize(frame, (max_width, int(frame.shape[0] * scale)),
                                       interpolation=cv2.INTER_AREA)
                yield frame, time.monotonic()
        finally:
            stream.close()
        return

    if source == "picam":
        from picamera2 import Picamera2
        cam = Picamera2()
        # picamera2's "RGB888" arrives in the blue-green-red order OpenCV expects.
        cam.configure(cam.create_video_configuration(main={"size": tuple(size), "format": "RGB888"}))
        cam.start()
        try:
            while True:
                yield cam.capture_array(), time.monotonic()
        finally:
            cam.stop()
        return

    import cv2
    live = str(source).isdigit()
    cap = cv2.VideoCapture(int(source) if live else source)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open video source {source!r}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps != fps or fps > 240:
        fps = 30.0
    stride = 1 if live or not sample_fps else max(1, round(fps / sample_fps))
    n = 0
    try:
        while True:
            if n % stride:
                if not cap.grab():
                    break
            else:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame.shape[1] > max_width:
                    scale = max_width / frame.shape[1]
                    frame = cv2.resize(frame, (max_width, int(frame.shape[0] * scale)),
                                       interpolation=cv2.INTER_AREA)
                yield frame, (time.monotonic() if live else n / fps)
            n += 1
    finally:
        cap.release()


_clahe = None


def enhance(frame):
    """Lift detail in dark footage so the pose model has more to work with."""
    import cv2
    global _clahe
    if _clahe is None:
        _clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    light, a, b = cv2.split(cv2.cvtColor(frame, cv2.COLOR_BGR2LAB))
    return cv2.cvtColor(cv2.merge((_clahe.apply(light), a, b)), cv2.COLOR_LAB2BGR)


def draw(frame, people, target, aim=True):
    """Draw boxes and labels onto the frame. aim=True also marks the kit release point."""
    import cv2
    h, w = frame.shape[:2]
    for p in people:
        is_target = target is not None and target.person is p
        pending = p.lying_s > 0 or p.raised_s > 0 or p.choking_s > 0
        if is_target:
            colour, thick = (0, 0, 255), 3
        elif pending:
            colour, thick = (0, 165, 255), 2
        else:
            colour, thick = (0, 200, 0), 2
        x1, y1, x2, y2 = (int(v) for v in p.box)
        cv2.rectangle(frame, (x1, y1), (x2, y2), colour, thick)
        label = p.posture
        if p.lying_s > 0:
            label = f"lying {p.lying_s:.1f}s"
        elif p.choking_s > 0:
            label = f"hands at throat {p.choking_s:.1f}s"
        elif p.raised_s > 0:
            label = f"signalling {p.raised_s:.1f}s"
        cv2.putText(frame, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
    if aim:
        from guidance import DROP_Y
        ax, ay = w // 2, int((DROP_Y + 1) / 2 * h)
        cv2.drawMarker(frame, (ax, ay), (255, 255, 255), cv2.MARKER_CROSS, 24, 2)
        if target:
            text = f"TARGET {target.kind}  x={target.x:+.2f}  y={target.y:+.2f}"
            cv2.putText(frame, text, (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    return frame


class Recorder:
    """Saves frames so the video plays at real speed, whatever the processing rate."""

    def __init__(self, path, fps=15):
        self.path, self.fps = path, fps
        self.writer = None
        self.t0 = None
        self.written = 0

    def write(self, frame, t):
        import cv2
        if self.writer is None:
            h, w = frame.shape[:2]
            self.writer = cv2.VideoWriter(self.path, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))
            self.t0 = t
        due = int((t - self.t0) * self.fps) + 1
        while self.written < due:
            self.writer.write(frame)
            self.written += 1

    def close(self):
        if self.writer is not None:
            self.writer.release()
