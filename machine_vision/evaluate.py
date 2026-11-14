"""Score the detector on a folder of clips, so you know how reliable it is.

Put each clip in a folder named after what SHOULD be detected in it:

    clips/person_down/   clips/waving/   clips/choking/
    clips/fire/          clips/fire_people/
    clips/none/          ordinary scenes: any alert here is a false alarm

Put "topdown" in the file name of clips filmed straight down (most stock drone
footage of a person lying). Everything else is treated as a tilted camera.

Then:   python evaluate.py clips

A screenshot of each first alert goes to eval_out/ so you can see what it
reacted to. Run the same command on the Pi to get its real frames per second.
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import time

import monitor as mon
import vision

VIDEO = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v")
EXPECTED = {
    "person_down": {"person_down"},
    "waving": {"waving"},
    "choking": {"choking"},
    "fire": {"fire", "fire_people"},
    "fire_people": {"fire_people"},
    "none": set(),
}


def find_clips(root):
    """Yield (path, label). The label is the clip's folder name, or '?' if it is not a known one."""
    for folder, _, files in sorted(os.walk(root)):
        label = os.path.basename(os.path.normpath(folder))
        for name in sorted(files):
            if name.lower().endswith(VIDEO):
                yield os.path.join(folder, name), (label if label in EXPECTED else "?")


def run_clip(path, label, monitor, fps, out_dir):
    """Run one clip. Returns ({kind: first time it fired}, frames looked at, seconds taken)."""
    import cv2
    monitor.reset()
    first = {}
    frames = 0
    started = time.monotonic()
    stem = os.path.splitext(os.path.basename(path))[0]
    for frame, t in vision.frames(path, fps or None):
        scene = monitor.process(frame, t)
        frames += 1
        for kind in scene.alerts:
            if kind not in first:
                first[kind] = t
                shot = mon.annotate(frame.copy(), scene)
                cv2.imwrite(os.path.join(out_dir, f"{label}__{stem}__{kind}.jpg"), shot)
    return first, frames, time.monotonic() - started


def judge(label, fired):
    expected = EXPECTED.get(label)
    if expected is None:
        return "-"
    if not expected:
        return "FALSE ALARM" if fired else "ok (quiet)"
    return "ok" if expected & set(fired) else "MISSED"


def main():
    ap = argparse.ArgumentParser(description="Score the detector on labelled clips.")
    ap.add_argument("clips", help="folder of clips, sorted into sub-folders by expected alert")
    ap.add_argument("--fps", type=float, default=6.0,
                    help="frames per second of video to look at; about what the Pi manages. 0 = every frame")
    ap.add_argument("--out", default="eval_out", help="folder for screenshots and results.csv")
    mon.add_detector_args(ap)
    args = ap.parse_args()

    clips = list(find_clips(args.clips))
    if not clips:
        raise SystemExit(f"No video files found under {args.clips!r}")
    os.makedirs(args.out, exist_ok=True)
    monitor = mon.build_monitor(args)

    rows = []
    total_frames = total_seconds = 0.0
    print(f"{'clip':40s} {'expect':12s} {'result':12s} {'first alert':12s} also fired")
    for path, label in clips:
        # A clip with "topdown" or "oblique" in its name or folder overrides --view.
        lowered = path.lower()
        monitor.pose.view = next((v for v in ("topdown", "oblique") if v in lowered), args.view)
        first, frames, seconds = run_clip(path, label, monitor, args.fps, args.out)
        total_frames += frames
        total_seconds += seconds
        result = judge(label, first)
        expected = EXPECTED.get(label) or set()
        hits = [first[k] for k in first if k in expected]
        when = f"{min(hits):.1f}s" if hits else ""
        extra = sorted(k for k in first if k not in expected)
        name = os.path.relpath(path, args.clips)
        print(f"{name[-40:]:40s} {label:12s} {result:12s} {when:12s} {', '.join(extra)}")
        rows.append({"clip": name, "expected": label, "result": result,
                     "first_alert_s": f"{min(hits):.2f}" if hits else "",
                     "fired": " ".join(f"{k}@{v:.1f}s" for k, v in sorted(first.items())),
                     "frames": frames, "frames_per_s": f"{frames / seconds:.1f}" if seconds else ""})

    with open(os.path.join(args.out, "results.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print("\nSummary")
    for label in EXPECTED:
        mine = [r for r in rows if r["expected"] == label]
        if not mine:
            continue
        if label == "none":
            bad = sum(r["result"] == "FALSE ALARM" for r in mine)
            print(f"  {label:12s} false alarms in {bad} of {len(mine)} clips")
        else:
            good = [r for r in mine if r["result"] == "ok"]
            delay = statistics.median(float(r["first_alert_s"]) for r in good) if good else None
            tail = f", typical time to alert {delay:.1f}s" if delay is not None else ""
            print(f"  {label:12s} detected in {len(good)} of {len(mine)} clips{tail}")
    if total_seconds:
        print(f"  speed        {total_frames / total_seconds:.1f} frames/s on this computer")
    print(f"Screenshots and results.csv are in {args.out}{os.sep}")


if __name__ == "__main__":
    main()
