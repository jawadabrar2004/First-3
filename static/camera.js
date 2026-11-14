// =====================================================================
// camera.js - the Raspberry Pi cameras, shown side by side:
//             Day on the left, IR on the right.
//
//   * VIDEO_MODE "pi":   each pane shows one MediaMTX player page in an
//                        <iframe>. Every 5 s we ask the server whether the
//                        Pi is reachable (/api/camera-status). If it isn't,
//                        both panes show CAMERA OFFLINE, and the streams
//                        reconnect by themselves when the Pi is back.
//   * VIDEO_MODE "mock": video.js puts the laptop webcam in the Day pane and
//                        we copy it into the IR pane in grey, so the
//                        side-by-side layout can still be demoed.
//
//   Also here: the T key folds / unfolds the Telemetry box.
// =====================================================================

const FEEDS = ["day", "ir"];
const CAM_NAMES = { day: "DAY CAM", ir: "IR CAM" };
const CAM_CHECK_EVERY_MS = 5000;

let camOnline = null;          // null = not checked yet, then true / false
const connectTimers = {};      // one "hide connecting" timer per feed

// ---------------------------------------------------------------------
// Pi streams
// ---------------------------------------------------------------------
function loadPiStream(feed) {
  showCamMessage(feed, "connecting", "Connecting to " + CAM_NAMES[feed] + "…");

  const frame = document.createElement("iframe");
  frame.title = "Drone camera (" + CAM_NAMES[feed] + ")";
  frame.allow = "autoplay; fullscreen";
  frame.src = PI_STREAMS[feed] + PI_PLAYER_PARAMS;

  // The player page has loaded; give the video a moment to start, then
  // hide "connecting". Never leave the message up for more than 10 s.
  clearTimeout(connectTimers[feed]);
  frame.addEventListener("load", () => {
    clearTimeout(connectTimers[feed]);
    connectTimers[feed] = setTimeout(() => hideCamMessage(feed), 1500);
  });
  connectTimers[feed] = setTimeout(() => hideCamMessage(feed), 10000);

  document.getElementById("feed-" + feed).replaceChildren(frame);
}

function unloadPiStream(feed) {
  clearTimeout(connectTimers[feed]);
  document.getElementById("feed-" + feed).replaceChildren();
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
  setCamStatus(data.online, (data.online ? "Pi cameras online at " : "Pi cameras offline at ") + data.host + ":" + data.port);

  if (data.online && camOnline !== true) {
    camOnline = true;
    FEEDS.forEach(loadPiStream);   // first connect, or the Pi came back
  } else if (!data.online && camOnline !== false) {
    camOnline = false;
    FEEDS.forEach((feed) => {
      unloadPiStream(feed);
      showCamMessage(feed, "offline", "CAMERA OFFLINE - check Pi / Wi-Fi");
    });
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
  FEEDS.forEach((feed) => showCamMessage(feed, "connecting", "Connecting to " + CAM_NAMES[feed] + "…"));
  checkCamera();
  setInterval(checkCamera, CAM_CHECK_EVERY_MS);
} else {
  setCamStatus(null, "Mock mode: using " + VIDEO_SOURCE.type + " (VIDEO_MODE in static/config.js)");
  document.querySelector(".video-layer").classList.add("mock-mode");
  // video.js fills the Day pane (the webcam takes a moment); copy it each time it changes
  new MutationObserver(mirrorMockIntoIr).observe(document.getElementById("feed-day"), { childList: true });
  mirrorMockIntoIr();
}
