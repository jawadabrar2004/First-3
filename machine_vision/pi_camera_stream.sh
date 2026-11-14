#!/bin/bash
# Run this ON THE RASPBERRY PI. It sends the Pi camera to whichever computer connects
# to port 8554, and starts again by itself when that computer disconnects or the
# Wi-Fi drops.
#
#   bash pi_camera_stream.sh
#
# Then on the laptop:
#   python monitor.py --source tcp://<pi address>:8554
#
# 1280x720 keeps far-away people large enough to recognise. If the picture is
# upside down on the drone, add:  --vflip --hflip
PORT=${PORT:-8554}
CMD=$(command -v rpicam-vid || command -v libcamera-vid)
if [ -z "$CMD" ]; then
    echo "rpicam-vid not found. Install it with: sudo apt install rpicam-apps" >&2
    exit 1
fi
echo "Sending the camera on port $PORT. Stop with Ctrl+C."
trap 'exit 0' INT TERM
while true; do
    "$CMD" -t 0 -n --width 1280 --height 720 --framerate 15 \
        --bitrate 2500000 --intra 15 --inline --flush \
        --listen -o "tcp://0.0.0.0:$PORT" "$@"
    sleep 1
done
