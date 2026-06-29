"""Massage parameter helpers.

Translates normalized massage dicts into ChairSystem MCU commands. The mapping
isolates hardware specifics from the LLM engine.
"""

from chair.schema import AREAS, TECHNIQUES

# Color name -> (R, G, B) for the LED strip
LED_COLORS = {
    "off": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "yellow": (255, 255, 0),
    "warm amber": (255, 200, 0),
    "cool blue": (0, 180, 255),
    "purple": (200, 0, 255),
}

DEFAULT = {
    "technique": "knead",
    "intensity": 30,
    "speed": 30,
    "areas": ["shoulders", "back"],
    "airbags": False,
    "vibration": 0,
    "led_color": "warm amber",
}


def normalize(massage):
    """Clamp/repair a massage block from the model so it's always renderable."""
    m = dict(DEFAULT)
    m.update(massage or {})
    if m.get("technique") not in TECHNIQUES:
        m["technique"] = "knead"
    for k in ("intensity", "speed", "vibration"):
        try:
            m[k] = max(0, min(100, int(m.get(k, 0))))
        except (TypeError, ValueError):
            m[k] = 0
    m["areas"] = [a for a in (m.get("areas") or []) if a in AREAS] or ["back"]
    m["airbags"] = bool(m.get("airbags", False))
    m["led_color"] = str(m.get("led_color") or "warm amber")
    return m


def describe(m):
    """One-line human-readable summary for the dashboard."""
    areas = ", ".join(m["areas"])
    bits = [f"{m['technique']} @ {m['intensity']}%", f"areas: {areas}",
            f"speed {m['speed']}%"]
    if m["vibration"]:
        bits.append(f"vibe {m['vibration']}%")
    if m["airbags"]:
        bits.append("airbags ON")
    bits.append(f"LED {m['led_color']}")
    return " | ".join(bits)


def to_hardware(m):
    """Translate a normalized massage dict to ChairSystem MCU commands.

    Returns a list of (key, *values) tuples ready for ChairLink.send().
    """
    m = normalize(m)
    commands = []

    # Motor technique: choose kneading or pounding
    speed_pwm = int(m["speed"] * 255 / 100)
    if m["technique"] == "knead":
        commands.append(("roller_kneading_on", 1))
        commands.append(("roller_kneading_speed", speed_pwm))
        commands.append(("roller_pounding_on", 0))
    elif m["technique"] == "pound":
        commands.append(("roller_pounding_on", 1))
        commands.append(("roller_pounding_speed", speed_pwm))
        commands.append(("roller_kneading_on", 0))
    else:
        # roll, stretch, tap, none -> turn off both
        commands.append(("roller_kneading_on", 0))
        commands.append(("roller_pounding_on", 0))

    # Feet motor: enabled only if "feet" in areas
    feet_on = 1 if "feet" in m["areas"] else 0
    commands.append(("feet_roller_on", feet_on))
    if feet_on:
        commands.append(("feet_roller_speed", speed_pwm))

    # Vibration
    commands.append(("butt_vibration_on", 1 if m["vibration"] else 0))

    # Airbags: map areas to valves. shoulders+arms+legs+outside are the four zones.
    if m["airbags"]:
        commands.append(("airpump_on", 1))
        # shoulders and neck -> airbag_shoulders
        shoulder_on = 1 if "shoulders" in m["areas"] or "neck" in m["areas"] else 0
        commands.append(("airbag_shoulders_on", shoulder_on))
        # arms -> airbag_arms
        commands.append(("airbag_arms_on", 1 if "arms" in m["areas"] else 0))
        # legs and lower_back -> airbag_legs
        legs_on = 1 if "legs" in m["areas"] or "lower_back" in m["areas"] else 0
        commands.append(("airbag_legs_on", legs_on))
        # outside (generic perimeter) is always on with airbags
        commands.append(("airbag_outside_on", 1))
    else:
        commands.append(("airpump_on", 0))
        commands.append(("airbag_shoulders_on", 0))
        commands.append(("airbag_arms_on", 0))
        commands.append(("airbag_legs_on", 0))
        commands.append(("airbag_outside_on", 0))

    # LED backlight
    rgb = LED_COLORS.get(m["led_color"].lower(), LED_COLORS["warm amber"])
    commands.append(("backlight_color", *rgb))
    commands.append(("backlight_on", 1))

    return commands
