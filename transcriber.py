"""
transcriber.py - turns the 911 call audio into text lines.

The rest of the app only uses these:

    poll(dt, telemetry) -> list of new transcript lines, each a dict:
                           {"speaker": "CALLER" | "DISPATCH", "text": "..."}
    reset()             -> start a new call
    caller_number       -> the caller's phone number (shown on the incoming-call screen)

MockTranscriber plays back one of a few scripted calls so the demo works
with no audio. Each new call picks one at random, so every drone type
(EpiPen, AED, bleeding kit) gets used.

To use a real speech-to-text service later (Whisper, Deepgram, Google, ...),
write a new class with the same methods. A typical design: a background
thread receives audio and pushes finished sentences into a queue, and poll()
simply empties that queue and returns the lines.
"""

import random

# How each payload is said in the middle of a sentence ("the AED", "the EpiPen", ...)
SPOKEN_PAYLOAD_NAMES = {"epipen": "EpiPen", "aed": "AED", "bleed_kit": "bleeding control kit"}

# Each line of a script:
#   (seconds to wait after the previous line, speaker, text, wait_for)
#
# wait_for makes a line wait for something to happen, so the call matches
# what the dispatcher does:
#   None              -> no condition
#   "dispatched"      -> the dispatcher has sent a drone
#   "on_scene"        -> the drone is hovering over the incident
#   "payload_dropped" -> the payload has reached the ground
#
# "{payload}" in a line is replaced with the payload the dispatcher picked.
SCENARIOS = {
    "cardiac": {
        "caller_number": "(860) 555-0142",
        "script": [
            (1, "DISPATCH", "911, what is the address of your emergency?", None),
            (3, "CALLER", "I'm at the University of Hartford, 200 Bloomfield Avenue in West Hartford, by the main parking lot.", None),
            (3, "DISPATCH", "Okay, tell me exactly what happened.", None),
            (3, "CALLER", "A man just collapsed in front of me. He's not moving and I don't think he's breathing!", None),
            (3, "DISPATCH", "Stay with me. I'm sending help right now.", None),
            (1, "DISPATCH", "A drone carrying the {payload} is on its way. It will be there in seconds.", "dispatched"),
            (3, "DISPATCH", "Put him flat on his back. Push hard and fast in the center of his chest, twice a second.", None),
            (3, "CALLER", "Okay, I'm doing compressions.", None),
            (1, "CALLER", "I can hear it! The drone is right above us!", "on_scene"),
            (3, "DISPATCH", "It's going to lower the {payload} to you. Grab it once it's on the ground.", None),
            (1, "CALLER", "It's down, I've got it!", "payload_dropped"),
            (3, "DISPATCH", "Open it and follow the voice instructions. Put the pads where the pictures show.", None),
            (6, "CALLER", "It shocked him... wait, he's breathing! He's breathing again!", None),
            (3, "DISPATCH", "Great job. Roll him onto his side. Paramedics are almost there.", None),
        ],
    },
    "allergy": {
        "caller_number": "(860) 555-0187",
        "script": [
            (1, "DISPATCH", "911, what is the address of your emergency?", None),
            (3, "CALLER", "We're at 200 Bloomfield Avenue, West Hartford. The picnic tables outside the student center.", None),
            (3, "DISPATCH", "Tell me what's happening.", None),
            (3, "CALLER", "My friend ate something with peanuts. Her throat is swelling and she can barely breathe!", None),
            (3, "DISPATCH", "Does she have an EpiPen with her?", None),
            (3, "CALLER", "No, she left it at home!", None),
            (3, "DISPATCH", "Okay, stay calm. I'm sending help right now.", None),
            (1, "DISPATCH", "A drone carrying the {payload} is on its way. It will be there in seconds.", "dispatched"),
            (3, "DISPATCH", "Keep her sitting up and keep talking to her.", None),
            (1, "CALLER", "The drone is here, it's right over us!", "on_scene"),
            (3, "DISPATCH", "It's going to lower the {payload} to you. Grab it once it's on the ground.", None),
            (1, "CALLER", "Got it!", "payload_dropped"),
            (3, "DISPATCH", "Pull off the blue safety cap. Press the orange tip hard into the outside of her thigh and hold for three seconds.", None),
            (6, "CALLER", "Done... she's breathing easier. She can talk again.", None),
            (3, "DISPATCH", "Good job. Keep her sitting up. Paramedics are on the way.", None),
        ],
    },
    "bleeding": {
        "caller_number": "(860) 555-0123",
        "script": [
            (1, "DISPATCH", "911, what is the address of your emergency?", None),
            (3, "CALLER", "200 Bloomfield Avenue in West Hartford, the University of Hartford. Outside the sports center.", None),
            (3, "DISPATCH", "Tell me what happened.", None),
            (3, "CALLER", "A guy fell through a glass door. His leg is cut really bad, the blood is spurting out!", None),
            (3, "DISPATCH", "Press down hard on the wound with anything you have. Don't let go.", None),
            (3, "DISPATCH", "I'm sending help right now.", None),
            (1, "DISPATCH", "A drone carrying the {payload} is on its way. It will be there in seconds.", "dispatched"),
            (3, "CALLER", "I'm pressing but it's soaking through!", None),
            (3, "DISPATCH", "Keep pressing. Push harder, with both hands.", None),
            (1, "CALLER", "The drone's here!", "on_scene"),
            (3, "DISPATCH", "It's going to lower the {payload} to you. Grab it once it's on the ground.", None),
            (1, "CALLER", "I've got the kit!", "payload_dropped"),
            (3, "DISPATCH", "Take out the tourniquet. Put it high on the leg above the cut, pull it tight and twist the rod until the bleeding stops.", None),
            (6, "CALLER", "It's tight... the bleeding stopped.", None),
            (3, "DISPATCH", "Good job. Don't loosen it. Paramedics are close.", None),
        ],
    },
}


class MockTranscriber:
    """Releases one scripted line at a time, as if someone were speaking."""

    def __init__(self):
        self.reset()

    def reset(self, scenario=None):
        """Start a new call. Picks a random scenario unless one is named."""
        self.scenario = scenario or random.choice(list(SCENARIOS))
        self.script = SCENARIOS[self.scenario]["script"]
        self.caller_number = SCENARIOS[self.scenario]["caller_number"]
        self.index = 0        # which line of the script is next
        self.waited = 0.0     # seconds since the previous line

    def poll(self, dt, telemetry):
        """Called by main.py every tick. Returns a list of new lines (often empty)."""
        self.waited += dt
        if self.index >= len(self.script):
            return []  # the call has finished

        delay, speaker, text, wait_for = self.script[self.index]
        if self.waited < delay or not self._condition_met(wait_for, telemetry):
            return []

        self.index += 1
        self.waited = 0.0
        payload = SPOKEN_PAYLOAD_NAMES.get(telemetry.get("payload_type"), "medical kit")
        return [{"speaker": speaker, "text": text.replace("{payload}", payload)}]

    @staticmethod
    def _condition_met(wait_for, telemetry):
        if wait_for is None:
            return True
        if wait_for == "dispatched":
            return telemetry["phase"] != "STANDBY"
        if wait_for == "on_scene":
            return telemetry["phase"] == "ON_SCENE"
        if wait_for == "payload_dropped":
            return telemetry["payload"] == "dropped"
        return True
