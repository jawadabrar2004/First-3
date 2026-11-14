// =====================================================================
// app.js - connects to the server, keeps the screen up to date, and
// decides which of the 4 screens to show:
//
//   incoming -> call is ringing (Answer button)
//   call     -> on the call: transcript, address box, drone choices
//   enroute  -> blurred camera, ETA countdown to the search zone + minimap
//   onscene  -> the cameras (from the moment the drone enters the search zone),
//               drop-downs on the left edge, controls in the bottom bar
//
// The server sends JSON messages over a WebSocket (/ws). Each message has
// a "type", and handleMessage() sends it to the right function below.
// If the connection drops, we show OFFLINE and keep trying to reconnect.
// =====================================================================

let socket = null;
let call = { answered: false, caller_number: null, address: null }; // latest call info
let lastCamerasActive = null; // to notice the moment the drone enters the search zone

function connect() {
  // ws:// for http pages, wss:// for https pages
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(protocol + "//" + location.host + "/ws");

  socket.onopen = () => setConnection(true);
  socket.onmessage = (event) => handleMessage(JSON.parse(event.data));
  socket.onclose = () => {
    setConnection(false);
    setTimeout(connect, 2000); // try again in 2 seconds
  };
}

function handleMessage(msg) {
  if (msg.type === "snapshot") {
    // Full state: rebuild everything from scratch
    call = msg.call;
    document.querySelectorAll(".transcript").forEach((list) => { list.innerHTML = ""; });
    msg.transcript.forEach(addTranscriptLine);
    showCallInfo();
    setupZoneMaps(msg.mission);      // map.js
    setIncidents(msg.incidents);     // vision.js
    lastCamerasActive = null;        // don't show the zone banner just for loading the page
    onTelemetry(msg.telemetry, msg.mission_seconds);
  } else if (msg.type === "telemetry") {
    onTelemetry(msg.data, msg.mission_seconds);
  } else if (msg.type === "transcript") {
    addTranscriptLine(msg.line);
  } else if (msg.type === "incident") {
    onIncident(msg.incident);        // vision.js: new machine vision alert, or a decision on one
  }
}

// Called a few times per second with fresh drone data
function onTelemetry(t, missionSeconds) {
  document.getElementById("mission-timer").textContent = formatTime(missionSeconds);
  setView(pickView(t), t);
  updateEta(t);
  updateTelemetry(t);              // telemetry.js
  updateControls(t);               // controls.js
  updateZoneMaps(t);               // map.js
  setCamerasActive(t.cameras_active); // camera.js: Pi feeds load once, in the zone
  updateVision(t);                 // vision.js
  if (lastCamerasActive === false && t.cameras_active) showZoneBanner();
  lastCamerasActive = t.cameras_active;
}

// "ENTERING SEARCH ZONE - CAMERAS ACTIVE", for a few seconds
let zoneBannerTimer = null;
function showZoneBanner() {
  const banner = document.getElementById("zone-banner");
  banner.hidden = false;
  clearTimeout(zoneBannerTimer);
  zoneBannerTimer = setTimeout(() => { banner.hidden = true; }, 4000);
}

// ---------------------------------------------------------------------
// Which screen to show
// ---------------------------------------------------------------------
function pickView(t) {
  if (!call.answered) return "incoming";
  if (t.phase === "STANDBY") return "call";
  if (t.phase === "EN_ROUTE") return "enroute";
  return "onscene"; // searching the zone, on scene, returning, landing, landed
}

const STATUS_TEXT = {
  incoming: "Incoming call",
  call: "On call",
  enroute: "Drone en route",
};

function setView(view, t) {
  const changed = document.body.dataset.view !== view;
  document.body.dataset.view = view;
  if (changed) camLog("view ->", view); // camera.js (only logs when DEBUG_CAMERA is on)

  // Header chip: a fixed text, or the drone's phase once on scene
  document.getElementById("status-chip").textContent = STATUS_TEXT[view] || t.phase_label;

  // Once the drone leaves the scene, say so under the camera label
  const phase = document.getElementById("scene-phase");
  phase.hidden = view !== "onscene" || t.phase === "ON_SCENE";
  phase.textContent = t.phase_label;

  if (changed && view === "call") document.getElementById("address").focus();
  if (changed) setTimeout(refreshZoneMaps, 50); // map.js: maps that just became visible re-measure
}

