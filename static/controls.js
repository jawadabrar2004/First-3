// =====================================================================
// controls.js - the dispatcher's buttons:
//   * Push-to-talk: hold to record the mic, release to send to /api/talk
//   * Payload drop: click, then confirm, then POST /api/drop
//   * Return to home: POST /api/rth
// app.js calls updateControls() with each telemetry update so buttons are
// only enabled when they make sense.
// =====================================================================

// ---------------------------------------------------------------------
// Push-to-talk
// ---------------------------------------------------------------------
const pttBtn = document.getElementById("ptt-btn");
const pttText = document.getElementById("ptt-text");
const pttStatus = document.getElementById("ptt-status");

let micStream = null;   // we ask for the mic once and reuse it
let recorder = null;
let chunks = [];
let holding = false;
let recordStart = 0;

async function startTalking() {
  if (holding) return;
  holding = true;
  setPttStatus("Starting microphone…");

  try {
    if (!micStream) micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    holding = false;
    setPttStatus("Microphone unavailable: " + err.message, true);
    return;
  }
  // The button may have been released while the browser asked for permission
  if (!holding) { setPttStatus("Hold the button while you talk"); return; }

  chunks = [];
  recorder = new MediaRecorder(micStream);
  recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
  recorder.onstop = sendRecording;
  recorder.start();
  recordStart = Date.now();

  pttBtn.classList.add("recording");
  pttText.textContent = "Talking… release to send";
  setPttStatus("Recording");
}

function stopTalking() {
  if (!holding) return;
  holding = false;
  pttBtn.classList.remove("recording");
  pttText.textContent = "Hold to talk";
  if (recorder && recorder.state === "recording") recorder.stop(); // triggers sendRecording
}

async function sendRecording() {
  const seconds = (Date.now() - recordStart) / 1000;
  if (seconds < 0.4) {
    setPttStatus("Too short. Hold the button while you talk.", true);
    return;
  }
  const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
  const form = new FormData();
  form.append("audio", blob, "talk.webm");

  setPttStatus("Sending " + seconds.toFixed(1) + " s clip…");
  try {
    const res = await fetch("/api/talk", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    setPttStatus("Sent " + seconds.toFixed(1) + " s clip ✓");
  } catch (err) {
    setPttStatus("Send failed: " + err.message, true);
  }
}

function setPttStatus(text, isError) {
  pttStatus.textContent = text;
  pttStatus.classList.toggle("error", !!isError);
}

// Mouse / touch / pen: pointer events cover all of them
pttBtn.addEventListener("pointerdown", (e) => {
  pttBtn.setPointerCapture(e.pointerId); // keep getting events even if the pointer slides off
  startTalking();
});
pttBtn.addEventListener("pointerup", stopTalking);
pttBtn.addEventListener("pointercancel", stopTalking);
pttBtn.addEventListener("contextmenu", (e) => e.preventDefault()); // long-press menu on touch screens

// Keyboard: hold Space or Enter while the button is focused
pttBtn.addEventListener("keydown", (e) => {
  if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); startTalking(); }
});
pttBtn.addEventListener("keyup", (e) => {
  if (e.key === " " || e.key === "Enter") { e.preventDefault(); stopTalking(); }
});
pttBtn.addEventListener("blur", stopTalking);

// ---------------------------------------------------------------------
// Payload drop (two steps: Drop payload -> Confirm drop)
// ---------------------------------------------------------------------
const dropBtn = document.getElementById("drop-btn");
const dropConfirm = document.getElementById("drop-confirm");
const dropHint = document.getElementById("drop-hint");
const payloadPill = document.getElementById("payload-pill");

const PAYLOAD_PILLS = {
  armed: { text: "ARMED", cls: "pill-warning" },
  dropping: { text: "DROPPING", cls: "pill-accent" },
  dropped: { text: "DROPPED", cls: "pill-ok" },
};

let confirmTimer = null;
let canDrop = false; // true only while the drone is hovering on scene with the payload armed

dropBtn.addEventListener("click", () => {
  dropBtn.hidden = true;
  dropConfirm.hidden = false;
  document.getElementById("drop-yes").focus();
  // Give up on the confirm step after 6 seconds
  confirmTimer = setTimeout(closeConfirm, 6000);
});

document.getElementById("drop-no").addEventListener("click", closeConfirm);

document.getElementById("drop-yes").addEventListener("click", async () => {
  closeConfirm();
  const data = await postJson("/api/drop");
  if (!data.ok) flashMessage(dropHint, data.message, true);
});

function closeConfirm() {
  clearTimeout(confirmTimer);
  dropConfirm.hidden = true;
  dropBtn.hidden = false;
}

// ---------------------------------------------------------------------
// Return to home
// ---------------------------------------------------------------------
const rthBtn = document.getElementById("rth-btn");
const rthHint = document.getElementById("rth-hint");

rthBtn.addEventListener("click", async () => {
  const data = await postJson("/api/rth");
  flashMessage(rthHint, data.message, !data.ok);
});

// ---------------------------------------------------------------------
// Enable / disable buttons based on the latest telemetry
// ---------------------------------------------------------------------
function updateControls(t) {
  const pill = PAYLOAD_PILLS[t.payload];
  payloadPill.textContent = pill.text;
  payloadPill.className = "pill " + pill.cls;

  canDrop = t.payload === "armed" && t.phase === "ON_SCENE";
  dropBtn.disabled = !canDrop;
  if (!canDrop && !dropConfirm.hidden) closeConfirm();

  let dropText;
  if (t.payload === "dropping") dropText = "Lowering payload…";
  else if (t.payload === "dropped") dropText = "Payload delivered";
  else if (t.phase === "ON_SCENE") dropText = "Drone on scene. Ready to drop.";
  else dropText = "Available when the drone is on scene";
  setHint(dropHint, dropText);

  const flying = ["TAKEOFF", "EN_ROUTE", "ON_SCENE"].includes(t.phase);
  rthBtn.disabled = !flying;
  const returning = t.phase === "RETURNING" || t.phase === "LANDING";
  setHint(rthHint, returning ? "Returning to base" : "");
}

// Hints show the current status, except right after a button press,
// when the server's reply stays visible for 4 seconds.
function setHint(el, text) {
  if (Date.now() < (el.messageUntil || 0)) return;
  el.textContent = text;
  el.classList.remove("error");
}

function flashMessage(el, text, isError) {
  el.textContent = text;
  el.classList.toggle("error", !!isError);
  el.messageUntil = Date.now() + 4000;
}

// Small helper: POST and read the JSON reply, turning network errors into a message
async function postJson(url) {
  try {
    const res = await fetch(url, { method: "POST" });
    return await res.json();
  } catch (err) {
    return { ok: false, message: "Server unreachable: " + err.message };
  }
}
