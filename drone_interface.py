"""
drone_interface.py - every piece of drone input/output lives in this file.

The rest of the app only talks to a drone through these methods:

    connect()            -> open the link to the drone
    update(dt)           -> called a few times per second by main.py
    get_telemetry()      -> dict with battery, altitude, speed, GPS, ...
    pop_events()         -> list of short status messages since last call
    drop_payload()       -> (ok, message)
    return_to_home()     -> (ok, message)

MockDrone  = fake drone used for demos (no hardware needed).
RealDrone  = empty shell with the SAME methods. Fill it in later with
             MAVLink / pymavlink to talk to the real flight controller.

Because both classes have the same methods, switching is a one-line change
in main.py (or set the environment variable DRONE_MODE=real).
"""

import math
import random

# ---------------------------------------------------------------------------
# Locations used by the mock mission
# ---------------------------------------------------------------------------
# Incident: University of Hartford, West Hartford, CT
INCIDENT = {"lat": 41.7985, "lon": -72.7148, "label": "200 Bloomfield Ave (University of Hartford)"}
# Home: a made-up drone base about 1.5 km south-west of the incident
HOME = {"lat": 41.7905, "lon": -72.7290, "label": "Drone base"}

# Flight settings for the simulator
CRUISE_ALTITUDE_M = 60      # height while travelling
ON_SCENE_ALTITUDE_M = 25    # height while hovering over the incident
CRUISE_SPEED_MS = 16        # horizontal speed in metres per second
CLIMB_RATE_MS = 4           # vertical speed in metres per second
PREFLIGHT_SECONDS = 4       # time on the ground before take-off
MAX_HOVER_SECONDS = 240     # automatically come home after this long on scene
LOW_BATTERY_PERCENT = 25    # automatically come home below this
PAYLOAD_DROP_SECONDS = 3    # how long the winch takes to lower the payload

# Human-friendly names for each phase (shown in the UI)
PHASE_LABELS = {
    "PREFLIGHT": "Pre-flight checks",
    "TAKEOFF": "Taking off",
    "EN_ROUTE": "En route to scene",
    "ON_SCENE": "On scene (hovering)",
    "RETURNING": "Returning to home",
    "LANDING": "Landing",
    "LANDED": "Landed at base",
}


def distance_m(lat1, lon1, lat2, lon2):
    """Distance in metres between two GPS points (haversine formula)."""
    r = 6371000  # Earth radius in metres
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Compass heading (0 = north, 90 = east) from point 1 towards point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


