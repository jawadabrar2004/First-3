// =====================================================================
// app.js - connects to the server and keeps the screen up to date.
//
// The server sends JSON messages over a WebSocket (/ws). Each message has
// a "type", and handleMessage() sends it to the right function below.
// If the connection drops, we show OFFLINE and keep trying to reconnect.
// =====================================================================

let socket = null;

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
    setupMap(msg.mission);
    document.getElementById("transcript").innerHTML = "";
    msg.transcript.forEach(addTranscriptLine);
    showKeyInfo(msg.key_info, false);
    onTelemetry(msg.telemetry, msg.mission_seconds);
  } else if (msg.type === "telemetry") {
    onTelemetry(msg.data, msg.mission_seconds);
  } else if (msg.type === "transcript") {
    addTranscriptLine(msg.line);
  } else if (msg.type === "key_info") {
    showKeyInfo(msg.data, true);
  }
}

// Called a few times per second with fresh drone data
function onTelemetry(t, missionSeconds) {
  document.getElementById("mission-timer").textContent = formatTime(missionSeconds);
  document.getElementById("phase-chip").textContent = t.phase_label;
  updateHud(t);
  updateTelemetry(t); // telemetry.js
  updateMap(t);       // map.js
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
// Video overlay (HUD)
// ---------------------------------------------------------------------
function updateHud(t) {
  document.getElementById("hud-phase").textContent = t.phase_label.toUpperCase();
  document.getElementById("hud-alt").textContent = t.altitude.toFixed(0);
  document.getElementById("hud-spd").textContent = t.speed.toFixed(1);
  document.getElementById("hud-hdg").textContent = String(t.heading).padStart(3, "0");
  document.getElementById("hud-pos").textContent = t.lat.toFixed(5) + ", " + t.lon.toFixed(5);
}

// ---------------------------------------------------------------------
// Transcript
// ---------------------------------------------------------------------
const SPEAKER_NAMES = { CALLER: "Caller", DISPATCH: "Dispatcher", SYSTEM: "System" };

function addTranscriptLine(line) {
  const list = document.getElementById("transcript");

  // Only auto-scroll if the dispatcher is already looking at the bottom
  // (so we don't yank the view away while they read older lines)
  const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 40;

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
}

// ---------------------------------------------------------------------
// Key info
// ---------------------------------------------------------------------
function showKeyInfo(info, highlightChanges) {
  setKeyInfo("ki-address", info.address, highlightChanges);
  setKeyInfo("ki-type", info.emergency_type, highlightChanges);
  setKeyInfo("ki-callback", info.callback_number, highlightChanges);

  const patient = setKeyInfo("ki-patient", info.patient_status, highlightChanges);
  if (info.patient_status) {
    patient.classList.add(info.patient_critical ? "ki-critical" : "ki-ok");
    if (info.patient_critical) patient.textContent = "⚠ " + info.patient_status;
  }
}

function setKeyInfo(id, value, highlight) {
  const el = document.getElementById(id);
  const old = el.dataset.value || "";
  el.dataset.value = value || "";
  el.textContent = value || "Listening…";
  el.classList.remove("ki-empty", "ki-critical", "ki-ok", "ki-new");
  if (!value) el.classList.add("ki-empty");
  if (highlight && value && value !== old) {
    void el.offsetWidth; // restart the flash animation
    el.classList.add("ki-new");
  }
  return el;
}

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------
function formatTime(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
}

connect();
