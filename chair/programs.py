"""Named massage programs: timing choreographies, breathing patterns, duty cycles.

Each program dict drives ProgramRunner in host.py. The AI controls intensity
and sentiment; programs control *when* things happen — duty cycles, breathing
rhythm, roller sequence.

Timing params exposed to the dashboard as range sliders; overrides from the
dashboard are passed in at runtime by the runner.
"""

import random

# ---------------------------------------------------------------------------
# Breathing profiles
# cycle_s:      baseline seconds for one full breath (inhale + exhale)
# variability:  fractional ± jitter applied per breath
# inhale_frac:  fraction of the cycle spent inflating
# ---------------------------------------------------------------------------
BREATHING_PROFILES = {
    "idle":         {"cycle_s": 14.0, "variability": 0.25, "inhale_frac": 0.42},
    "excitement":   {"cycle_s": 10.5, "variability": 0.20, "inhale_frac": 0.40},
    "active":       {"cycle_s":  8.0, "variability": 0.28, "inhale_frac": 0.40},
    "manipulation": {"cycle_s":  6.0, "variability": 0.35, "inhale_frac": 0.38},
}

# Phase → breathing multiplier. Higher = shorter cycle = faster.
PHASE_BREATH_MULT = {
    "idle":        1.00,
    "excitement":  1.10,
    "intro":       1.00,
    "exploration": 1.08,
    "deepening":   1.25,
    "winddown":    0.88,
    "ending":      0.75,
}


# ---------------------------------------------------------------------------
# Roller choreography helpers
# Each step: knead/pound booleans, motor direction, duration in seconds.
# ---------------------------------------------------------------------------

def _gentle_roll(speed_s=10.0):
    return [
        {"knead": True,  "pound": False, "direction": "up",   "duration_s": speed_s},
        {"knead": True,  "pound": False, "direction": "stop", "duration_s": 0.6},
        {"knead": True,  "pound": False, "direction": "down", "duration_s": speed_s},
        {"knead": True,  "pound": False, "direction": "stop", "duration_s": 0.6},
    ]


def _knead_up_pound_down(speed_s=7.5):
    """Knead while ascending, pound while descending."""
    return [
        {"knead": True,  "pound": False, "direction": "up",   "duration_s": speed_s},
        {"knead": False, "pound": False, "direction": "stop", "duration_s": 0.8},
        {"knead": False, "pound": True,  "direction": "down", "duration_s": speed_s},
        {"knead": False, "pound": False, "direction": "stop", "duration_s": 1.2},
    ]


def _pulse_pound(dwell_s=2.0, travel_s=5.0):
    """Pound while moving; pulse in place at each end."""
    return [
        {"knead": False, "pound": True,  "direction": "up",   "duration_s": travel_s},
        {"knead": False, "pound": True,  "direction": "stop", "duration_s": dwell_s},
        {"knead": False, "pound": True,  "direction": "down", "duration_s": travel_s},
        {"knead": False, "pound": True,  "direction": "stop", "duration_s": dwell_s},
    ]


def _knead_stop_pound():
    """Move kneading, stop, pound at each end."""
    return [
        {"knead": True,  "pound": False, "direction": "up",   "duration_s": 5.0},
        {"knead": False, "pound": False, "direction": "stop", "duration_s": 0.4},
        {"knead": False, "pound": True,  "direction": "stop", "duration_s": 3.0},
        {"knead": False, "pound": False, "direction": "stop", "duration_s": 0.3},
        {"knead": True,  "pound": False, "direction": "down", "duration_s": 5.0},
        {"knead": False, "pound": True,  "direction": "stop", "duration_s": 3.0},
        {"knead": False, "pound": False, "direction": "stop", "duration_s": 0.4},
    ]


