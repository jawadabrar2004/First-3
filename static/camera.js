// =====================================================================
// camera.js - the Raspberry Pi cameras, shown side by side:
//             Day on the left, IR on the right.
//
//   * VIDEO_MODE "pi":   when the feeds load depends on the Cameras switch
//                        (bottom bar; starts as CAMERAS_ALWAYS_ON in config.js):
//                          On   - as soon as the page opens and the Pi is online,
//                                 on every screen
//                          Auto - only once the drone is in the search zone
//                                 (telemetry.cameras_active; app.js calls
//                                 setCamerasActive). Before that the blurred placeholder shows.
//                        Each pane shows one MediaMTX player page in an
//                        <iframe>. Each iframe is created ONCE and then left
//                        alone: removing or re-creating it restarts the video.
//                        Every 5 s we ask the server whether the Pi is
//                        reachable (/api/camera-status):
//                          - 1-2 failed checks in a row: keep the video playing,
//                            header dot turns yellow ("CAM ?")
//                          - 3 failed checks in a row: CAMERA OFFLINE (feeds removed)
//                          - back online after being offline: feeds load again
//   * VIDEO_MODE "mock": video.js puts the laptop webcam in the Day pane and
//                        we copy it into the IR pane in grey.
//
//   Also here: the T key folds / unfolds the Telemetry box.
//   Set DEBUG_CAMERA = true in config.js to log every check and every
//   iframe change in the browser console (F12).
// =====================================================================

const FEEDS = ["day", "ir"];
const CAM_NAMES = { day: "DAY CAM", ir: "IR CAM" };
const CAM_CHECK_EVERY_MS = 5000;
const OFFLINE_AFTER_FAILS = 3;     // failed checks in a row before we call it offline

let camState = "unknown";          // "unknown" | "online" | "unsure" | "offline"
let failedChecks = 0;              // failed checks in a row (reset on success)
let warnedHostMismatch = false;
let zoneActive = false;            // true once the drone has entered the search zone
let camerasAlwaysOn = typeof CAMERAS_ALWAYS_ON === "undefined" ? false : CAMERAS_ALWAYS_ON; // "On" vs "Auto"

// Should the Pi feeds be loaded right now?
function camerasWanted() {
  return camerasAlwaysOn || zoneActive;
}
const loadedFrames = {};           // feed -> its <iframe>, while loaded
const connectTimers = {};          // feed -> timer that hides "connecting"
const cameraStats = { created: { day: 0, ir: 0 }, loadEvents: { day: 0, ir: 0 }, removed: { day: 0, ir: 0 } };
window.cameraStats = cameraStats;  // type cameraStats in the console to see the counts

// Console logging with a timestamp, only when DEBUG_CAMERA is on
function camLog(...args) {
  if (typeof DEBUG_CAMERA === "undefined" || !DEBUG_CAMERA) return;
  console.log("[camera " + new Date().toISOString().slice(11, 23) + "]", ...args);
}

// ---------------------------------------------------------------------
// Pi streams
// ---------------------------------------------------------------------
function loadPiStream(feed) {
  if (loadedFrames[feed]) {
    camLog("load skipped,", feed, "is already loaded"); // never reload a playing feed
    return;
  }
  showCamMessage(feed, "connecting", "Connecting to " + CAM_NAMES[feed] + "…");

  const frame = document.createElement("iframe");
  frame.title = "Drone camera (" + CAM_NAMES[feed] + ")";
  frame.allow = "autoplay; fullscreen";
  frame.src = PI_STREAMS[feed] + PI_PLAYER_PARAMS; // the only place src is ever set

  // The player page has loaded; give the video a moment to start, then
  // hide "connecting". Never leave the message up for more than 10 s.
  clearTimeout(connectTimers[feed]);
  frame.addEventListener("load", () => {
    cameraStats.loadEvents[feed]++;
    if (cameraStats.loadEvents[feed] > cameraStats.created[feed]) {
      camLog("WARNING:", feed, "iframe loaded again without being re-created (it reloaded itself)");
    } else {
      camLog(feed, "iframe page loaded");
    }
    clearTimeout(connectTimers[feed]);
    connectTimers[feed] = setTimeout(() => hideCamMessage(feed), 1500);
  });
  connectTimers[feed] = setTimeout(() => hideCamMessage(feed), 10000);

  document.getElementById("feed-" + feed).replaceChildren(frame);
  loadedFrames[feed] = frame;
  cameraStats.created[feed]++;
  camLog("iframe CREATED:", feed, frame.src, "(created", cameraStats.created[feed], "time(s) so far)");
}

