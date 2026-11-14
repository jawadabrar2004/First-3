// =====================================================================
// vision.js - shows what the machine vision (machine_vision/monitor.py) sees.
//
// main.py starts monitor.py when the drone enters the search zone. While it
// runs (telemetry.vision_active):
//   * the Day pane can show monitor.py's annotated video
//       (http://VISION_HOST:VISION_PORT/stream.mjpg), over the raw feed.
//       The small CV ON / RAW switch flips between them.
//   * every second we read .../status.json: people in view + current alerts,
//       shown in the bottom bar's "Scene" readout.
// New incidents (each with a screenshot) come from main.py over the
// WebSocket. Each goes into the Alerts drop-down with Confirm / Dismiss
// buttons, gets a marker on the maps, and plays a short sound.
// The dispatcher always decides: the system never acts on an alert itself.
// =====================================================================

const VISION_URL = "http://" + VISION_HOST + ":" + VISION_PORT;
const CV_STORAGE_KEY = "first3.cvView";
const ALERT_NAMES = {
  person_down: "Person down",
  waving: "Waving for help",
  choking: "Possible choking",
  fire: "Fire",
  fire_people: "Fire, people near",
};

let visionOn = false;      // is monitor.py meant to be running?
let statusTimer = null;
let cvView = loadCvView(); // "on" (annotated) or "raw"
let cvHasFrame = false;    // has the annotated stream shown a picture yet?
const shownIncidents = {}; // id -> its <li> in the Alerts list

// ---------------------------------------------------------------------
// Called by app.js with every telemetry update
// ---------------------------------------------------------------------
function updateVision(t) {
  if (t.vision_active === visionOn) return;
  visionOn = t.vision_active;
  document.getElementById("cv-toggle").hidden = !visionOn;
  if (visionOn) {
    setSceneState("CV starting…");
    pollVisionStatus();
    statusTimer = setInterval(pollVisionStatus, 1000);
  } else {
    clearInterval(statusTimer);
    setSceneState("CV off");
    showScene(null);
  }
  applyCvView();
}

// ---------------------------------------------------------------------
// CV ON / RAW switch on the Day pane
// ---------------------------------------------------------------------
function loadCvView() {
  try { return localStorage.getItem(CV_STORAGE_KEY) === "raw" ? "raw" : "on"; } catch (err) { return "on"; }
}

document.querySelectorAll(".cv-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    cvView = btn.dataset.cv;
    try { localStorage.setItem(CV_STORAGE_KEY, cvView); } catch (err) { /* not remembered */ }
    applyCvView();
  });
});

function applyCvView() {
  document.querySelectorAll(".cv-btn").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(btn.dataset.cv === cvView));
  });
  const img = document.getElementById("cv-stream");
  const want = visionOn && cvView === "on";
  if (want && !img.getAttribute("src")) {
    img.src = VISION_URL + "/stream.mjpg";
  } else if (!want && img.getAttribute("src")) {
    img.removeAttribute("src");   // closes the stream
    cvHasFrame = false;
  }
  // Only cover the raw feed once the annotated view really has a picture
  // (the raw feed underneath is never touched)
  img.hidden = !(want && cvHasFrame);
}

document.getElementById("cv-stream").addEventListener("load", () => {
  cvHasFrame = true;              // first picture arrived
  applyCvView();
});

// monitor.py takes a few seconds to load its model: keep retrying the stream
document.getElementById("cv-stream").addEventListener("error", (e) => {
  const img = e.target;
  cvHasFrame = false;
  img.hidden = true;              // show the raw feed while we wait
  if (!visionOn || cvView !== "on") return;
  img.removeAttribute("src");
  setTimeout(() => { if (visionOn && cvView === "on") img.src = VISION_URL + "/stream.mjpg?t=" + Date.now(); }, 2000);
});

// ---------------------------------------------------------------------
// Scene readout (bottom bar): people in view + alerts active right now
// ---------------------------------------------------------------------
async function pollVisionStatus() {
  try {
    const res = await fetch(VISION_URL + "/status.json", { cache: "no-store" });
    const status = await res.json();
    if (!visionOn) return;
    setSceneState("");
    showScene(status);
  } catch (err) {
    if (!visionOn) return;
    setSceneState("CV starting…"); // monitor.py not up yet (or restarting)
    showScene(null);               // don't keep showing an old head count
  }
}

function showScene(status) {
  document.getElementById("scene-people").textContent = status ? status.people : "-";
  const badges = document.getElementById("scene-badges");
  badges.replaceChildren();
  if (!status) return;
  Object.keys(status.alerts || {}).forEach((kind) => {
    const b = document.createElement("span");
    b.className = "alert-badge alert-" + kind;
    b.textContent = ALERT_NAMES[kind] || status.alerts[kind];
    badges.appendChild(b);
  });
}

function setSceneState(text) {
  document.getElementById("scene-state").textContent = text;
}

