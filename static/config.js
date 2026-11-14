// =====================================================================
// config.js - the ONE place to change where the drone video comes from.
//
// Pick a type and (if needed) a url:
//
//   "webcam" - the laptop's own camera, used as a pretend drone camera.
//              Picks the built-in camera automatically. To force a specific
//              camera, put part of its name in `camera`,
//              e.g. { type: "webcam", camera: "AVStream" }
//   "mjpeg"  - MJPEG stream from a Raspberry Pi or ESP32-CAM, shown in an <img>.
//              e.g. { type: "mjpeg", url: "http://192.168.1.50:81/stream" }
//   "webrtc" - MediaMTX WebRTC page on the Pi, shown in an <iframe>.
//              e.g. { type: "webrtc", url: "http://raspberrypi.local:8889/cam" }
//   "file"   - a looping demo video. Put the mp4 in static/ and point at it.
//              e.g. { type: "file", url: "/static/demo.mp4" }
//
// Switching to the real drone later = edit the lines below, save, reload the page.
// =====================================================================

const VIDEO_SOURCE = {
  type: "webcam",
  url: "",
  camera: "", // optional: part of the camera's name. Empty = the laptop's built-in camera
};
