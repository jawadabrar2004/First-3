// =====================================================================
// map.js - Leaflet map with the drone, the incident and the drone base.
// app.js calls setupMap() once (when it learns the locations) and
// updateMap() every time new telemetry arrives.
// =====================================================================

let map = null;
let droneMarker = null;
let droneTrail = null;
let followDrone = true; // stop auto-panning once the dispatcher drags the map

function setupMap(mission) {
  const home = [mission.home.lat, mission.home.lon];
  const incident = [mission.incident.lat, mission.incident.lon];

  if (!map) {
    map = L.map("map", { zoomControl: true, attributionControl: true });
    // Dark map tiles from CARTO (free, based on OpenStreetMap)
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 20,
      subdomains: "abcd",
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    }).addTo(map);
    map.on("dragstart", () => { followDrone = false; });

    // Incident: red dot
    L.marker(incident, {
      icon: L.divIcon({ className: "map-pin map-pin-incident", iconSize: [16, 16] }),
      title: "Incident",
    }).addTo(map).bindTooltip("Incident: " + mission.incident.label);

    // Drone base: grey square
    L.marker(home, {
      icon: L.divIcon({ className: "map-pin map-pin-home", iconSize: [14, 14] }),
      title: "Drone base",
    }).addTo(map).bindTooltip(mission.home.label);

    // Drone: a cyan arrow we rotate to match its heading
    droneMarker = L.marker(home, {
      icon: L.divIcon({
        className: "map-drone",
        iconSize: [26, 26],
        html: '<svg viewBox="0 0 24 24"><path d="M12 2 20 21 12 16.5 4 21z"/></svg>',
      }),
      zIndexOffset: 1000,
      title: "Drone",
    }).addTo(map);

    // Line showing where the drone has been
    droneTrail = L.polyline([], { color: "#22d3ee", weight: 2, opacity: 0.6, dashArray: "4 6" }).addTo(map);
  }

  // Start of a mission: clear the trail and show both points
  droneTrail.setLatLngs([]);
  followDrone = true;
  map.fitBounds([home, incident], { padding: [30, 30] });
}

function updateMap(t) {
  if (!map) return;
  const pos = [t.lat, t.lon];
  droneMarker.setLatLng(pos);

  // Point the arrow the way the drone is flying
  const svg = droneMarker.getElement() && droneMarker.getElement().querySelector("svg");
  if (svg) svg.style.transform = "rotate(" + t.heading + "deg)";

  // Add to the trail only when the drone has actually moved
  const trail = droneTrail.getLatLngs();
  const last = trail[trail.length - 1];
  if (!last || last.lat !== t.lat || last.lng !== t.lon) droneTrail.addLatLng(pos);

  // Keep the drone on screen unless the dispatcher has moved the map
  if (followDrone && !map.getBounds().pad(-0.1).contains(pos)) map.panTo(pos);

  document.getElementById("map-distance").textContent =
    t.distance_to_incident >= 1000
      ? (t.distance_to_incident / 1000).toFixed(2) + " km to scene"
      : t.distance_to_incident + " m to scene";
}