// ---------------------------------------------------------------------
// Alerts (incidents)
// ---------------------------------------------------------------------
// Full list from a snapshot (page load / new call): no sound
function setIncidents(items) {
  Object.keys(shownIncidents).forEach((id) => delete shownIncidents[id]);
  document.getElementById("alert-feed").replaceChildren();
  (items || []).forEach((item) => showIncident(item, false));
  updateAlertCount();
}

// One incident from the WebSocket: new, or the dispatcher's decision on one
function onIncident(item) {
  showIncident(item, true);
  updateAlertCount();
}

function showIncident(item, isLive) {
  let li = shownIncidents[item.id];
  const isNew = !li;
  if (isNew) {
    li = buildIncident(item);
    shownIncidents[item.id] = li;
    const feed = document.getElementById("alert-feed");
    feed.prepend(li);  // newest at the top
    addIncidentToMaps(item); // map.js
    if (isLive) {
      playAlertSound();
      const box = document.getElementById("alerts-dropdown");
      box.open = true;
    }
  }
  li.classList.toggle("is-confirmed", item.decision === "confirmed");
  li.classList.toggle("is-dismissed", item.decision === "dismissed");
  li.querySelector(".alert-decision").textContent = item.decision ? item.decision.toUpperCase() : "";
  li.querySelectorAll(".alert-actions button").forEach((b) => { b.disabled = !!item.decision; });
}

function buildIncident(item) {
  const li = document.createElement("li");
  li.className = "alert-item alert-" + item.kind;

  const thumb = document.createElement("img");
  thumb.className = "alert-thumb";
  thumb.alt = "Screenshot: " + item.text;
  thumb.src = "/api/vision/incidents/" + encodeURIComponent(item.image);
  thumb.addEventListener("click", () => openLightbox(thumb.src, item));

  const body = document.createElement("div");
  body.className = "alert-body";
  const head = document.createElement("div");
  head.className = "alert-head";
  const kind = document.createElement("span");
  kind.className = "alert-badge alert-" + item.kind;
  kind.textContent = ALERT_NAMES[item.kind] || item.text;
  const time = document.createElement("span");
  time.className = "alert-time mono";
  time.textContent = (item.time || "").slice(11, 19); // HH:MM:SS
  head.append(kind, time);

  const info = document.createElement("span");
  info.className = "alert-info";
  info.textContent = item.people != null ? item.people + " in view" : "";

  const actions = document.createElement("div");
  actions.className = "alert-actions";
  const confirm = document.createElement("button");
  confirm.className = "btn btn-small btn-critical";
  confirm.type = "button";
  confirm.textContent = "Confirm";
  confirm.addEventListener("click", () => decideIncident(item.id, "confirm"));
  const dismiss = document.createElement("button");
  dismiss.className = "btn btn-small";
  dismiss.type = "button";
  dismiss.textContent = "Dismiss";
  dismiss.addEventListener("click", () => decideIncident(item.id, "dismiss"));
  const decision = document.createElement("span");
  decision.className = "alert-decision";
  actions.append(confirm, dismiss, decision);

  body.append(head, info, actions);
  li.append(thumb, body);
  return li;
}

async function decideIncident(id, decision) {
  try {
    await fetch("/api/vision/incidents/" + id + "/" + decision, { method: "POST" });
    // the server sends the update back over the WebSocket (onIncident)
  } catch (err) {
    console.warn("Couldn't send the decision:", err);
  }
}

function updateAlertCount() {
  const open = Object.values(shownIncidents).filter((li) => !li.classList.contains("is-confirmed") &&
                                                           !li.classList.contains("is-dismissed")).length;
  const badge = document.getElementById("alert-count");
  badge.textContent = open;
  badge.hidden = open === 0;
  const feed = document.getElementById("alert-feed");
  if (!feed.children.length) {
    const empty = document.createElement("li");
    empty.className = "alert-empty";
    empty.textContent = "No alerts yet";
    feed.appendChild(empty);
  } else {
    feed.querySelectorAll(".alert-empty").forEach((el) => el.remove());
  }
}

// ---------------------------------------------------------------------
// Enlarged screenshot
// ---------------------------------------------------------------------
function openLightbox(src, item) {
  document.getElementById("lightbox-img").src = src;
  document.getElementById("lightbox-caption").textContent =
    (ALERT_NAMES[item.kind] || item.text) + " · " + (item.time || "").replace("T", " ");
  document.getElementById("lightbox").hidden = false;
}
document.getElementById("lightbox").addEventListener("click", () => {
  document.getElementById("lightbox").hidden = true;
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") document.getElementById("lightbox").hidden = true;
});

// ---------------------------------------------------------------------
// Alert sound: two short beeps, made in the browser (no sound file needed)
// ---------------------------------------------------------------------
let audioCtx = null;
function playAlertSound() {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const now = audioCtx.currentTime;
    [[880, 0], [660, 0.18]].forEach(([freq, start]) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "square";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, now + start);
      gain.gain.exponentialRampToValueAtTime(0.15, now + start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + start + 0.15);
      osc.connect(gain).connect(audioCtx.destination);
      osc.start(now + start);
      osc.stop(now + start + 0.16);
    });
  } catch (err) {
    // no sound available; the alert still shows
  }
}
