"""Translate a massage block into a 'panel state' for the chair graphic.

The dashboard draws the hand-drawn chair (assets/chair/) as a stack of
transparent overlays on chair_background.png — one overlay per function. This
module is the single mapping from the model's massage dict (chair/schema.py)
to which overlays light up, where the roller cursor sits, the LED tint, and the
status light. Pure and side-effect free, so it's easy to unit-test and reuse.

Overlay names here are the sprite basenames (without ".png") in assets/chair/.
"""

# How far down the back track each area sits (0 = neck/top, 1 = feet/bottom).
# Used to place the roller_position_cursor; the topmost active area wins.
#
# TODO [Phase 3 — real chair]: Replace this estimated mapping with real motor
# dead-reckoning. Boot sequence: run roller to bottom_sensor, then up to
# top_sensor, record transit time. Repeat a few times and average to build a
# calibration constant (ms per full travel). Track position by accumulating
# motor-on time (up = subtract, down = add). Persist the running average so
# it tightens over time. The bottom_sensor / top_sensor sprites in
# assets/chair/ are already wired to the UI for visual confirmation.
_AREA_POS = {
    "neck": 0.0,
    "shoulders": 0.18,
    "back": 0.45,
    "lower_back": 0.65,
    "arms": 0.40,
    "legs": 0.85,
    "feet": 1.0,
}

# Sentiments that read as the chair being "happy" with the human (green) vs not.
_RED_SENTIMENTS = {"tense", "anxious", "resistant", "distressed"}

# A loose CSS color for common led_color phrasings the model emits. Anything
# unrecognised falls back to a warm amber; the dashboard tints the backlight.
_LED_CSS = {
    "warm amber": "#ffb347", "amber": "#ffb347", "warm": "#ffb347",
    "red": "#ff4d4d", "crimson": "#d12f2f", "blood": "#a01818",
    "green": "#5dd28c", "blue": "#5b8dff", "deep blue": "#2f4fd1",
    "violet": "#9b5bff", "purple": "#9b5bff", "magenta": "#ff5bd0",
    "pink": "#ff8fc8", "white": "#f0f0f0", "cold": "#cfe6ff",
    "gold": "#ffd24d", "orange": "#ff8a3d", "teal": "#3fd0c8",
}


def _led_css(led_color):
    key = (led_color or "").strip().lower()
    if key in _LED_CSS:
        return _LED_CSS[key]
    # substring match so "soft violet glow" -> violet, "dim red" -> red
    for name, css in _LED_CSS.items():
        if name in key:
            return css
    return "#ffb347"


def panel_state(massage, *, phase=None, sentiment=None):
    """Return the panel state dict the dashboard renders from.

    `massage` must already be normalized (chair.massage.normalize). `phase` and
    `sentiment` are optional context for the recline and status light.
    """
    technique = massage["technique"]
    areas = massage["areas"]
    intensity = massage["intensity"]
    layers = []

    # --- back rollers: technique drives which roller overlay is lit ----------
    if technique in ("pound", "tap"):
        layers.append("roller_pounding_on")
    elif technique == "knead":
        layers.append("roller_kneading_on")
    elif technique == "roll":
        layers.append("roller_up_on")
    # "stretch"/"none" -> no roller, the airbags/areas carry it

    # --- per-area airbags / feet roller --------------------------------------
    if "feet" in areas:
        layers.append("feet_roller_on")
    if "shoulders" in areas or "neck" in areas:
        layers.append("airbag_shoulders_on")
    if "arms" in areas:
        layers.append("airbag_arms_on")
    if "legs" in areas:
        layers.append("airbag_legs_on")

    # --- airbags / pump / vibration / backlight ------------------------------
    if massage["airbags"]:
        layers += ["airpump_on", "airbag_outside_on"]
    if massage["vibration"] > 0:
        layers.append("butt_vibration_on")
    layers.append("backlight_on")  # the chair always has its under-glow

    # --- recline by phase: ease the chair back for the wind-down/ending ------
    if phase in ("winddown", "ending"):
        layers.append("chair_down_on")
        layers.append("chair_status_down")
    else:
        layers.append("chair_status_up")

    # --- roller cursor position: topmost active area -------------------------
    positions = [_AREA_POS[a] for a in areas if a in _AREA_POS]
    roller_pos = min(positions) if positions else 0.45

    status = None
    if sentiment:
        status = "red" if sentiment in _RED_SENTIMENTS else "green"

    return {
        "layers": layers,
        "roller_pos": round(roller_pos, 3),
        "led_color": massage["led_color"],
        "led_css": _led_css(massage["led_color"]),
        "status": status,
        "technique": technique,
        "areas": areas,
        "intensity": intensity,
        "speed": massage["speed"],
        "vibration": massage["vibration"],
        "airbags": massage["airbags"],
    }
