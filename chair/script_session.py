"""ScriptSession: drives the chair from the YAML branching script instead of an LLM.

Exposes the same .step(button_event, on_text=None) interface as Session so
host.py can swap it in transparently when model == "script:v2".
"""

import json
import os
import re
import time

_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "content", "chair_script_v2.json",
)

# YAML program dicts → massage normalize() format.
# rollers: wave→roll, knead→knead, pulse→pound, still→none
_ROLLER_MAP = {"wave": "roll", "knead": "knead", "pulse": "pound", "still": "none"}
# zone → areas list
_ZONE_MAP = {
    "full":  ["back", "shoulders", "legs"],
    "upper": ["shoulders", "back"],
    "lower": ["lower_back", "legs"],
    "neck":  ["neck", "shoulders"],
    "none":  ["back"],
}

def _program_to_massage(prog):
    """Convert a YAML program dict to a massage.normalize()-ready dict."""
    rollers  = prog.get("rollers", "knead")
    speed    = prog.get("speed", 0.3)
    depth    = prog.get("depth", 1)
    zone     = prog.get("zone", "full")
    airbags  = prog.get("airbags", "off")
    return {
        "technique": _ROLLER_MAP.get(rollers, "knead"),
        "intensity": int(min(100, depth * 25 + 5)),
        "speed":     int(min(100, speed * 100)),
        "areas":     _ZONE_MAP.get(zone, ["back"]),
        "airbags":   airbags != "off",
        "vibration": 0,
        "led_color": "warm amber",
    }


# Map event strings from buttons.event_for() back to YAML routing keys.
_EVENT_TO_KEY = {
    "[button: YES]":        "yes",
    "[button: NO]":         "no",
    "[button: MAYBE]":      "maybe",
    "[they pressed the KILL switch]": "kill",
    "[button: REPEAT]":     "repeat",
    "[button: THUMB UP]":   "thumb_up",
    "[button: THUMB DOWN]": "thumb_down",
    "[button: HORN]":       "horn",
    "[button: SETTINGS]":   "yes",   # no script key; fall through to yes
    "[language switch]":    "language",
    "[language switch: up]":   "language",
    "[language switch: down]": "language",
}

_OPTION_RE = re.compile(r"\[chose screen option: ['\"](.+?)['\"]\]")
_INLINE_RE  = re.compile(r"\[\[(\w+):([^\]]+)\]\]")


def _strip_inline(text, profile_note=""):
    """Remove/replace [[directive:arg]] tags from spoken text."""
    def _sub(m):
        tag, arg = m.group(1), m.group(2)
        if tag == "pause":
            return ""
        if tag == "motor":
            return ""
        if tag == "profile":
            return profile_note or "You are exactly what the data suggested."
        return ""
    return _INLINE_RE.sub(_sub, text).strip()


def _clean_spaces(text):
    return re.sub(r"  +", " ", text).strip()