class MockDrone:
    """A pretend drone that flies home -> incident -> hovers -> home."""

    def __init__(self):
        self.reset()

    # ----- the shared interface ------------------------------------------

    def connect(self):
        """Nothing to connect to for the mock. RealDrone opens MAVLink here."""
        self._events.append("Connected to drone (mock simulator)")

    def reset(self):
        """Put the drone back on the pad with a full battery."""
        self.lat = HOME["lat"]
        self.lon = HOME["lon"]
        self.altitude = 0.0
        self.speed = 0.0
        self.heading = bearing_deg(HOME["lat"], HOME["lon"], INCIDENT["lat"], INCIDENT["lon"])
        self.battery = 100.0
        self.phase = "PREFLIGHT"
        self.phase_time = 0.0          # seconds spent in the current phase
        self.payload = "armed"         # armed -> dropping -> dropped
        self.payload_timer = 0.0
        self._events = []

    def update(self, dt):
        """Advance the simulation by dt seconds. main.py calls this ~4x per second."""
        self.phase_time += dt

        if self.phase == "PREFLIGHT":
            if self.phase_time >= PREFLIGHT_SECONDS:
                self._set_phase("TAKEOFF", "Drone launched from base")

        elif self.phase == "TAKEOFF":
            self._climb_towards(CRUISE_ALTITUDE_M, dt)
            if self.altitude >= CRUISE_ALTITUDE_M - 0.5:
                self._set_phase("EN_ROUTE", "Cruise altitude reached, heading to scene")

        elif self.phase == "EN_ROUTE":
            self._climb_towards(CRUISE_ALTITUDE_M, dt)
            arrived = self._fly_towards(INCIDENT["lat"], INCIDENT["lon"], dt)
            if arrived:
                self._set_phase("ON_SCENE", "Drone on scene, hovering over incident")

        elif self.phase == "ON_SCENE":
            self.speed = 0.0
            self._climb_towards(ON_SCENE_ALTITUDE_M, dt)  # descend to drop height
            if self.phase_time >= MAX_HOVER_SECONDS:
                self._set_phase("RETURNING", "Hover time limit reached, returning to home")

        elif self.phase == "RETURNING":
            self._climb_towards(CRUISE_ALTITUDE_M, dt)
            arrived = self._fly_towards(HOME["lat"], HOME["lon"], dt)
            if arrived:
                self._set_phase("LANDING", "Over base, landing")

        elif self.phase == "LANDING":
            self.speed = 0.0
            self._climb_towards(0, dt)
            if self.altitude <= 0.1:
                self.altitude = 0.0
                self._set_phase("LANDED", "Drone landed at base")

        # Payload winch: "dropping" lasts a few seconds, then "dropped"
        if self.payload == "dropping":
            self.payload_timer += dt
            if self.payload_timer >= PAYLOAD_DROP_SECONDS:
                self.payload = "dropped"
                self._events.append("Payload delivered to the ground")

        # Battery drains only while the motors are running
        if self.altitude > 0 or self.phase in ("TAKEOFF", "LANDING"):
            self.battery = max(0.0, self.battery - 0.15 * dt)

        # Safety: low battery forces return to home
        if self.battery < LOW_BATTERY_PERCENT and self.phase in ("EN_ROUTE", "ON_SCENE"):
            self._set_phase("RETURNING", "Low battery, automatic return to home")

    def get_telemetry(self):
        """Everything the dispatcher screen needs, as a plain dict (easy to send as JSON)."""
        to_incident = distance_m(self.lat, self.lon, INCIDENT["lat"], INCIDENT["lon"])
        from_home = distance_m(self.lat, self.lon, HOME["lat"], HOME["lon"])

        # Fake radio signal: weaker the further we are from base, plus a little noise
        signal = 98 - from_home / 40 + random.uniform(-2, 2)

        # ETA only makes sense while flying somewhere
        eta = None
        if self.phase == "EN_ROUTE":
            eta = round(to_incident / CRUISE_SPEED_MS)
        elif self.phase == "RETURNING":
            eta = round(from_home / CRUISE_SPEED_MS)

        return {
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "altitude": round(self.altitude, 1),        # metres above take-off point
            "speed": round(self.speed, 1),              # metres per second
            "heading": round(self.heading),             # degrees, 0 = north
            "battery": round(self.battery, 1),          # percent
            "signal": round(max(0, min(100, signal))),  # percent
            "flight_mode": self._flight_mode(),
            "phase": self.phase,
            "phase_label": PHASE_LABELS[self.phase],
            "payload": self.payload,
            "distance_to_incident": round(to_incident),
            "eta_seconds": eta,
        }

    def pop_events(self):
        """Return (and clear) status messages like 'Drone on scene'."""
        events, self._events = self._events, []
        return events

    def drop_payload(self):
        """Release the payload (e.g. an AED). Only allowed while hovering on scene."""
        if self.payload != "armed":
            return False, f"Payload already {self.payload}"
        if self.phase != "ON_SCENE":
            return False, "Drone must be on scene (hovering) to drop the payload"
        self.payload = "dropping"
        self.payload_timer = 0.0
        self._events.append("Payload release started")
        return True, "Dropping payload"

    def return_to_home(self):
        """Fly back to base and land."""
        if self.phase in ("PREFLIGHT", "LANDED"):
            return False, "Drone is on the ground"
        if self.phase in ("RETURNING", "LANDING"):
            return False, "Drone is already returning"
        self._set_phase("RETURNING", "Return to home ordered by dispatcher")
        return True, "Returning to home"

    # ----- helpers used only by the simulator -----------------------------

    def _set_phase(self, phase, message):
        self.phase = phase
        self.phase_time = 0.0
        self._events.append(message)

    def _climb_towards(self, target_alt, dt):
        step = CLIMB_RATE_MS * dt
        if abs(target_alt - self.altitude) <= step:
            self.altitude = float(target_alt)
        elif target_alt > self.altitude:
            self.altitude += step
        else:
            self.altitude -= step

    def _fly_towards(self, lat, lon, dt):
        """Move in a straight line towards (lat, lon). Returns True once there."""
        remaining = distance_m(self.lat, self.lon, lat, lon)
        step = CRUISE_SPEED_MS * dt
        if remaining <= step:
            self.lat, self.lon = lat, lon
            self.speed = 0.0
            return True
        self.heading = bearing_deg(self.lat, self.lon, lat, lon)
        fraction = step / remaining
        self.lat += (lat - self.lat) * fraction
        self.lon += (lon - self.lon) * fraction
        self.speed = CRUISE_SPEED_MS + random.uniform(-0.4, 0.4)
        return False

    def _flight_mode(self):
        """Map our phases onto ArduPilot-style flight mode names."""
        return {
            "PREFLIGHT": "STANDBY",
            "TAKEOFF": "GUIDED",
            "EN_ROUTE": "GUIDED",
            "ON_SCENE": "LOITER",
            "RETURNING": "RTL",
            "LANDING": "LAND",
            "LANDED": "DISARMED",
        }[self.phase]


class RealDrone:
    """
    The real drone. Same methods as MockDrone, not implemented yet.

    Plan: use pymavlink to talk to the flight controller, e.g.
        from pymavlink import mavutil
        self.master = mavutil.mavlink_connection("udp:127.0.0.1:14550")
        self.master.wait_heartbeat()
    then read GLOBAL_POSITION_INT, SYS_STATUS, VFR_HUD and HEARTBEAT
    messages in update(), and send commands (MAV_CMD_DO_SET_SERVO for the
    payload release, MAV_CMD_NAV_RETURN_TO_LAUNCH for RTH).
    """

    def __init__(self, connection_string="udp:127.0.0.1:14550"):
        self.connection_string = connection_string
        self._events = []

    def connect(self):
        raise NotImplementedError("RealDrone.connect: open the MAVLink connection here")

    def reset(self):
        pass  # a real drone can't be magically reset

    def update(self, dt):
        raise NotImplementedError("RealDrone.update: read new MAVLink messages here")

    def get_telemetry(self):
        # Must return the same keys as MockDrone.get_telemetry()
        raise NotImplementedError("RealDrone.get_telemetry")

    def pop_events(self):
        events, self._events = self._events, []
        return events

    def drop_payload(self):
        raise NotImplementedError("RealDrone.drop_payload: send a servo/relay command here")

    def return_to_home(self):
        raise NotImplementedError("RealDrone.return_to_home: send MAV_CMD_NAV_RETURN_TO_LAUNCH")
