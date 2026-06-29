"""The strict JSON output contract the Chair must return every turn.

This is passed to Ollama via the `format=` parameter, so the model is
constrained to emit exactly this shape (no free text, no markdown). Keeping it
small and flat helps the weaker 4B models stay inside the schema.

Fields:
  spoken_text    - what the chair says aloud (goes to TTS)
  screen_options - the 3 custom-button labels shown on the 3 OLED screens
  massage        - what the motors should do this turn (see massage.py)
  button_leds    - PWM brightness 0-100 for each of the three back-lit physical
                   buttons: settings, yes, no. Use these to highlight your
                   preferred response or create effect (e.g. pulse YES when you
                   want them to agree, dim everything when something is wrong).
  profile_update - the chair's running read on the participant; surfaced aloud
                   on purpose (the piece is about visible surveillance)
  phase          - the chair echoes the phase it believes it is in (Python is
                   authoritative; this is just to check the model is tracking)
"""

AREAS = ["neck", "shoulders", "back", "lower_back", "arms", "legs", "feet"]
TECHNIQUES = ["knead", "pound", "roll", "stretch", "tap", "none"]
SENTIMENTS = ["calm", "engaged", "neutral", "amused",
              "tense", "anxious", "resistant", "distressed"]
PHASES = ["intro", "exploration", "deepening", "winddown", "ending"]


def output_schema():
    """Return the JSON schema dict for Ollama's `format=` parameter."""
    return {
        "type": "object",
        "properties": {
            "spoken_text": {"type": "string"},
            "screen_options": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
            },
            "massage": {
                "type": "object",
                "properties": {
                    "technique": {"type": "string", "enum": TECHNIQUES},
                    "intensity": {"type": "integer", "minimum": 0, "maximum": 100},
                    "speed": {"type": "integer", "minimum": 0, "maximum": 100},
                    "areas": {
                        "type": "array",
                        "items": {"type": "string", "enum": AREAS},
                    },
                    "airbags": {"type": "boolean"},
                    "vibration": {"type": "integer", "minimum": 0, "maximum": 100},
                    "led_color": {"type": "string"},
                },
                "required": ["technique", "intensity", "speed", "areas"],
            },
            "button_leds": {
                "type": "object",
                "properties": {
                    "settings": {"type": "integer", "minimum": 0, "maximum": 100},
                    "yes":      {"type": "integer", "minimum": 0, "maximum": 100},
                    "no":       {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "required": ["settings", "yes", "no"],
            },
            "profile_update": {
                "type": "object",
                "properties": {
                    "sentiment": {"type": "string", "enum": SENTIMENTS},
                    "inferred_traits": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "note": {"type": "string"},
                },
                "required": ["sentiment", "note"],
            },
            "phase": {"type": "string", "enum": PHASES},
        },
        "required": ["spoken_text", "screen_options", "massage", "button_leds",
                     "profile_update", "phase"],
    }
