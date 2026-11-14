"""
key_info.py - pulls the important facts out of the call transcript.

Output (always the same keys, None when not heard yet):
    {
      "address":          "200 Bloomfield Avenue",
      "emergency_type":   "Cardiac arrest (suspected)",
      "patient_status":   "Unconscious, not breathing",
      "patient_critical": True,
      "callback_number":  "860-555-0142",
    }

KeywordExtractor uses simple keyword and regular-expression matching.
To switch to an LLM later, write a class with the same extract() method
(see LLMExtractor at the bottom) and change one line in main.py.
"""

import re

# A street address: a house number, 1-4 words, then a street type.
# Example match: "200 Bloomfield Avenue"
ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+(?:[A-Z][a-zA-Z]*\s+){1,4}"
    r"(?:Avenue|Ave|Street|St|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Court|Ct|Place|Pl|Parkway|Pkwy)\b\.?"
)
# Optional town right after the address, e.g. "in West Hartford"
TOWN_RE = re.compile(r"^\s*(?:,|in)\s+((?:[A-Z][a-z]+\s?){1,3})")

# US phone numbers: 860-555-0142, (860) 555 0142, 860.555.0142
PHONE_RE = re.compile(r"\(?\b(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})\b")

# "not breathing", "isn't breathing", "I don't think he's breathing", ...
# (a negative word, then up to 3 more words, then "breathing")
NOT_BREATHING_RE = re.compile(r"\b(?:not|no|isn't|don't|doesn't|stopped)\b(?:\s+\S+){0,3}?\s+breathing")

# Keyword -> emergency type. The first matching rule wins, so put the most
# specific ones first.
EMERGENCY_RULES = [
    (["not breathing", "collapsed", "no pulse", "heart attack", "cardiac"], "Cardiac arrest (suspected)"),
    (["overdose", "took too many", "pills"], "Overdose"),
    (["fire", "smoke", "burning"], "Fire"),
    (["car accident", "crash", "hit by a car"], "Traffic accident"),
    (["bleeding", "stabbed", "shot", "gun"], "Trauma / bleeding"),
    (["drowning", "in the water"], "Drowning"),
    (["choking"], "Choking"),
]


class KeywordExtractor:
    """Simple rules-based extractor. Good enough for the demo script."""

    def extract(self, lines):
        """lines = list of {"speaker", "text"} dicts. Returns the key-info dict."""
        info = {
            "address": None,
            "emergency_type": None,
            "patient_status": None,
            "patient_critical": False,
            "callback_number": None,
        }
        consciousness = None  # latest thing the caller said about being awake
        breathing = None      # latest thing the caller said about breathing

        # Only the caller's words count: the dispatcher's questions
        # ("Is he breathing?") would confuse the keyword matching.
        for line in lines:
            if line["speaker"] != "CALLER":
                continue
            text = line["text"]
            low = text.lower()

            m = ADDRESS_RE.search(text)
            if m:
                address = m.group(0).rstrip(".")
                town = TOWN_RE.match(text[m.end():])
                if town:
                    address += ", " + town.group(1).strip()
                info["address"] = address

            m = PHONE_RE.search(text)
            if m:
                info["callback_number"] = "-".join(m.groups())

            if info["emergency_type"] is None:
                for keywords, label in EMERGENCY_RULES:
                    if any(k in low for k in keywords):
                        info["emergency_type"] = label
                        break

            # Later statements overwrite earlier ones, so the status stays current.
            if any(k in low for k in ["unconscious", "unresponsive", "not moving", "passed out"]):
                consciousness = "Unconscious"
            if any(k in low for k in ["waking up", "awake", "conscious again"]):
                consciousness = "Conscious"
            # Check the negative phrases first: "not breathing" contains "breathing".
            if NOT_BREATHING_RE.search(low):
                breathing = "not breathing"
            elif "breathing" in low:
                breathing = "breathing"

        parts = [p for p in [consciousness, breathing] if p]
        if parts:
            status = ", ".join(parts)
            info["patient_status"] = status[0].upper() + status[1:]
            info["patient_critical"] = breathing == "not breathing" or (
                consciousness == "Unconscious" and breathing != "breathing"
            )
        return info


class LLMExtractor:
    """
    Placeholder for an LLM-based extractor. Same extract() method.

    Rough idea:
        transcript = "\\n".join(f'{l["speaker"]}: {l["text"]}' for l in lines)
        ask the model to return JSON with the keys listed at the top of this file,
        parse it, and return the dict. Keep the API key in a .env file.
    """

    def extract(self, lines):
        raise NotImplementedError("Call your LLM API here")
