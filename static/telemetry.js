// =====================================================================
// telemetry.js - fills in the Telemetry drop-down box on the left edge of
// the camera (battery, altitude, speed, mode, signal, GPS).
// app.js calls updateTelemetry() every time new data arrives.
// =====================================================================

function updateTelemetry(t) {
  // Battery: number + coloured bar (green > 50%, amber > 25%, red below)
  document.getElementById("t-battery").textContent = t.battery.toFixed(0);
  document.getElementById("t-battery-mini").textContent = t.battery.toFixed(0); // shown when the box is closed
  const bar = document.getElementById("t-battery-bar");
  bar.style.width = t.battery + "%";
  bar.className = "bar-fill" + (t.battery <= 25 ? " critical" : t.battery <= 50 ? " low" : "");

  document.getElementById("t-alt").textContent = t.altitude.toFixed(1);
  document.getElementById("t-speed").textContent = t.speed.toFixed(1);
  document.getElementById("t-mode").textContent = t.flight_mode;
  document.getElementById("t-gps").textContent = t.lat.toFixed(6) + "\n" + t.lon.toFixed(6);

  // Signal: number + 4 bars (one bar per 25%)
  document.getElementById("t-signal").textContent = t.signal;
  const bars = document.querySelectorAll("#t-signal-bars i");
  bars.forEach((b, i) => b.classList.toggle("on", t.signal > i * 25));
}