function unloadPiStream(feed) {
  clearTimeout(connectTimers[feed]);
  if (!loadedFrames[feed]) return;
  loadedFrames[feed].remove();
  delete loadedFrames[feed];
  cameraStats.removed[feed]++;
  camLog("iframe REMOVED:", feed);
}

// Message in the middle of a pane: "connecting" or "offline"
function showCamMessage(feed, kind, text) {
  const box = document.getElementById("msg-" + feed);
  box.className = "cam-message cam-message-" + kind;
  box.textContent = text;
  box.hidden = false;
}

function hideCamMessage(feed) {
  document.getElementById("msg-" + feed).hidden = true;
}

// ---------------------------------------------------------------------
// Is the Pi reachable? Checked every 5 s (the next check starts only after
// the previous one has finished, so slow checks never pile up).
// ---------------------------------------------------------------------
async function checkCamera() {
  const started = performance.now();
  let data;
  try {
    const res = await fetch("/api/camera-status");
    data = await res.json();
  } catch (err) {
    // Our own server is down. That says nothing about the Pi (the video
    // comes straight from the Pi), so leave the video alone.
    camLog("status check: dispatch server unreachable", err.message);
    setCamStatus("unsure", "Can't reach the dispatch server");
    return;
  }
  const roundTrip = Math.round(performance.now() - started);
  camLog("status:", data.online ? "online" : "FAILED", "| server check", data.duration_ms, "ms | round trip", roundTrip,
         "ms | ip", data.ip, data.error ? "| error " + data.error : "");

  if (data.host !== PI_HOST && !warnedHostMismatch) {
    warnedHostMismatch = true; // say it once, not every 5 s
    console.warn("PI_HOST differs: static/config.js has", PI_HOST, "but the server checks", data.host,
                 "- set them to the same value (see README, Raspberry Pi cameras)");
  }
  const where = data.host + ":" + data.port;

  if (data.online) {
    failedChecks = 0;
    const wasOffline = camState === "offline" || camState === "unknown";
    if (camState !== "online") camLog("state", camState, "-> online");
    camState = "online";
    setCamStatus("online", "Pi cameras online at " + where);
    // Only on an offline -> online change, and only once the drone is in the zone
    if (wasOffline && camerasWanted()) FEEDS.forEach(loadPiStream);
    return;
  }

  failedChecks++;
  if (failedChecks < OFFLINE_AFTER_FAILS) {
    // Probably a blip: keep the video playing, just warn in the header
    if (camState !== "unsure") camLog("state", camState, "-> unsure (failed", failedChecks, "of", OFFLINE_AFTER_FAILS + ")");
    if (camState === "online") camState = "unsure";
    setCamStatus("unsure", "Pi camera check failed " + failedChecks + " time(s) in a row (" + where + ")");
    return;
  }

  setCamStatus("offline", "Pi cameras offline at " + where);
  if (camState !== "offline") {
    camLog("state", camState, "-> OFFLINE after", failedChecks, "failed checks");
    camState = "offline";
    FEEDS.forEach((feed) => {
      unloadPiStream(feed);
      showCamMessage(feed, "offline", "CAMERA OFFLINE - check Pi / Wi-Fi");
    });
  }
}

async function cameraCheckLoop() {
  await checkCamera();
  setTimeout(cameraCheckLoop, CAM_CHECK_EVERY_MS);
}

// ---------------------------------------------------------------------
// Search zone gate. app.js calls this with telemetry.cameras_active on every
// update; only a change does anything, so the feeds load exactly once.
// ---------------------------------------------------------------------
function setCamerasActive(active) {
  if (VIDEO_MODE !== "pi" || active === zoneActive) return;
  zoneActive = active;
  camLog("search zone", active ? "entered" : "reset (new mission)");
  applyCameraWant();
}

