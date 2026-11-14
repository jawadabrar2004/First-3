"""
transcriber.py - turns the 911 call audio into text lines.

The rest of the app only uses two methods:

    poll(dt, telemetry) -> list of new transcript lines, each a dict:
                           {"speaker": "CALLER" | "DISPATCH", "text": "..."}
    reset()             -> start the call over

MockTranscriber plays back a scripted call so the demo works with no audio.

To use a real speech-to-text service later (Whisper, Deepgram, Google, ...),
write a new class with the same two methods. A typical design: a background
thread receives audio and pushes finished sentences into a queue, and poll()
simply empties that queue and returns the lines.
"""

# Each step of the scripted call:
#   (seconds to wait after the previous line, speaker, text, wait_for)
# wait_for lets a line wait for something the drone does, so the story
# matches the map:
#   None              -> no condition
#   "near_scene"      -> drone is within 250 m of the incident
#   "payload_dropped" -> the payload has reached the ground
SCRIPT = [
    (2, "DISPATCH", "911, what is the address of your emergency?", None),
    (4, "CALLER", "I'm at the University of Hartford, 200 Bloomfield Avenue in West Hartford. By the main parking lot.", None),
    (4, "DISPATCH", "Okay, tell me exactly what happened.", None),
    (4, "CALLER", "A man just collapsed right in front of me. He's not moving!", None),
    (4, "DISPATCH", "Is he awake? Is he breathing?", None),
    (5, "CALLER", "He's unconscious. I don't think he's breathing. His lips are turning blue.", None),
    (4, "DISPATCH", "Okay, help is on the way. We are sending a drone with a defibrillator right now.", None),
    (4, "DISPATCH", "What's the phone number you're calling from, in case we get disconnected?", None),
    (4, "CALLER", "My number is 860-555-0142.", None),
    (4, "DISPATCH", "How old is he, roughly?", None),
    (4, "CALLER", "Maybe fifty or sixty.", None),
    (4, "DISPATCH", "I'm going to tell you how to do CPR. Get him flat on his back on the ground.", None),
    (5, "CALLER", "Okay, he's on his back.", None),
    (4, "DISPATCH", "Put the heel of your hand in the center of his chest, other hand on top. Push hard and fast, twice a second.", None),
    (5, "CALLER", "I'm doing it. One, two, three, four...", None),
    (6, "DISPATCH", "You're doing great. Keep going, don't stop.", None),
    (10, "CALLER", "How long until help gets here?", None),
    (4, "DISPATCH", "The drone is less than a minute away. Keep pushing, hard and fast.", None),
    (10, "CALLER", "I'm getting tired...", None),
    (4, "DISPATCH", "If anyone else is there, have them take over. Don't stop compressions.", None),
    (5, "CALLER", "Someone's here, she's taking over now.", None),
    (2, "CALLER", "I can hear something... it's the drone! It's right above us!", "near_scene"),
    (4, "DISPATCH", "The drone is going to lower a defibrillator to you. Keep doing CPR until it's on the ground.", None),
    (3, "CALLER", "It's down! I've got it.", "payload_dropped"),
    (4, "DISPATCH", "Open the lid and follow the voice instructions. Put the pads where the pictures show.", None),
    (6, "CALLER", "Pads are on. It says shock advised... it shocked him.", None),
    (6, "CALLER", "Wait... he's breathing! He's breathing again! He's waking up!", None),
    (4, "DISPATCH", "Great job. Roll him onto his side. Paramedics are two minutes away.", None),
]


class MockTranscriber:
    """Releases one scripted line at a time, as if someone were speaking."""

    def __init__(self, script=SCRIPT):
        self.script = script
        self.reset()

    def reset(self):
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
        return [{"speaker": speaker, "text": text}]

    @staticmethod
    def _condition_met(wait_for, telemetry):
        if wait_for is None:
            return True
        if wait_for == "near_scene":
            return telemetry["distance_to_incident"] < 250
        if wait_for == "payload_dropped":
            return telemetry["payload"] == "dropped"
        return True
