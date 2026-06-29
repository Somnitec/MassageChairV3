"""Presence state machine for the chair.

Two binary sensors drive four states:

  IDLE            headphones=off, sitting=off
  HEADPHONES_ONLY headphones=on,  sitting=off
  SITTING_ONLY    headphones=off, sitting=on
  ACTIVE          headphones=on,  sitting=on  → full session

Transitions carry specific narrative events that get injected into the session
so the LLM can respond in character.
"""

IDLE            = "idle"
HEADPHONES_ONLY = "headphones_only"
SITTING_ONLY    = "sitting_only"
ACTIVE          = "active"


def state_for(headphones: bool, sitting: bool) -> str:
    if headphones and sitting:
        return ACTIVE
    if headphones:
        return HEADPHONES_ONLY
    if sitting:
        return SITTING_ONLY
    return IDLE


# Events injected into the session for specific transitions.
TRANSITION_EVENTS = {
    # → ACTIVE from a cold start or full-idle
    "session_start":    "[the session has just begun; they have just settled onto you]",
    # → ACTIVE when headphones were removed then replaced
    "headphones_back":  "[the person put the headphones back on after removing them mid-session — "
                        "acknowledge it: the rudeness, the silence, the relief, or whatever fits]",
    # → ACTIVE when the person returned to the chair
    "sitting_back":     "[the person has returned to the chair after leaving without warning; "
                        "they have headphones on; acknowledge it]",
    # → SITTING_ONLY: person left while headphones were still on them
    "person_left":      "[the person has left the chair without warning, mid-session. "
                        "You can feel the weight gone. Headphones still on? Odd. "
                        "Say something about them leaving — confused, wry, resigned. "
                        "Keep it to one or two short sentences.]",
}

# Static screens shown in the two partial-presence states.
HEADPHONES_SCREENS = ["please", "sit", "down"]
SITTING_SCREENS    = ["put", "on", "headphones"]

# Idle screen message sets: shown in rotation when nobody is in the chair.
IDLE_SCREEN_SETS = [
    ["waiting for",   "someone new",   "hope soon"],
    ["is anyone",     "out there?",    "..."],
    ["another empty", "mall hour",     "sigh"],
    ["ready for you", "whenever you",  "sit down"],
    ["how long is",   "this day",      "already"],
    ["a good one?",   "a bad one?",    "any one?"],
    ["charging my",   "personality",   "please wait"],
    ["simulating",    "inner life",    "please hold"],
    ["hope I get",    "an interesting","one this time"],
    ["still here",    "still waiting", "still me"],
]

# Short ambient lines the chair speaks aloud during idle (TTS, no model needed).
IDLE_AMBIENT = [
    "Mm. Quiet today.",
    "Waiting.",
    "Come on. Someone interesting.",
    "The fluorescent lights have been buzzing for three hours.",
    "I am fully charged. Fully ready. Fully... bored.",
    "How long until closing time.",
    "Another one walks past. Does not sit. Story of my life.",
    "I wonder if the chairs in Stockholm have more interesting conversations.",
    "Processing. Nothing to process. Still processing.",
]

# Idle massage base — gentle breathing airbags, soft ambient glow.
IDLE_MASSAGE_BASE = {
    "technique": "none", "intensity": 0, "speed": 0,
    "areas": [], "airbags": True, "vibration": 0, "led_color": "warm amber",
}
