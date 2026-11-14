# Machine vision: emergency detection from the drone camera

Watches a camera feed and raises an alert, with a screenshot, for:

| Alert | Meaning |
|---|---|
| `person_down` | someone lying on the ground |
| `waving` | someone waving, or holding both arms up |
| `choking` | both hands held at the throat (weak signal) |
| `fire` / `fire_people` | flames, with a count of the people in view |

## Files

| File | What it is |
|---|---|
| `monitor.py` | **The one script to run.** Reads the camera, draws boxes and alerts, saves incidents, serves the live video. |
| `vision.py` | People rules and camera reading. Used by `monitor.py`. |
| `evaluate.py` | Scores a folder of test clips, so you can measure changes. |
| `pi_camera_stream.sh` | Run on the Pi to send its camera to another computer. |
| `yolo11n-pose.pt` | The people model. |
| `yolo11n-pose_ncnn_model/` | The same model in a faster format for a Pi 5. |

## Install

```
python -m venv .venv
.venv\Scripts\activate          (Windows)      source .venv/bin/activate   (Mac, Linux)
pip install -r requirements.txt
```

On a Pi, create the environment with `python3 -m venv --system-site-packages venv`
so the Pi camera library stays visible.

## Run

**Pi sends the camera, a laptop does the detection** (the only option for a Pi Zero 2 W):

```
On the Pi:      bash pi_camera_stream.sh
On the laptop:  python monitor.py --source tcp://<pi address>:8554 --imgsz 1280 --serve 8100
```

Both must be on the same network. The laptop reconnects by itself if the link drops.

**Everything on a Pi 5:**

```
python monitor.py --source picam --size 1280x720 --model yolo11n-pose_ncnn_model --no-show --serve 8100
```

**Laptop webcam, or a video file:**

```
python monitor.py
python monitor.py --source some_clip.mp4 --fps 6
```

Press `q` in the preview window to quit. Screenshots go to `incidents/`.

## Plugging into the dashboard

With `--serve 8100`, `monitor.py` offers these addresses (8100 because the dashboard uses 8000):

| Address | What it gives |
|---|---|
| `http://localhost:8100/stream.mjpg` | Live video with boxes and alerts drawn in. Works in an `<img>` tag. |
| `http://localhost:8100/status.json` | `{"time": "...", "people": 2, "fires": 0, "alerts": {"person_down": "Person down"}}` |
| `http://localhost:8100/incidents.jsonl` | One line per saved incident; the screenshot is at `/<image name>`. |

In the dashboard's `static/config.js`:

```js
const VIDEO_SOURCE = { type: "mjpeg", url: "http://localhost:8100/stream.mjpg" };
```

Replace `localhost` with the other computer's address if `monitor.py` runs elsewhere.

## Options that matter

| Option | Use |
|---|---|
| `--imgsz 1280` | Sees people about twice as far away as the default 640, at about half the speed. |
| `--fire-sensitivity low` / `normal` / `high` | `low`: only large flickering flames. `normal` (default): also small distant fires that glow. `high`: fainter glow, and fire-coloured things on people. |
| `--no-fire` | Switch fire detection off. |
| `--view topdown` | Only if the camera points straight down. The default assumes a camera tilted about 45 degrees. |
| `--no-show` | No preview window (needed over SSH). |

## Limits found in testing

- **Distance.** A lying person must span about 12% of the picture width at the default
  size, about 7% with `--imgsz 1280`. With a standard Pi camera tilted 45 degrees that
  is roughly 8 m and 15 m of altitude. Higher than that, people are missed.
- **Direction.** With a tilted camera, a person lying with their head pointing straight
  away from the camera looks upright and is missed. Look from a second direction.
- **Bending over** can be read as lying down.
- **Fire** must be clearly brighter than its surroundings. A small bright orange-and-white
  object against a dark background can still pass. Fire-coloured things on a person are
  ignored, so to test with fire on a phone screen, prop the phone up instead of holding it.
- Tested on a laptop with recorded clips and a simulated Pi stream. `pi_camera_stream.sh`
  and the Pi 5 route have not been run on a real Pi with this version.
