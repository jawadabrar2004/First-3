// =====================================================================
// map.js - the search-zone maps (Leaflet). There are two, built the same way:
//   * the minimap on the ETA screen   (id "eta-map")
//   * the Map drop-down on scene       (id "scene-map")
//
// Each shows: the caller's reported position (pin), the search zone (a
// translucent circle with the uncertainty radius), the drone's live position
// and heading, the drone base, the planned flight path (dashed), the path
// flown so far, and a marker for every machine vision alert.
// app.js calls setupZoneMaps() with the mission and updateZoneMaps() with
// every telemetry update; vision.js calls addIncidentToMaps().
// =====================================================================

const ZONE_COLOR = "#fbbf24";   // --warning: the search zone
const DRONE_COLOR = "#22d3ee";  // --accent: the drone and its path
const FIT_EVERY_MS = 1000;      // re-fit the view at most once a second

class ZoneMap {
  constructor(elementId) {
    this.el = document.getElementById(elementId);
    this.map = null;
    this.incidentLayer = null;
    this.lastFit = 0;
    // Maps live on screens / drop-downs that are hidden at times. Whenever the
    // box changes size (e.g. hidden -> shown), re-measure and re-fit.
    new ResizeObserver(() => this.refresh()).observe(this.el);
  }

  // Build the map (first time) or reset it for a new mission
  setup(mission) {
    const home = [mission.home.lat, mission.home.lon];
    const caller = [mission.caller.lat, mission.caller.lon];

    if (!this.map) {
      // Start with a view right away: Leaflet only draws layers once the map has one
      this.map = L.map(this.el, { zoomControl: false, attributionControl: true }).setView(caller, 15);
      // Standard OpenStreetMap tiles (free, no API key); style.css darkens them
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(this.map);

      // Search zone: translucent circle, labelled
      this.zone = L.circle(caller, { radius: mission.caller.radius_m, color: ZONE_COLOR, weight: 2,
                                     fillColor: ZONE_COLOR, fillOpacity: 0.15 }).addTo(this.map);
      this.zone.bindTooltip("Search zone", { permanent: true, direction: "top", className: "map-label" });

      // Caller's reported position: a pin
      this.callerPin = L.marker(caller, {
        icon: L.divIcon({ className: "map-pin-caller", iconSize: [18, 24], iconAnchor: [9, 24],
                          html: '<svg viewBox="0 0 24 32"><path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 20 12 20s12-11 12-20C24 5.4 18.6 0 12 0z"/><circle cx="12" cy="12" r="4.5"/></svg>' }),
        title: "Caller's reported position",
      }).addTo(this.map).bindTooltip("Caller (reported)");

      // Drone base: grey square
      this.base = L.marker(home, {
        icon: L.divIcon({ className: "map-pin-home", iconSize: [12, 12] }), title: "Drone base",
      }).addTo(this.map).bindTooltip("Drone base");

      // Planned flight path (dashed) and the path flown so far
      this.plan = L.polyline([home, caller], { color: DRONE_COLOR, weight: 2, opacity: 0.7, dashArray: "6 8" }).addTo(this.map);
      this.trail = L.polyline([], { color: DRONE_COLOR, weight: 3, opacity: 0.9 }).addTo(this.map);

      // Drone: an arrow that turns with its heading
      this.drone = L.marker(home, {
        icon: L.divIcon({ className: "map-drone", iconSize: [22, 22],
                          html: '<svg viewBox="0 0 24 24"><path d="M12 2 20 21 12 16.5 4 21z"/></svg>' }),
        zIndexOffset: 1000, title: "Drone",
      }).addTo(this.map);

      this.incidentLayer = L.layerGroup().addTo(this.map);
    }

    // New mission: put everything back
    this.zone.setLatLng(caller).setRadius(mission.caller.radius_m);
    this.zoneBounds = L.latLng(caller).toBounds(mission.caller.radius_m * 2); // the circle's box
    this.callerPin.setLatLng(caller);
    this.base.setLatLng(home);
    this.plan.setLatLngs([home, caller]);
    this.trail.setLatLngs([]);
    this.incidentLayer.clearLayers();
    this.fit(home, true);
  }

  update(t) {
    if (!this.map) return;
    const pos = [t.lat, t.lon];
    this.drone.setLatLng(pos);
    const svg = this.drone.getElement() && this.drone.getElement().querySelector("svg");
    if (svg) svg.style.transform = "rotate(" + t.heading + "deg)";

    if (t.phase !== "STANDBY") {
      const last = this.trail.getLatLngs().slice(-1)[0];
      if (!last || last.lat !== t.lat || last.lng !== t.lon) this.trail.addLatLng(pos);
    }
    this.fit(pos, false);
  }

  // Keep the drone and the whole search zone in view
  fit(dronePos, now) {
    if (!this.map || this.el.offsetWidth === 0) return;  // hidden right now
    if (!now && Date.now() - this.lastFit < FIT_EVERY_MS) return;
    this.lastFit = Date.now();
    // (zoneBounds, not zone.getBounds(): that one fails until the circle has been drawn)
    const bounds = L.latLngBounds(this.zoneBounds.getSouthWest(), this.zoneBounds.getNorthEast()).extend(dronePos);
    this.map.fitBounds(bounds, { padding: [24, 24], maxZoom: 18, animate: !now });
  }

  // Call when the map becomes visible (screen change, drop-down opened)
  refresh(dronePos) {
    if (!this.map || this.el.offsetWidth === 0) return;
    this.map.invalidateSize();
    this.fit(dronePos || this.drone.getLatLng(), true);
  }

  addIncident(item) {
    if (!this.map || item.lat == null) return;
    L.marker([item.lat, item.lon], {
      icon: L.divIcon({ className: "map-pin-alert", iconSize: [18, 18], html: "!" }),
      title: item.text,
    }).addTo(this.incidentLayer).bindTooltip(item.text, { permanent: true, direction: "right", className: "map-label map-label-alert" });
  }
}

const zoneMaps = [new ZoneMap("eta-map"), new ZoneMap("scene-map")];

function setupZoneMaps(mission) {
  zoneMaps.forEach((m) => m.setup(mission));
}

function updateZoneMaps(t) {
  zoneMaps.forEach((m) => m.update(t));
  document.getElementById("map-mini").textContent =
    t.in_search_zone ? "in zone" : t.distance_to_zone + " m";
}

function refreshZoneMaps() {
  zoneMaps.forEach((m) => m.refresh());
}

function addIncidentToMaps(item) {
  zoneMaps.forEach((m) => m.addIncident(item));
}

// The on-scene map lives in a drop-down: re-measure it when it opens
document.getElementById("map-dropdown").addEventListener("toggle", (e) => {
  if (e.target.open) zoneMaps[1].refresh();
});
