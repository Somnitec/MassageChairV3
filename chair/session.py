"""The session engine: pacing (phases), memory, profile/sentiment tracking.

Pacing is enforced here, not by the model: we compute the target phase from
elapsed wall-clock time (or a simulated clock) and tell the model which phase it
is in. The model only echoes it back.
"""

import time

import config
from chair import llm, persona, massage
from chair.schema import output_schema


def phase_for(elapsed_s, session_s):
    """Return the phase name for a given elapsed time."""
    frac = elapsed_s / session_s if session_s else 1.0
    current = config.PHASE_BOUNDARIES[0][0]
    for name, start in config.PHASE_BOUNDARIES:
        if frac >= start:
            current = name
        else:
            break
    return current


class Session:
    """One participant's run with the chair."""

    def __init__(self, model=config.DEFAULT_MODEL,
                 session_s=config.SESSION_SECONDS, clock=None):
        self.model = model
        self.session_s = session_s
        self.history = []                 # list of past turns
        self.profile = {}                 # running read on the participant
        self.sentiment_log = []           # sentiment per turn, for tracking
        self._clock = clock or time.monotonic
        self._t0 = self._clock()

    # -- timing -----------------------------------------------------------
    @property
    def elapsed(self):
        return self._clock() - self._t0

    @property
    def remaining(self):
        return max(0.0, self.session_s - self.elapsed)

    @property
    def phase(self):
        return phase_for(self.elapsed, self.session_s)

    @property
    def expired(self):
        return self.elapsed >= self.session_s

    # -- one turn ---------------------------------------------------------
    def step(self, button_event, on_text=None):
        """Process one button press, return a normalized response dict + meta.

        If `on_text` is given, the chair's spoken line is streamed to it as it
        generates (see llm.chat); the full turn is still returned as usual.
        """
        phase = self.phase
        messages = persona.build_messages(
            phase=phase,
            elapsed_s=self.elapsed,
            remaining_s=self.remaining,
            profile=self.profile,
            history=self.history,
            button_event=button_event,
        )
        raw, meta = llm.chat(self.model, messages, output_schema(), on_text=on_text)
        resp = self._normalize(raw, phase)

        # update running profile + sentiment tracking
        pu = resp["profile_update"]
        self.sentiment_log.append(pu["sentiment"])
        self.profile = {
            "sentiment": pu["sentiment"],
            "note": pu.get("note", self.profile.get("note", "")),
            "inferred_traits": self._merge_traits(pu.get("inferred_traits", [])),
        }

        self.history.append({
            "button_event": button_event,
            "spoken_text": resp["spoken_text"],
            "phase": phase,
        })
        return resp, meta

    # -- helpers ----------------------------------------------------------
    def _merge_traits(self, new_traits):
        seen = list(self.profile.get("inferred_traits", []))
        for t in new_traits:
            if t and t not in seen:
                seen.append(t)
        return seen[-8:]  # keep it bounded

    def _normalize(self, raw, phase):
        raw = dict(raw or {})
        opts = list(raw.get("screen_options") or [])
        opts = (opts + ["…", "…", "…"])[:3]
        pu = raw.get("profile_update") or {}
        leds_raw = raw.get("button_leds") or {}
        return {
            "spoken_text": str(raw.get("spoken_text", "")).strip(),
            "screen_options": [str(o) for o in opts],
            "massage": massage.normalize(raw.get("massage")),
            "button_leds": {
                "settings": max(0, min(100, int(leds_raw.get("settings", 30)))),
                "yes":      max(0, min(100, int(leds_raw.get("yes", 30)))),
                "no":       max(0, min(100, int(leds_raw.get("no", 30)))),
            },
            "profile_update": {
                "sentiment": pu.get("sentiment", "neutral"),
                "inferred_traits": pu.get("inferred_traits", []) or [],
                "note": pu.get("note", ""),
            },
            "phase": raw.get("phase", phase),
        }
