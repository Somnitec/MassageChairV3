#!/usr/bin/env python3
"""Phase-1 terminal dashboard: simulate the chair with no hardware.

Shows what the chair would say (TTS), what's on the 3 OLED screens, what the
motors would do, and the chair's running profile of you. You drive it with the
button panel from your keyboard.

  python3 simulate.py                 # default model, 10-min session
  python3 simulate.py --model qwen3:4b --minutes 3
  python3 simulate.py --model 3 --minutes 3   # 3 = preset slot in config.MODELS

Buttons:
  y / n / m           yes / no / maybe
  1 2 3               press custom screen button 1/2/3
  r1 .. r5            1-5 rating dial
  tu / td             thumb up / thumb down
  horn                press the horn
  set / settings      settings button
  lang up / lang down language switch
  vol 1 .. vol 5      volume slider
  k                   KILL switch (soft - the chair gets a say)
  rep                 repeat
  ff <secs>           fast-forward the session clock (test phase changes)
  model <name>        hot-swap the model mid-session
  model 1|2|3         hot-swap to preset model 1/2/3 (config.MODELS)
  q             quit
"""

import argparse
import time

import config
from chair import buttons, massage
from chair.session import Session
from chair.tts import Speaker

# --- tiny ANSI helpers ----------------------------------------------------
DIM = "\033[2m"; B = "\033[1m"; R = "\033[0m"
CYAN = "\033[36m"; YEL = "\033[33m"; MAG = "\033[35m"; GRN = "\033[32m"
RED = "\033[31m"


class ControllableClock:
    """monotonic clock plus a manual offset, so we can fast-forward in testing."""
    def __init__(self):
        self._t0 = time.monotonic()
        self.offset = 0.0
    def __call__(self):
        return time.monotonic() - self._t0 + self.offset


def render_header(sess):
    """Top banner + the '🗣' prefix, printed before the spoken line streams in."""
    print()
    print(f"{DIM}┌─ THE CHAIR ── {sess.model} ── phase: {B}{sess.phase}{R}{DIM}"
          f" ── t={int(sess.elapsed)}s / {sess.session_s}s ─┐{R}")
    print(f"{CYAN}{B}🗣  {R}", end="", flush=True)


def stream_token(delta):
    """Print one streamed chunk of spoken_text, keeping the cyan styling."""
    print(f"{CYAN}{B}{delta}{R}", end="", flush=True)


def render_body(resp, meta, sess):
    """Everything after the spoken line: massage, profile, screens, hints."""
    opts = resp["screen_options"]
    print()  # end the streamed spoken line
    print()
    print(f"{MAG}⚙  massage:{R} {massage.describe(resp['massage'])}")
    pu = resp["profile_update"]
    traits = ", ".join(sess.profile.get("inferred_traits", [])) or "—"
    print(f"{YEL}👁  profile:{R} sentiment={B}{pu['sentiment']}{R} "
          f"| traits: {traits}")
    if pu.get("note"):
        print(f"{YEL}   note:{R} {DIM}{pu['note']}{R}")
    print(f"{DIM}   sentiment trail: {' → '.join(sess.sentiment_log)}{R}")
    print(f"{GRN}┌─ SCREENS ─┐{R} {DIM}({meta['latency_s']}s){R}")
    print(f"   {GRN}[1]{R} {opts[0]}   {GRN}[2]{R} {opts[1]}   {GRN}[3]{R} {opts[2]}")
    print(f"{DIM}   (y/n/m · 1/2/3 · r1-r5 · tu/td · horn · set · lang up/dn · vol N · k · rep · ff N · model X|1-3 · q){R}")


def resolve_model(arg):
    """Map a model arg to a name: '1'..'N' pick config.MODELS, else used as-is."""
    arg = arg.strip()
    if arg.isdigit() and 1 <= int(arg) <= len(config.MODELS):
        return config.MODELS[int(arg) - 1]
    return arg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=config.DEFAULT_MODEL,
                    help="model name, or 1/2/3 for a preset slot in config.MODELS")
    ap.add_argument("--minutes", type=float, default=config.SESSION_SECONDS / 60)
    ap.add_argument("--no-tts", action="store_true",
                    help="disable spoken output even if a TTS engine is present")
    args = ap.parse_args()

    clock = ControllableClock()
    sess = Session(model=resolve_model(args.model),
                   session_s=int(args.minutes * 60), clock=clock)
    speaker = Speaker(enabled=not args.no_tts)

    def on_text(delta):
        stream_token(delta)
        speaker.feed(delta)

    print(f"{B}Massage Chair V3 — phase-1 simulation{R}")
    print(f"{DIM}model={sess.model}  session={args.minutes:g}min  "
          f"(first turn loads the model, be patient){R}")
    presets = "  ".join(f"{i}={m}" for i, m in enumerate(config.MODELS, 1))
    print(f"{DIM}presets:  {presets}{R}")
    tts_status = f"voice: {speaker.engine_name}" if speaker.active else "voice: off"
    print(f"{DIM}{tts_status}{R}")

    button = "[the session has just begun; they have just settled onto you]"
    opts = ["yes", "no", "maybe"]
    while True:
        render_header(sess)
        try:
            resp, meta = sess.step(button, on_text=on_text)
        except Exception as e:  # noqa: BLE001 - surface model/transport errors live
            print(f"\n{RED}!! {e}{R}")
            break
        speaker.flush()  # speak the last sentence (no trailing space to trigger it)
        opts = resp["screen_options"]
        render_body(resp, meta, sess)

        if sess.expired:
            print(f"\n{RED}— session time is up —{R}")
            break

        while True:
            raw = input(f"{B}> {R}").strip()
            low = raw.lower()
            if low == "q":
                return
            if low.startswith("ff "):
                try:
                    clock.offset += float(low[3:]);
                    print(f"{DIM}…fast-forwarded to t={int(sess.elapsed)}s "
                          f"(phase {sess.phase}){R}")
                except ValueError:
                    print(f"{RED}usage: ff <seconds>{R}")
                continue
            if low.startswith("model "):
                sess.model = resolve_model(raw[6:])
                print(f"{DIM}…switched model to {sess.model}{R}")
                continue
            button = buttons.parse_typed(raw, opts)
            if button is None:
                print(f"{DIM}(unknown button; try y/n/m, 1/2/3, r1-r5, k){R}")
                continue
            break


if __name__ == "__main__":
    main()
