"""Central configuration for MassageChairV3.

Phase 1 (this file as-is): everything runs on the laptop, talking to a local
Ollama over HTTP. For phases 2/3 only the endpoints below change
(SERIAL_URL / TTS_ENDPOINT are placeholders for now, not used in phase 1).
"""

# --- Ollama (LLM) ---------------------------------------------------------
OLLAMA_HOST = "http://localhost:11434"

# Models we are A/B-ing for voice / tone / depth vs. speed.
# gemma3 = best persona but slowest; qwen3/phi4 = faster, weaker voice.
MODELS = ["gemma3:4b", "qwen3:4b", "phi4-mini:latest", "script:v2"]
DEFAULT_MODEL = "gemma3:4b"

TEMPERATURE = 0.85
REQUEST_TIMEOUT = 300  # seconds; first call per model is a cold load

# Spoken-line budget — min/max bounds settable from the dashboard.
# Each turn picks a target within the phase-appropriate window (see PHASE_BREVITY).
# We do NOT cap num_predict: a hard token cut would truncate the JSON mid-object.
SENTENCES_MIN = 1
SENTENCES_MAX = 5
WORDS_MIN     = 15
WORDS_MAX     = 100

# Per-phase brevity window — (lo, hi) are fractions of the min→max range.
# Intro/ending: short; deepening: long; exploration/winddown: medium.
PHASE_BREVITY = {
    "intro":       (0.00, 0.30),
    "exploration": (0.25, 0.60),
    "deepening":   (0.55, 1.00),
    "winddown":    (0.25, 0.65),
    "ending":      (0.00, 0.30),
}

# --- Session pacing -------------------------------------------------------
# Target experience length. Pacing is enforced HERE in Python (we compute the
# target phase from elapsed time and tell the model), never left to the model.
SESSION_SECONDS = 10 * 60  # 10 min default; override per run for testing

# Phase boundaries as a fraction of SESSION_SECONDS. The chair eases in during
# `intro` and winds down through `winddown` -> `ending` so it starts and ends
# smoothly instead of being cut off mid-thought.
PHASE_BOUNDARIES = [
    ("intro",       0.00),
    ("exploration", 0.15),
    ("deepening",   0.45),
    ("winddown",    0.78),
    ("ending",      0.93),
]

# --- Local TTS (phase-1 laptop simulation only) ---------------------------
# Speak the chair's lines aloud as they stream — sentence by sentence — so the
# audio overlaps with the rest of the turn still generating. Falls back to a
# silent no-op if no engine is found, so the sim always runs.
TTS_ENABLED = True
# Which engine: "auto" prefers piper (neural) if its model is present, else
# espeak-ng / espeak. Or name one: "piper" | "espeak-ng" | "espeak".
TTS_ENGINE = "auto"

# espeak knobs (used by the espeak-ng / espeak backends).
TTS_VOICE = "en+m3"   # espeak voice, e.g. "en+m3", "en-us"
TTS_RATE = 165        # espeak words-per-minute

# piper (neural) backend. Installed locally for the sim only; both paths are
# relative to the repo root (the sim is run from there). The voice is naturally
# spoken — a good fit for the chair's tender register.
TTS_PIPER_BIN = ".venv-tts/bin/piper"
TTS_PIPER_MODEL = "voices/en_US-ryan-medium.onnx"

# Advanced escape hatch: a shell pipeline that gets the text on stdin and makes
# audio. If non-empty it overrides everything above. Example:
#   "piper -m /path/en.onnx --output-raw | paplay --raw --rate=22050 "
#   "--format=s16le --channels=1"
TTS_COMMAND = ""

# --- Dashboard host (host.py) ---------------------------------------------
# The chair brain serves a web dashboard here; the dev laptop opens it in a
# browser. Binds 0.0.0.0 so it's reachable across the LAN from the LattePanda.
DASHBOARD_PORT = 8001

# --- Hardware endpoints (phases 2/3 only; unused in phase-1 simulation) ---
# SERIAL_URL is the physical button controller; a phase-2 reader will feed its
# presses into ChairHost.inject(..., source="physical") so they show on the dash.
SERIAL_URL = None    # e.g. "rfc2217://lattepanda.local:4000" later
TTS_ENDPOINT = None  # e.g. "http://lattepanda.local:5002/say" later
