// The call flow: Answer shows the caller's number and location, then the responder picks a drone.
(function () {
  "use strict";

  // A demo call until real calls are connected. Swap these for live data later.
  const CALL = { phone: "(860) 555-0142", lat: 41.76374, lng: -72.68512 };

  const answerBtn = document.getElementById("answer");
  const answerText = document.getElementById("answer-text");
  const card = document.getElementById("call");
  const note = document.getElementById("drone-note");
  const drones = Array.from(document.querySelectorAll(".drone-btn"));

  answerBtn.addEventListener("click", () => {
    document.getElementById("caller-phone").textContent = CALL.phone;
    document.getElementById("lat").textContent = CALL.lat.toFixed(5);
    document.getElementById("lng").textContent = CALL.lng.toFixed(5);
    answerBtn.disabled = true;
    answerText.textContent = "Answered";
    card.hidden = false;
    card.focus();
  });

  // One drone at a time; choosing another switches to it.
  drones.forEach(btn => btn.addEventListener("click", () => {
    drones.forEach(b => b.setAttribute("aria-pressed", String(b === btn)));
    note.textContent = "Drone " + btn.dataset.drone + " selected";
  }));
})();
