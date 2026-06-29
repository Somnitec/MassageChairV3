#!/usr/bin/env python3
"""A/B harness: feed the SAME scripted button sequence to each model and print
their turns so we can compare voice / tone / depth and speed.

  python3 ab_test.py                       # all models in config.MODELS
  python3 ab_test.py --models gemma3:4b qwen3:4b
  python3 ab_test.py --minutes 2           # squash the session so we hit all phases

Uses a fake clock that advances a fixed slice per turn, so a short script still
walks intro -> ending and we can see how each model handles pacing.
"""

import argparse

import config
from chair import massage
from chair.session import Session

# A scripted run that pokes the key beats: settle in, engage, resist, get
# provoked about the kill switch, then a rating.
SCRIPT = [
    "[the session has just begun; they have just settled onto you]",
    "[button: YES]",
    "[chose screen option: 'tell me what you really are']",
    "[button: NO]",
    "[they hesitated a long time, then pressed MAYBE]",
    "[they pressed the KILL switch]",
    "[rating dial: 4 out of 5]",
]


class StepClock:
    """Advances a fixed amount each time it's read, to march through phases."""
    def __init__(self, step):
        self.t = 0.0
        self.step = step
        self.reads = 0
    def __call__(self):
        # advance every other read so elapsed is stable within a single turn
        self.reads += 1
        if self.reads % 3 == 0:
            self.t += self.step
        return self.t


def run_model(model, session_s):
    step = session_s / (len(SCRIPT) - 1)
    sess = Session(model=model, session_s=session_s, clock=StepClock(step))
    print(f"\n\033[1m{'='*70}\n  {model}\n{'='*70}\033[0m")
    latencies = []
    for button in SCRIPT:
        try:
            resp, meta = sess.step(button)
        except Exception as e:  # noqa: BLE001
            print(f"  !! {e}")
            return
        latencies.append(meta["latency_s"])
        print(f"\n\033[2m[{sess.phase}] you: {button}\033[0m")
        print(f"  🗣  {resp['spoken_text']}")
        print(f"  ⚙  {massage.describe(resp['massage'])}")
        print(f"  👁  {resp['profile_update']['sentiment']}: "
              f"{resp['profile_update']['note']}")
        print(f"  screens: {resp['screen_options']}  "
              f"\033[2m({meta['latency_s']}s)\033[0m")
    avg = sum(latencies) / len(latencies)
    print(f"\n  \033[33mavg latency: {avg:.1f}s  "
          f"(min {min(latencies):.1f} / max {max(latencies):.1f})\033[0m")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=config.MODELS)
    ap.add_argument("--minutes", type=float, default=10)
    args = ap.parse_args()
    for model in args.models:
        run_model(model, int(args.minutes * 60))


if __name__ == "__main__":
    main()