# ---------------------------------------------------------------------------
# Program registry
#
# airbag_zones:       which zone valves breathe. The outside airbag always
#                     follows the pump (it is the "wrapper" airbag).
# airbag_on_s:        default inflate duration (s); dashboard can override.
# airbag_off_s:       default deflate/rest duration (s).
# butt_on_s:          vibration duty-cycle on time (0 = disabled).
# butt_off_s:         vibration duty-cycle off time.
# roller_choreography:sequence of roller steps (see helpers above).
# initial_recline:    chair position when program starts: 0 = up, 100 = fully down.
# base_led_color:     default LED color (overridden by AI on each turn).
# ---------------------------------------------------------------------------
PROGRAMS = {
    "neck_shoulders": {
        "description": "Gentle kneading at neck and shoulders",
        "breathing_profile": "idle",
        "airbag_zones":    ["shoulders"],
        "airbag_on_s":     5.5,
        "airbag_off_s":    8.5,
        "butt_on_s":       0,
        "butt_off_s":      0,
        "roller_choreography": _gentle_roll(10.0),
        "initial_recline": 20,
        "base_led_color":  "warm amber",
    },
    "full_back": {
        "description": "Full back — knead up, pound down",
        "breathing_profile": "active",
        "airbag_zones":    ["shoulders"],
        "airbag_on_s":     4.5,
        "airbag_off_s":    5.5,
        "butt_on_s":       0,
        "butt_off_s":      0,
        "roller_choreography": _knead_up_pound_down(8.0),
        "initial_recline": 40,
        "base_led_color":  "deep blue",
    },
    "back_pound": {
        "description": "Heavy pounding, full back, butt vibration",
        "breathing_profile": "manipulation",
        "airbag_zones":    [],
        "airbag_on_s":     0,
        "airbag_off_s":    0,
        "butt_on_s":       4.0,
        "butt_off_s":      3.0,
        "roller_choreography": _pulse_pound(2.0, 5.0),
        "initial_recline": 50,
        "base_led_color":  "red",
    },
    "legs_feet": {
        "description": "Legs and feet — airbag squeeze with butt duty cycle",
        "breathing_profile": "active",
        "airbag_zones":    ["legs"],
        "airbag_on_s":     6.0,
        "airbag_off_s":    6.0,
        "butt_on_s":       5.0,
        "butt_off_s":      7.0,
        "roller_choreography": _gentle_roll(12.0),
        "initial_recline": 60,
        "base_led_color":  "teal",
    },
    "full_body": {
        "description": "Full body — knead, stop, pound; all zones breathing",
        "breathing_profile": "manipulation",
        "airbag_zones":    ["shoulders", "arms", "legs"],
        "airbag_on_s":     5.0,
        "airbag_off_s":    5.0,
        "butt_on_s":       6.0,
        "butt_off_s":      4.0,
        "roller_choreography": _knead_stop_pound(),
        "initial_recline": 70,
        "base_led_color":  "violet",
    },
    "gentle": {
        "description": "Minimal — slow roll only, no airbags",
        "breathing_profile": "idle",
        "airbag_zones":    [],
        "airbag_on_s":     0,
        "airbag_off_s":    0,
        "butt_on_s":       0,
        "butt_off_s":      0,
        "roller_choreography": _gentle_roll(14.0),
        "initial_recline": 15,
        "base_led_color":  "warm amber",
    },
    "off": {
        "description": "Everything off",
        "breathing_profile": "idle",
        "airbag_zones":    [],
        "airbag_on_s":     0,
        "airbag_off_s":    0,
        "butt_on_s":       0,
        "butt_off_s":      0,
        "roller_choreography": [],
        "initial_recline": 0,
        "base_led_color":  "warm amber",
    },
    # Internal: used for idle/partial-presence states — gentle outside airbag only.
    "_idle_breathing": {
        "description": "Idle ambient breathing (internal)",
        "breathing_profile": "idle",
        "airbag_zones":    [],    # only outside airbag follows the pump
        "airbag_on_s":     6.0,
        "airbag_off_s":    8.5,
        "butt_on_s":       0,
        "butt_off_s":      0,
        "roller_choreography": [],
        "initial_recline": 0,
        "base_led_color":  "warm amber",
    },
}

DEFAULT_PROGRAM = "neck_shoulders"


def public_programs():
    """Programs available to users (excludes internal _ prefixed ones)."""
    return {k: v for k, v in PROGRAMS.items() if not k.startswith("_")}


def effective_breath(prog, phase="idle", overrides=None):
    """Return (on_s, off_s) for the current program state, with variability.

    phase: session phase name, used to scale breathing speed.
    overrides: dict with optional 'airbag_on_s' / 'airbag_off_s' from sliders.
    """
    profile_name = prog.get("breathing_profile", "active")
    profile = BREATHING_PROFILES.get(profile_name, BREATHING_PROFILES["active"])
    cycle_s = profile["cycle_s"]
    mult    = PHASE_BREATH_MULT.get(phase, 1.0)
    cycle_s = cycle_s / mult        # higher mult → shorter cycle → faster breath

    inhale  = profile["inhale_frac"]
    default_on  = prog.get("airbag_on_s",  cycle_s * inhale)
    default_off = prog.get("airbag_off_s", cycle_s * (1 - inhale))

    on_s  = float((overrides or {}).get("airbag_on_s",  default_on))
    off_s = float((overrides or {}).get("airbag_off_s", default_off))
    return on_s, off_s


def effective_butt(prog, overrides=None):
    """Return (on_s, off_s) for butt vibration duty cycle."""
    on_s  = float((overrides or {}).get("butt_on_s",  prog.get("butt_on_s",  0)))
    off_s = float((overrides or {}).get("butt_off_s", prog.get("butt_off_s", 0)))
    return on_s, off_s


def program_params(prog):
    """Return the timing params dict the dashboard displays."""
    return {
        "airbag_on_s":     prog.get("airbag_on_s",  0),
        "airbag_off_s":    prog.get("airbag_off_s", 0),
        "butt_on_s":       prog.get("butt_on_s",    0),
        "butt_off_s":      prog.get("butt_off_s",   0),
        "initial_recline": prog.get("initial_recline", 0),
        "breathing_profile": prog.get("breathing_profile", "active"),
    }