// Load or remove the feeds to match camerasWanted(). Loading is safe to repeat:
// loadPiStream() never re-creates a feed that's already there.
function applyCameraWant() {
  if (VIDEO_MODE !== "pi") return;
  if (camerasWanted()) {
    if (camState === "online" || camState === "unsure") FEEDS.forEach(loadPiStream);
    // otherwise the next successful status check loads them
  } else {
    FEEDS.forEach((feed) => { unloadPiStream(feed); hideCamMessage(feed); });
  }
}

// ---------------------------------------------------------------------
// Cameras: Auto / On switch (bottom bar). Only for this page session;
// the starting value comes from CAMERAS_ALWAYS_ON in config.js.
// ---------------------------------------------------------------------
function setCamerasAlwaysOn(on) {
  camerasAlwaysOn = on;
  document.querySelectorAll(".cams-btn").forEach((btn) => {
    btn.setAttribute("aria-pressed", String((btn.dataset.cams === "on") === on));
  });
  camLog("cameras switch:", on ? "On (always)" : "Auto (search zone)");
  applyCameraWant();
}

document.querySelectorAll(".cams-btn").forEach((btn) => {
  btn.addEventListener("click", () => setCamerasAlwaysOn(btn.dataset.cams === "on"));
});

// Dot in the header: green = online, yellow = not sure, red = offline, grey = mock / not checked yet
function setCamStatus(state, detail) {
  const el = document.getElementById("cam-status");
  const looks = {
    online: ["conn-live", "CAM"],
    unsure: ["conn-warn", "CAM ?"],
    offline: ["conn-down", "CAM OFFLINE"],
    mock: ["conn-offline", "CAM MOCK"],
  }[state];
  el.className = "conn " + looks[0];
  document.getElementById("cam-status-text").textContent = looks[1];
  el.title = detail;
}

// ---------------------------------------------------------------------
// Mock mode: copy whatever video.js put in the Day pane into the IR pane
// ---------------------------------------------------------------------
function mirrorMockIntoIr() {
  const original = document.getElementById("feed-day").firstElementChild;
  const irPane = document.getElementById("feed-ir");
  if (!original) return irPane.replaceChildren();

  const copy = original.cloneNode(true);
  if (original.srcObject) copy.srcObject = original.srcObject; // webcam stream: share it
  if (copy.tagName === "VIDEO") {
    copy.muted = true;
    copy.autoplay = true;
    copy.playsInline = true;
  }
  irPane.replaceChildren(copy);
}

// ---------------------------------------------------------------------
// T key: fold / unfold the Telemetry box (ignored while typing)
// ---------------------------------------------------------------------
document.addEventListener("keydown", (e) => {
  if (e.key !== "t" && e.key !== "T") return;
  if (e.ctrlKey || e.metaKey || e.altKey || e.repeat) return;
  const t = e.target;
  if (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
  if (document.body.dataset.view !== "onscene") return;
  const box = document.getElementById("tele-dropdown");
  box.open = !box.open;
});

// ---------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------
if (VIDEO_MODE === "pi") {
  setVideoLabel("DAY + IR · " + PI_HOST); // video.js: shown in the Telemetry box
  setCamerasAlwaysOn(camerasAlwaysOn);    // show the switch's starting position
  camLog("pi mode, PI_HOST =", PI_HOST);
  cameraCheckLoop();
} else {
  document.getElementById("cams-toggle").hidden = true; // the webcam is always on in mock mode
  setCamStatus("mock", "Mock mode: using " + VIDEO_SOURCE.type + " (VIDEO_MODE in static/config.js)");
  document.querySelector(".video-layer").classList.add("mock-mode");
  // video.js fills the Day pane (the webcam takes a moment); copy it each time it changes
  new MutationObserver(mirrorMockIntoIr).observe(document.getElementById("feed-day"), { childList: true });
  mirrorMockIntoIr();
}
