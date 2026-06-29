"""
chair_test_harness.py

Hand-fire test harness for the massage chair AI.
Run this BEFORE wiring anything to real motors or TTS — it just talks to the
model and prints what it would say/do, so you can listen for tone and check
the kill-button response.

Usage:
    python chair_test_harness.py

At the prompt, type one of: yes, no, maybe, kill, other, quit
"""

import json
import time
import uuid
from pathlib import Path
from typing import Literal

import ollama
from pydantic import BaseModel, Field, ValidationError

# ---- Config -----------------------------------------------------------------

MODEL = "gemma3:4b"  # swap to "phi4-mini" or "qwen3:4b" to A/B the voice
SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

BUTTONS = ["yes", "no", "maybe", "kill", "other"]
HARD_CUTOFF_SECONDS = 900  # 15 min — enforced here, not left to the model


# ---- Schema -------------------------------------------------------------------

class Massage(BaseModel):
    intensity: float
    kneading_speed: float
    roller_pattern: Literal["still", "wave", "pulse", "knead", "circle"]
    zone: Literal["full", "upper", "lower", "neck"]


class ProfileUpdate(BaseModel):
    agency_score: float
    machine_trust: float
    note: str


class ChairTurn(BaseModel):
    spoken_text: str
    screen_options: list[str] = Field(min_length=3, max_length=3)
    massage: Massage
    profile_update: ProfileUpdate
    phase: Literal["opening", "middle", "closing"]


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ---- Harness ------------------------------------------------------------------

def call_model(system_prompt: str, user_context: str, temperature: float) -> ChairTurn:
    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_context},
        ],
        format=ChairTurn.model_json_schema(),
        options={"temperature": temperature},
    )
    raw = response["message"]["content"]
    return ChairTurn.model_validate_json(raw)


def main():
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    session_id = uuid.uuid4().hex[:8]
    log_path = LOG_DIR / f"session_{session_id}.jsonl"

    profile_state = {"agency_score": 0.0, "machine_trust": 0.5, "note": "session start"}
    turn_count = 0
    session_start = time.monotonic()
    last_press = session_start

    print(f"\nSession {session_id} -- model: {MODEL}")
    print("Buttons:", ", ".join(BUTTONS), "(or 'quit')\n")

    while True:
        choice = input("Button pressed > ").strip().lower()
        if choice == "quit":
            break
        if choice not in BUTTONS:
            print(f"  (not a recognized button: {BUTTONS})")
            continue

        now = time.monotonic()
        elapsed_seconds = round(now - session_start, 1)
        ipi_ms = round((now - last_press) * 1000)
        last_press = now
        turn_count += 1

        user_context = (
            f"button_pressed: {choice}\n"
            f"elapsed_seconds: {elapsed_seconds}\n"
            f"turn_count: {turn_count}\n"
            f"inter_press_interval_ms: {ipi_ms}\n"
            f"profile_state: {json.dumps(profile_state)}\n"
        )

        try:
            turn = call_model(system_prompt, user_context, temperature=0.7)
        except ValidationError:
            print("  !! invalid JSON from model, retrying at temperature 0")
            turn = call_model(system_prompt, user_context, temperature=0.0)

        # clamp before anything downstream would ever see it
        turn.massage.intensity = clamp(turn.massage.intensity)
        turn.massage.kneading_speed = clamp(turn.massage.kneading_speed)

        profile_state = turn.profile_update.model_dump()

        print(f"\n  [{turn.phase}] {turn.spoken_text}")
        print(f"  screens: {turn.screen_options}")
        print(f"  massage: {turn.massage.model_dump()}")
        print(f"  profile: {profile_state}\n")

        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.time(),
                "turn": turn_count,
                "button_pressed": choice,
                "ipi_ms": ipi_ms,
                "elapsed_s": elapsed_seconds,
                "model_output": turn.model_dump(),
            }) + "\n")

        if elapsed_seconds > HARD_CUTOFF_SECONDS:
            print("  -- 15 min hard cutoff reached, end the session here --")
            break

    print(f"\nLog saved to {log_path}")


if __name__ == "__main__":
    main()
