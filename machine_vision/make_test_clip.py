"""Make a short test clip for mock mode: machine_vision/test_clip.mp4

The dispatch console's mock mode can't give monitor.py the laptop webcam (the
browser is already using it), so monitor.py watches this clip instead.

Built from the two sample photos that come with the ultralytics package, so
nothing has to be downloaded:
   0- 6 s  people standing                (people count, no alert)
   6-13 s  the bus photo turned on its side, so its people look like
           they're lying down             (person_down)
  13-17 s  flickering flames on a dark background  (meant for fire; too
           synthetic to trigger it in testing, so expect person_down only)
  17-20 s  people standing again

Run from the project folder:   python machine_vision/make_test_clip.py
Any other clip works too: save it as machine_vision/test_clip.mp4, or point
the VISION_MOCK_SOURCE environment variable at it.
"""
import os

import cv2
import numpy as np
from ultralytics.utils import ASSETS

W, H, FPS = 1280, 720, 30
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_clip.mp4")


def fit(img):
    """Scale an image to fill the frame, cropping the edges."""
    h, w = img.shape[:2]
    scale = max(W / w, H / h)
    img = cv2.resize(img, (int(w * scale) + 1, int(h * scale) + 1))
    y, x = (img.shape[0] - H) // 2, (img.shape[1] - W) // 2
    return img[y:y + H, x:x + W]


def slow_zoom(img, i, n):
    """A gentle zoom, so the picture isn't perfectly still."""
    z = 1.0 + 0.06 * i / max(1, n)
    m = cv2.getRotationMatrix2D((W / 2, H / 2), 0, z)
    return cv2.warpAffine(img, m, (W, H), borderMode=cv2.BORDER_REFLECT)


def flames(i, rng):
    """Flickering orange and yellow blobs on a dark yard."""
    frame = np.full((H, W, 3), (25, 30, 28), np.uint8)
    for k in range(9):
        cx = 640 + int(70 * np.sin(i * 0.3 + k)) + rng.integers(-15, 15)
        cy = 520 - k * 28 + rng.integers(-10, 10)
        r = max(18, 95 - k * 9 + int(rng.integers(-12, 12)))
        color = (0, int(120 + k * 14 + rng.integers(0, 30)), 255)          # BGR: orange -> yellow
        cv2.ellipse(frame, (cx, cy), (r, int(r * 1.6)), 0, 0, 360, color, -1)
    cv2.ellipse(frame, (640, 560), (60, 40), 0, 0, 360, (210, 245, 255), -1)  # hot white core
    return cv2.GaussianBlur(frame, (21, 21), 0)


def main():
    people = fit(cv2.imread(str(ASSETS / "zidane.jpg")))
    lying = fit(cv2.rotate(cv2.imread(str(ASSETS / "bus.jpg")), cv2.ROTATE_90_CLOCKWISE))
    rng = np.random.default_rng(1)
    out = cv2.VideoWriter(OUT, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    parts = [(people, 6), (lying, 7), (None, 4), (people, 3)]   # (picture or None=fire, seconds)
    for img, seconds in parts:
        n = seconds * FPS
        for i in range(n):
            out.write(flames(i, rng) if img is None else slow_zoom(img, i, n))
    out.release()
    print(f"Wrote {OUT} ({sum(s for _, s in parts)} s)")


if __name__ == "__main__":
    main()
