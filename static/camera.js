// =====================================================================
// camera.js - the Raspberry Pi cameras (Day + IR) and the Day/IR switch.
//
//   * VIDEO_MODE "pi":   shows the Pi's MediaMTX player page in an <iframe>.
//                        Only one stream is loaded at a time; switching
//                        replaces it. Every 5 s we ask the server whether the
//                        Pi is reachable (/api/camera-status). If it isn't,
//                        we show CAMERA OFFLINE and reconnect when it's back.
//   * VIDEO_MODE "mock": video.js shows the laptop webcam. The switch then just
//                        turns the picture grey, so the IR toggle can be demoed.
//
//   Press I (or click Day / IR in the bottom bar) to switch cameras.
//   The last choice is remembered in this browser.
// =====================================================================

const CAM_NAMES = { day: "DAY CAM", ir: "IR CAM" };
const CAM_STORAGE_KEY = "first3.cameraMode";
const CAM_CHECK_EVERY_MS = 5000;

let camMode = loadCamMode();  // "day" or "ir"
let camOnline = null;         // null = not checked yet, then true / false
let connectTimer = null;

// ---------------------------------------------------------------------
// Remember Day / IR between page loads (storage can be blocked, so try/catch)
// ---------------------------------------------------------------------
function loadCamMode() {
  try {
    return localStorage.getItem(CAM_STORAGE_KEY) === "ir" ? "ir" : "day";
  } catch (err) {
    return "day";
  }
}

function saveCamMode(mode) {
  try {
    localStorage.setItem(CAM_STORAGE_KEY, mode);
  } catch (err) {
    // not saved; it will just start on Day next time
  }
}

// ---------------------------------------------------------------------
// Switching Day / IR
// ---------------------------------------------------------------------
function setCameraMode(mode) {
  camMode = mode;
  saveCamMode(mode);
  updateCamControls();
  if (VIDEO_MODE === "pi") {
    if (camOnline !== false) loadPiStream(); // when offline, the next status check reconnects
  } else {
    // Mock: grey picture = pretend IR
    document.querySelector(".video-layer").classList.toggle("ir-mode", mode === "ir");
  }
}

function toggleCameraMode() {
  setCameraMode(camMode === "day" ? "ir" : "day");
}

// Day / IR buttons in the bottom bar
document.querySelectorAll(".cam-btn").forEach((btn) => {
  btn.addEventListener("click", () => setCameraMode(btn.dataset.cam));
});

// Keyboard shortcut: I (ignored while typing, e.g. in the address box)
document.addEventListener("keydown", (e) => {
  if (e.key !== "i" && e.key !== "I") return;
  if (e.ctrlKey || e.metaKey || e.altKey || e.repeat) return;
  const t = e.target;
  if (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
  toggleCameraMode();
});

// Label in the corner of the video + which button looks pressed
function updateCamControls() {
  document.getElementById("cam-label").textContent = CAM_NAMES[camMode];
  document.querySelectorAll(".cam-btn").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(btn.dataset.cam === camMode));
  });
}

// ---------------------------------------------------------------------
// Loading the Pi stream
// ---------------------------------------------------------------------
function loadPiStream() {
  const url = PI_STREAMS[camMode] + PI_PLAYER_PARAMS;
  showCamMessage("connecting", "Connecting to " + CAM_NAMES[camMode] + "…");

  const frame = document.createElement("iframe");
  frame.title = "Drone camera (" + CAM_NAMES[camMode] + ")";
  frame.allow = "autoplay; fullscreen";
  frame.src = url;

  // The player page has loaded; give the video a moment to start, then
  // hide "connecting". Never leave the message up for more than 10 s.
  clearTimeout(connectTimer);
  frame.addEventListener("load", () => {
    clearTimeout(connectTimer);
    connectTimer = setTimeout(hideCamMessage, 1500);
  });
  connectTimer = setTimeout(hideCamMessage, 10000);

  document.getElementById("video-stage").replaceChildren(frame); // replaces the old stream
  setVideoLabel(CAM_NAMES[camMode] + " · " + PI_HOST); // video.js: shown in the Telemetry box
}

function unloadPiStream() {
  clearTimeout(connectTimer);
  document.getElementById("video-stage").replaceChildren();
}

// Message in the middle of the video: "connecting" or "offline"
function showCamMessage(kind, text) {
  const box = document.getElementById("cam-message");
  box.className = "cam-message cam-message-" + kind;
  box.textContent = text;
  box.hidden = false;
}

function hideCamMessage() {
  document.getElementById("cam-message").hidden = true;
}

// ---------------------------------------------------------------------
// Is the Pi reachable? Asked every 5 s.
// ---------------------------------------------------------------------
async function checkCamera() {
  let data;
  try {
    const res = await fetch("/api/camera-status");
    data = await res.json();
  } catch (err) {
    setCamStatus(null, "Can't reach the dispatch server");
    return; // server down: leave the video as it is
  }

  if (data.host !== PI_HOST) {
    console.warn("PI_HOST differs: static/config.js has", PI_HOST, "but the server checks", data.host);
  }
  setCamStatus(data.online, (data.online ? "Pi camera online at " : "Pi camera offline at ") + data.host + ":" + data.port);

  if (data.online && camOnline !== true) {
    camOnline = true;
    loadPiStream();            // first connect, or the Pi came back
  } else if (!data.online && camOnline !== false) {
    camOnline = false;
    unloadPiStream();
    showCamMessage("offline", "CAMERA OFFLINE - check Pi / Wi-Fi");
  }
}

// Dot in the header: green = online, red = offline, grey = unknown / mock
function setCamStatus(online, detail) {
  const el = document.getElementById("cam-status");
  el.className = "conn " + (online === true ? "conn-live" : online === false ? "conn-down" : "conn-offline");
  document.getElementById("cam-status-text").textContent =
    online === true ? "CAM" : online === false ? "CAM OFFLINE" : VIDEO_MODE === "pi" ? "CAM ?" : "CAM MOCK";
  el.title = detail;
}

// ---------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------
updateCamControls();
if (VIDEO_MODE === "pi") {
  showCamMessage("connecting", "Connecting to " + CAM_NAMES[camMode] + "…");
  checkCamera();
  setInterval(checkCamera, CAM_CHECK_EVERY_MS);
} else {
  setCamStatus(null, "Mock mode: using " + VIDEO_SOURCE.type + " (VIDEO_MODE in static/config.js)");
  setCameraMode(camMode); // applies the grey "IR" look if IR was last used
}
