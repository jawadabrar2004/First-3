// =====================================================================
// controls.js - the dispatcher's buttons:
//   * Dispatch: type the address, then pick a drone -> POST /api/dispatch
//   * Push-to-talk: hold to record the mic, release to send to /api/talk
//   * Payload drop: click, then confirm, then POST /api/drop
//   * Return to base: POST /api/rth
// app.js calls updateControls() with each telemetry update so buttons are
// only enabled when they make sense.
// =====================================================================

// ---------------------------------------------------------------------
// Dispatch: address box + the three drone cards
// ---------------------------------------------------------------------
const addressInput = document.getElementById("address");
const droneCards = document.querySelectorAll(".drone-card");
const dispatchHint = document.getElementById("dispatch-hint");

// The drone cards unlock once something is typed in the address box
function refreshDroneCards() {
  const hasAddress = addressInput.value.trim() !== "";
  droneCards.forEach((card) => { card.disabled = !hasAddress; });
  dispatchHint.textContent = hasAddress
    ? "Pick the drone to send. It launches right away."
    : "Type the address to unlock the drones";
  dispatchHint.classList.remove("error");
}
addressInput.addEventListener("input", refreshDroneCards);

// Pressing Enter in the address box shouldn't reload the page
document.getElementById("dispatch-form").addEventListener("submit", (e) => e.preventDefault());

droneCards.forEach((card) => {
  card.addEventListener("click", async () => {
    droneCards.forEach((c) => { c.disabled = true; }); // no double dispatch
    dispatchHint.textContent = "Dispatching…";
    const data = await postJson("/api/dispatch", {
      address: addressInput.value.trim(),
      payload: card.dataset.payload,
    });
    if (!data.ok) {
      refreshDroneCards();
      dispatchHint.textContent = data.message;
      dispatchHint.classList.add("error");
    }
    // On success the server sends new state and app.js switches to the ETA screen
  });
});

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
  form.append("seconds", seconds.toFixed(1)); // shown in the status feed

  setPttStatus("Sending " + seconds.toFixed(1) + " s clip…");
  try {
    const res = await fetch("/api/talk", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    setPttStatus("Sent ✓");
    setTimeout(() => { if (pttStatus.textContent === "Sent ✓") setPttStatus(""); }, 3000);
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
// Return to base
// ---------------------------------------------------------------------
// The button is in the header, next to LIVE. Its label doubles as its status.
const rthBtn = document.getElementById("rth-btn");
const rthText = document.getElementById("rth-text");

rthBtn.addEventListener("click", async () => {
  const data = await postJson("/api/rth");
  if (!data.ok) rthBtn.title = data.message; // rare: shown when hovering the button
});

// ---------------------------------------------------------------------
// Enable / disable buttons based on the latest telemetry
// ---------------------------------------------------------------------
function updateControls(t) {
  document.getElementById("payload-name").textContent = t.payload_name || "--";
  const pill = PAYLOAD_PILLS[t.payload];
  payloadPill.textContent = pill.text;
  payloadPill.className = "pill " + pill.cls;

  canDrop = t.payload === "armed" && t.phase === "ON_SCENE";
  dropBtn.disabled = !canDrop;
  if (!canDrop && !dropConfirm.hidden) closeConfirm();

  // Kept short on purpose: the pill already says ARMED / DROPPING / DROPPED
  setHint(dropHint, t.payload === "dropping" ? "Lowering…" : "");

  const flying = ["EN_ROUTE", "ON_SCENE"].includes(t.phase);
  rthBtn.disabled = !flying;
  if (t.phase === "RETURNING" || t.phase === "LANDING") rthText.textContent = "Returning to base…";
  else if (t.phase === "LANDED") rthText.textContent = "Landed at base";
  else rthText.textContent = "Return to base";
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

// Small helper: POST (optionally with a JSON body) and read the JSON reply,
// turning network errors into a message
async function postJson(url, body) {
  try {
    const options = { method: "POST" };
    if (body) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }
    const res = await fetch(url, options);
    return await res.json();
  } catch (err) {
    return { ok: false, message: "Server unreachable: " + err.message };
  }
}