// ---------------------------------------------------------------------
// Screen 1: incoming call
// ---------------------------------------------------------------------
document.getElementById("answer-btn").addEventListener("click", () => {
  fetch("/api/answer", { method: "POST" });
});

function showCallInfo() {
  document.getElementById("caller-number").textContent = call.caller_number || "Unknown number";
  document.getElementById("call-caller").textContent = call.caller_number ? "Caller " + call.caller_number : "";
  const address = call.address || "";
  document.getElementById("eta-address").textContent = address;
  document.getElementById("scene-address").textContent = address;
  if (!call.answered) {
    document.getElementById("address").value = ""; // new call
    stopRecordTimer();                              // controls.js
  }
  refreshDroneCards(); // controls.js
}

// ---------------------------------------------------------------------
// Screen 3: ETA countdown (to the search zone) over the blurred camera
// ---------------------------------------------------------------------
function updateEta(t) {
  if (t.payload_name) document.getElementById("eta-title").textContent = t.payload_name + " drone en route";
  document.getElementById("zone-distance").textContent =
    t.in_search_zone ? "inside the zone" : t.distance_to_zone + " m";
  if (t.phase !== "EN_ROUTE" || t.eta_seconds == null) return;
  document.getElementById("eta-value").textContent = formatTime(Math.ceil(t.eta_seconds), true);
  const done = 1 - t.eta_seconds / t.eta_total;
  document.getElementById("eta-bar").style.width = Math.max(0, Math.min(1, done)) * 100 + "%";
}

// ---------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------
function setConnection(live) {
  const el = document.getElementById("conn");
  el.className = "conn " + (live ? "conn-live" : "conn-offline");
  document.getElementById("conn-text").textContent = live ? "LIVE" : "OFFLINE";
}

document.getElementById("reset-btn").addEventListener("click", () => {
  fetch("/api/reset", { method: "POST" });
});

// ---------------------------------------------------------------------
// Transcript + status feed (the same lines go to every .transcript list)
// ---------------------------------------------------------------------
const SPEAKER_NAMES = { CALLER: "Caller", DISPATCH: "Dispatcher", SYSTEM: "Status" };

function addTranscriptLine(line) {
  document.querySelectorAll(".transcript").forEach((list) => {
    // Only auto-scroll if the list is already at the bottom (or hidden),
    // so we don't yank the view away from someone reading older lines
    const atBottom = list.clientHeight === 0 || list.scrollHeight - list.scrollTop - list.clientHeight < 60;

    const li = document.createElement("li");
    li.className = "sp-" + line.speaker.toLowerCase();

    const time = document.createElement("span");
    time.className = "t-time mono";
    time.textContent = formatTime(line.t);

    const body = document.createElement("div");
    const speaker = document.createElement("span");
    speaker.className = "t-speaker";
    speaker.textContent = SPEAKER_NAMES[line.speaker] || line.speaker;
    const text = document.createElement("span");
    text.textContent = line.text; // textContent (not innerHTML) so text can't inject HTML

    body.append(speaker, text);
    li.append(time, body);
    list.appendChild(li);
    if (atBottom) list.scrollTop = list.scrollHeight;
  });
  markFeedUnread();
}

// On scene the feed lives in a small drop-down box. While it's closed, a dot
// on it shows there are new lines; opening it clears the dot.
const feedDropdown = document.getElementById("feed-dropdown");
function markFeedUnread() {
  if (!feedDropdown.open && document.body.dataset.view === "onscene") feedDropdown.classList.add("has-new");
}
feedDropdown.addEventListener("toggle", () => {
  if (!feedDropdown.open) return;
  feedDropdown.classList.remove("has-new");
  const list = feedDropdown.querySelector(".transcript");
  list.scrollTop = list.scrollHeight; // jump to the newest line
});

// Hidden lists don't scroll, so jump to the newest line when a screen appears
new MutationObserver(() => {
  document.querySelectorAll(".transcript").forEach((list) => { list.scrollTop = list.scrollHeight; });
}).observe(document.body, { attributes: true, attributeFilter: ["data-view"] });

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------
function formatTime(totalSeconds, short) {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return (short ? String(m) : String(m).padStart(2, "0")) + ":" + String(s).padStart(2, "0");
}

connect();
