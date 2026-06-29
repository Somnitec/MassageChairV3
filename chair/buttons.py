"""The participant's button vocabulary — the one place that turns a press into
the text the model sees.

The human can't speak; they only press buttons. Every front-end (the terminal
sim, the web dashboard, and later the physical controller) funnels presses
through here so the phrasing the persona reads is identical everywhere. The
persona prompt in persona.py is written against exactly these strings.
"""

# Canonical button kinds a front-end can send.
YES = "YES"
NO = "NO"
MAYBE = "MAYBE"
KILL = "KILL"
REPEAT = "REPEAT"
OPTION = "OPTION"       # value = 1-based index into the 3 screen options
RATING = "RATING"       # value = 1-5 dial
THUMB_UP = "THUMB_UP"
THUMB_DOWN = "THUMB_DOWN"
HORN = "HORN"
SETTINGS = "SETTINGS"
LANGUAGE = "LANGUAGE"   # value = "up" or "down" (physical switch direction)
VOLUME = "VOLUME"       # value = 1-5 (physical slider positions)

# The fixed (non-dynamic) buttons, in display order, for front-ends to render.
FIXED = [YES, NO, MAYBE, REPEAT, KILL, THUMB_UP, THUMB_DOWN, HORN, SETTINGS]


def event_for(kind, value=None, options=None):
    """Map a (kind, value) press to the event string the model is given.

    `options` is the current list of 3 screen-option labels, needed to quote the
    chosen one for an OPTION press. Returns None for an unknown/garbled press.
    """
    kind = (kind or "").upper()
    if kind == YES:
        return "[button: YES]"
    if kind == NO:
        return "[button: NO]"
    if kind == MAYBE:
        return "[button: MAYBE]"
    if kind == KILL:
        return "[they pressed the KILL switch]"
    if kind == REPEAT:
        return "[button: REPEAT]"
    if kind == THUMB_UP:
        return "[button: THUMB UP]"
    if kind == THUMB_DOWN:
        return "[button: THUMB DOWN]"
    if kind == HORN:
        return "[button: HORN]"
    if kind == SETTINGS:
        return "[button: SETTINGS]"
    if kind == LANGUAGE:
        direction = str(value or "").lower()
        if direction in ("up", "down"):
            return f"[language switch: {direction}]"
        return "[language switch]"
    if kind == VOLUME:
        idx = _as_int(value)
        if idx is not None and 1 <= idx <= 5:
            return f"[volume: {idx}/5]"
        return None
    if kind == OPTION:
        idx = _as_int(value)
        opts = options or []
        if idx is not None and 1 <= idx <= len(opts):
            return f"[chose screen option: {opts[idx - 1]!r}]"
        return None
    if kind == RATING:
        idx = _as_int(value)
        if idx is not None and 1 <= idx <= 5:
            return f"[rating dial: {idx} out of 5]"
        return None
    return None


def parse_typed(cmd, options):
    """Map a typed terminal command (y/n/m, 1/2/3, r1-r5, k, rep) to an event.

    Thin convenience wrapper over event_for for the keyboard front-end.
    """
    low = (cmd or "").strip().lower()
    if low in ("y", "yes"):
        return event_for(YES)
    if low in ("n", "no"):
        return event_for(NO)
    if low in ("m", "maybe"):
        return event_for(MAYBE)
    if low in ("k", "kill"):
        return event_for(KILL)
    if low in ("rep", "repeat"):
        return event_for(REPEAT)
    if low in ("tu", "thumb_up", "thumbup"):
        return event_for(THUMB_UP)
    if low in ("td", "thumb_down", "thumbdown"):
        return event_for(THUMB_DOWN)
    if low == "horn":
        return event_for(HORN)
    if low in ("set", "settings"):
        return event_for(SETTINGS)
    if low.startswith("lang "):
        return event_for(LANGUAGE, low[5:].strip())
    if low.startswith("vol ") and low[4:].strip().isdigit():
        return event_for(VOLUME, low[4:].strip())
    if low in ("1", "2", "3"):
        return event_for(OPTION, low, options)
    if low.startswith("r") and low[1:].isdigit():
        return event_for(RATING, low[1:])
    return None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
