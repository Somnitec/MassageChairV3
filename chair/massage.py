"""Massage parameter helpers.

Phase 1 only displays/validates these. Phases 2/3 will translate them into the
actual serial commands documented in the V2 repo (feet speed, airbag groups,
back pounding/kneading position, vibration, LED program). Keeping the mapping
isolated here means the rest of the engine never touches hardware specifics.
"""

from chair.schema import AREAS, TECHNIQUES

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
