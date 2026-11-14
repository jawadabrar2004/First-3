// =====================================================================
// config.js - the ONE place to change where the drone video comes from.
// =====================================================================

// ---------------------------------------------------------------------
// 1. Which video to show
//    "pi"   - live cameras on the Raspberry Pi (MediaMTX), Day + IR
//    "mock" - no Pi needed: uses VIDEO_SOURCE below (laptop webcam by default)
// ---------------------------------------------------------------------
const VIDEO_MODE = "pi";

// Log every camera status check and every video iframe change in the
// browser console (F12). Leave false normally; turn on to debug the feeds.
const DEBUG_CAMERA = false;

// ---------------------------------------------------------------------
// 2. Where the Pi is
//    Usually "raspberrypi.local". On a phone hotspot that name can resolve
//    to IPv6, and WebRTC may then fail. If the video won't load, run
//    `hostname -I` on the Pi and put its IPv4 address here instead,
//    e.g. "192.168.43.120".
//    Keep this the same as PI_HOST on the server (main.py / env var PI_HOST).
// ---------------------------------------------------------------------
const PI_HOST = "raspberrypi.local";

// All Pi stream addresses are built from PI_HOST. You shouldn't need to edit these.
const PI_URL_HOST = PI_HOST.includes(":") && !PI_HOST.startsWith("[") ? "[" + PI_HOST + "]" : PI_HOST; // IPv6 needs [brackets]
const PI_STREAMS = {
  day: "http://" + PI_URL_HOST + ":8889/cam/",      // WebRTC page, day camera (trailing / skips a redirect)
  ir: "http://" + PI_URL_HOST + ":8889/ir/",        // WebRTC page, IR camera
  dayRtsp: "rtsp://" + PI_URL_HOST + ":8554/cam",   // RTSP, for computer vision later
  irRtsp: "rtsp://" + PI_URL_HOST + ":8554/ir",
};
// Asks MediaMTX's player page to hide its own controls and start playing muted
const PI_PLAYER_PARAMS = "?controls=false&muted=true&autoplay=true&playsinline=true";

// ---------------------------------------------------------------------
// Machine vision (machine_vision/monitor.py). main.py starts it on this
// computer when the drone enters the search zone; the page reads its live
// view and status from here. Change the host only if monitor.py runs on
// another computer.
// ---------------------------------------------------------------------
const VISION_HOST = "localhost";
const VISION_PORT = 8100;   // http://localhost:8100/stream.mjpg and /status.json

// ---------------------------------------------------------------------
// 3. Mock mode video (used when VIDEO_MODE = "mock")
//
//   "webcam" - the laptop's own camera, used as a pretend drone camera.
//              Picks the built-in camera automatically. To force a specific
//              camera, put part of its name in `camera`,
//              e.g. { type: "webcam", camera: "AVStream" }
//   "mjpeg"  - MJPEG stream from a Raspberry Pi or ESP32-CAM, shown in an <img>.
//              e.g. { type: "mjpeg", url: "http://192.168.1.50:81/stream" }
//   "webrtc" - any WebRTC player page, shown in an <iframe>.
//   "file"   - a looping demo video. Put the mp4 in static/ and point at it.
//              e.g. { type: "file", url: "/static/demo.mp4" }
// ---------------------------------------------------------------------
const VIDEO_SOURCE = {
  type: "webcam",
  url: "",
  camera: "", // optional: part of the camera's name. Empty = the laptop's built-in camera
};