class ScriptSession:
    """A finite-state machine over chair_script_v2.json with the Session interface."""

    model = "script:v2"

    def __init__(self, session_s=600, clock=None, script_path=None):
        self.session_s  = session_s
        self._clock     = clock or time.monotonic
        self._t0        = self._clock()
        self.history    = []
        self.profile    = {"note": "", "inferred_traits": []}
        self.sentiment_log = []

        path = script_path or _SCRIPT_PATH
        try:
            with open(path, encoding="utf-8") as f:
                script = json.load(f)
        except FileNotFoundError:
            raise ValueError(f"Script not found: {path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Script JSON invalid ({path}): {e}")

        # Validate required keys
        if "nodes" not in script:
            raise ValueError(f"Script missing 'nodes' key: {path}")
        if not isinstance(script["nodes"], dict) or not script["nodes"]:
            raise ValueError(f"Script 'nodes' must be a non-empty dict: {path}")

        self._nodes    = script["nodes"]
        self._programs = script.get("programs", {})
        self._global   = script.get("global", {})
        self._fallbacks = script.get("profile_fallbacks", {})

        self._node_id  = "W0"        # current node
        self._prev_id  = None        # for "return" routes
        self._horn_count     = 0
        self._volume_count   = 0
        self._repeat_count   = 0
        self._manipulation   = False
        self._lang           = "en"
        self._rating         = 0     # sum of thumb nudges

    # -- timing (mirrors Session) -----------------------------------------
    @property
    def elapsed(self):
        return self._clock() - self._t0

    @property
    def remaining(self):
        return max(0.0, self.session_s - self.elapsed)

    @property
    def phase(self):
        node = self._nodes.get(self._node_id, {})
        return node.get("phase", "calibration")

    @property
    def expired(self):
        return self.elapsed >= self.session_s

    # -- step (mirrors Session) -------------------------------------------
    def step(self, button_event, on_text=None):
        t0 = time.monotonic()

        key = self._event_to_key(button_event)

        # For session_start / system events: speak the current node, no routing.
        is_system = button_event in ("session_start", "headphones_back", "sitting_back")

        if is_system:
            spoken_override = None
            next_id = None
        else:
            spoken_override, next_id = self._dispatch(key)

        # Advance to destination node (spoken_override may be fully custom for globals).
        if next_id and next_id not in ("return",):
            self._prev_id = self._node_id
            self._node_id = next_id
        elif next_id == "return" and self._prev_id:
            self._node_id = self._prev_id

        # Set manipulation flag based on node prefix / set block.
        node = self._nodes.get(self._node_id, {})
        if self._node_id.startswith("M_") or (node.get("set") or {}).get("manipulation_active"):
            self._manipulation = True

        phase    = node.get("phase", "calibration")
        screens  = node.get("screens", {})
        s_opts   = [str(screens.get(f"s{i}", "…")) for i in range(1, 4)]
        prog_name = node.get("massage", "steady")
        prog      = self._programs.get(prog_name, {})
        massage   = _program_to_massage(prog) if prog else {
            "technique": "knead", "intensity": 30, "speed": 30,
            "areas": ["back"], "airbags": False, "vibration": 0, "led_color": "warm amber",
        }

        # Determine spoken text.
        if spoken_override is not None:
            # Global handler (kill/repeat/horn/thumb/language) provided its own text.
            spoken = spoken_override
        else:
            # Normal case: speak the destination node's text, with opener for the pressed key.
            openers = node.get("openers") or {}
            opener  = openers.get(key, "")
            base    = node.get("spoken", "")
            spoken  = (opener + " " + base).strip() if opener else base

        note = self.profile.get("note", "")
        spoken_clean = _clean_spaces(_strip_inline(spoken, note))

        # stream text so TTS can pipeline
        if on_text and spoken_clean:
            on_text(spoken_clean)

        self.sentiment_log.append("neutral")
        self.history.append({"button_event": button_event, "spoken_text": spoken_clean, "phase": phase})

        resp = {
            "spoken_text":    spoken_clean,
            "screen_options": s_opts,
            "massage":        massage,
            "button_leds":    {"settings": 30, "yes": 50, "no": 50},
            "profile_update": {
                "sentiment":       "neutral",
                "inferred_traits": self.profile.get("inferred_traits", []),
                "note":            self.profile.get("note", ""),
            },
            "phase": phase,
        }
        meta = {"latency_s": round(time.monotonic() - t0, 3)}
        return resp, meta

    # -- internal routing -------------------------------------------------
    def _event_to_key(self, event_str):
        """Map a button event string to a YAML routing key."""
        key = _EVENT_TO_KEY.get(event_str)
        if key:
            return key

        # option button: "[chose screen option: 'LABEL']"
        m = _OPTION_RE.match(event_str)
        if m:
            label = m.group(1)
            node = self._nodes.get(self._node_id, {})
            screens = node.get("screens", {})
            for i in range(1, 4):
                if screens.get(f"s{i}") == label:
                    return f"s{i}"
            return "yes"   # fallback

        # volume: "[volume: N/5]"
        if event_str.startswith("[volume:"):
            return "volume"

        # system events → treat as yes/continue
        return "yes"

    def _dispatch(self, key):
        """Return (spoken_override|None, next_node_id|None).

        spoken_override is non-None only for global handlers that supply their own
        text (kill ack, repeat, horn, thumb ack, language ack).  For normal routing
        it is None and step() reads from the destination node.
        """
        node = self._nodes.get(self._node_id, {})

        # --- KILL: two-stage global handler ---
        if key == "kill":
            g_kill = self._global.get("kill", {})
            if self._manipulation:
                route = (g_kill.get("when_during_manipulation") or {}).get("route", "E_killed")
                return None, route
            else:
                info = g_kill.get("when_before_manipulation", {})
                phase = node.get("phase", "")
                ack = (info.get("ack_by_phase") or {}).get(phase, "")
                route = info.get("route", "M_withhold0")
                # ack is spoken right now; destination node text spoken on arrival
                return (_strip_inline(ack) or None), route

        # --- REPEAT ---
        if key == "repeat":
            g_rep = self._global.get("repeat", {})
            self._repeat_count += 1
            openers = g_rep.get("openers_first", [])
            if self._repeat_count <= len(openers):
                prefix = openers[self._repeat_count - 1]
            else:
                prefix = g_rep.get("opener_escalated", "")
            base = node.get("spoken", "")
            return (_strip_inline((prefix + " " + base).strip()) or None), self._node_id

        # --- HORN ---
        if key == "horn":
            g_horn = self._global.get("horn", {})
            self._horn_count += 1
            thresh = g_horn.get("threshold", 4)
            if self._horn_count >= thresh:
                self._horn_count = 0
                return None, g_horn.get("on_threshold", {}).get("route")
            lines = g_horn.get("stock_lines", [])
            line = lines[(self._horn_count - 1) % len(lines)] if lines else ""
            return _strip_inline(line), None

        # --- VOLUME ---
        if key == "volume":
            g_vol = self._global.get("volume", {})
            self._volume_count += 1
            if self._volume_count >= g_vol.get("fidget_threshold", 5):
                self._volume_count = 0
                return None, g_vol.get("on_threshold", {}).get("route")
            return None, None

        # --- THUMB_UP / THUMB_DOWN ---
        if key == "thumb_up":
            self._rating += 1
            g_thu = self._global.get("thumb_up", {})
            spoken = _strip_inline(g_thu.get("ack", "Noted."))
            node_next = (node.get("next") or {}).get("thumb_up")
            return spoken, node_next

        if key == "thumb_down":
            self._rating -= 1
            g_thd = self._global.get("thumb_down", {})
            spoken = _strip_inline(g_thd.get("ack", "Noted."))
            node_next = (node.get("next") or {}).get("thumb_down")
            return spoken, node_next

        # --- LANGUAGE ---
        if key == "language":
            g_lang = self._global.get("language", {})
            if self._lang == "en":
                self._lang = "nl"
                spoken = _strip_inline(g_lang.get("ack_to_nl", ""))
            else:
                self._lang = "en"
                spoken = _strip_inline(g_lang.get("ack_to_en", ""))
            return spoken, None

        # --- Normal node routing → let step() read the destination node ---
        next_routes = node.get("next") or {}
        next_id = next_routes.get(key) or next_routes.get("any")
        return None, next_id
