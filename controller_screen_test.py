#!/usr/bin/env python3
"""Hardware test for the Controller MCU's 3 status OLEDs (screens A/B/C).

Talks to the Controller MCU over serial (locally or via a TCP serial
bridge) and lets you push text/animations to the screens by hand, or run a
canned sequence that exercises every transition effect + the overflow
truncation fallback + forced marquee + the pulse indicator. stdlib-only.

Examples
--------
  # see which /dev/tty* is which MCU
  python3 controller_screen_test.py --list

  # interactive control of the controller MCU on this machine
  python3 controller_screen_test.py /dev/ttyACM0

  # control it from another machine via a socat bridge on the LattePanda
  python3 controller_screen_test.py tcp:lattepanda.local:7000

  # run the canned validation sequence (every effect, on every screen)
  python3 controller_screen_test.py /dev/ttyACM0 --seq

Everything arriving from the MCU (button presses/releases, screen acks,
boot logs) prints in the background as it happens, from a reader thread --
not just right after you send a command -- so a physical button press
shows up live even while you're sitting at the prompt.

Interactive commands (type `help`):
  a|b|c <text>              draw text on screen A/B/C, default "wipe" effect
  a|b|c <text> / <effect>   effect: instant|wipe|flash|typewriter|marquee
  pulse a|b|c on|off        toggle the "breathing" brightness indicator
  clear                     blank all three screens
  raw {"key":[1]}           send a literal JSON command
  quit
"""

import argparse
import sys
import threading
import time

from chair.hardware import ChairLink, identify, list_serial_ports

BOOT_WAIT = 2.0  # Arduino resets when the port is opened


def show(blobs):
    for b in blobs:
        if "_log" in b:
            print("  #", b["_log"])
        elif "_raw" in b:
            print("  <raw>", b["_raw"].strip())
        else:
            print("  <-", b)


class Reader:
    """Continuously drains `link` in the background and prints whatever
    arrives, so button presses/releases / logs show up live instead of
    only right after a command is sent. Only this thread ever reads from
    `link`; the main thread only ever writes (link.send) -- that split
    keeps ChairLink's non-thread-safe internal buffer single-owner."""

    def __init__(self, link):
        self.link = link
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def _loop(self):
        while not self._stop.is_set():
            show(self.link.drain(0.2))

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1.0)


def send_screen(link, screen, text, effect=None):
    key = "customScreen" + screen.upper()
    values = (text,) if effect is None else (text, effect)
    payload = link.send(key, *values)
    print(">>", payload)


def send_pulse(link, screen, on):
    key = "screenPulse" + screen.upper()
    payload = link.send(key, bool(on))
    print(">>", payload)


def clear_all(link):
    payload = link.send("clearScreen", True)
    print(">>", payload)


EFFECTS = ("instant", "wipe", "flash", "typewriter", "marquee")

SEQUENCE = [
    ("Every effect on screen A, in turn (watch the OLED, not just this log)", None),
]


def run_sequence(link):
    print("\n>> instant/wipe/flash/typewriter on screen A")
    for fx in ("instant", "wipe", "flash", "typewriter"):
        send_screen(link, "a", fx.upper(), fx)
        time.sleep(1.2)

    print("\n>> word-wrap: a longer phrase that needs multiple lines, screen B")
    send_screen(link, "b", "the chair judges your posture", "wipe")
    time.sleep(1.5)

    print("\n>> overflow truncation fallback: one long unbroken word, screen C")
    send_screen(link, "c", "supercalifragilisticexpialidocious", "wipe")
    time.sleep(2.0)

    print("\n>> forced marquee even though it would fit statically, screen A")
    send_screen(link, "a", "look at me go", "marquee")
    time.sleep(3.0)

    print("\n>> pulse (breathing) indicator on screen B for 3s")
    send_pulse(link, "b", True)
    time.sleep(3.0)
    send_pulse(link, "b", False)

    print("\n>> clear all")
    clear_all(link)
    print("\nSequence done. Confirm visually: 4 effects then a forced scroll on A,")
    print("wrapped text on B (then pulsed), a truncated '...' word on C.")


def run_command(link, line):
    parts = line.strip().split(None, 1)
    if not parts:
        return True
    cmd = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if cmd in ("quit", "exit", "q"):
        return False
    elif cmd == "help":
        print(__doc__)
    elif cmd == "clear":
        clear_all(link)
    elif cmd == "raw":
        payload = link.send_raw(rest)
        print(">>", payload)
    elif cmd == "pulse":
        sub = rest.split()
        if len(sub) != 2 or sub[0] not in ("a", "b", "c") or sub[1] not in ("on", "off"):
            print("  ? usage: pulse a|b|c on|off")
        else:
            send_pulse(link, sub[0], sub[1] == "on")
    elif cmd in ("a", "b", "c"):
        if "/" in rest:
            text, _, fx = rest.partition("/")
            text, fx = text.strip(), fx.strip().lower()
            if fx not in EFFECTS:
                print("  ? unknown effect %r, try one of %s" % (fx, ", ".join(EFFECTS)))
                return True
        else:
            text, fx = rest, None
        send_screen(link, cmd, text, fx)
    else:
        print("  ? unknown command (try `help`)")
    return True


DEFAULT_PORT = "/dev/cu.usbmodem30057301"  # this dev machine's Controller MCU, for now


def main():
    ap = argparse.ArgumentParser(description="Massage chair controller screen test")
    ap.add_argument("port", nargs="?", default=DEFAULT_PORT,
                     help="/dev/ttyACM0  or  tcp:host:port (default: %(default)s)")
    ap.add_argument("--list", action="store_true", help="scan & identify serial ports")
    ap.add_argument("--seq", action="store_true", help="run the canned validation sequence")
    args = ap.parse_args()

    if args.list:
        ports = list_serial_ports()
        if not ports:
            print("No /dev/ttyACM* or /dev/ttyUSB* found.")
            return
        for p in ports:
            print("Probing %s ..." % p)
            try:
                role, _ = identify(p)
            except Exception as e:
                role = "error: %s" % e
            print("  -> %s\n" % role)
        return

    if not args.port:
        ap.error("give a port (or --list). e.g. /dev/ttyACM0 or tcp:host:7000")

    print("Connecting to %s ..." % args.port)
    link = ChairLink(args.port, boot_wait=BOOT_WAIT if not args.port.startswith("tcp:") else 0.0)
    link.open()
    reader = Reader(link).start()
    print("Connected. Watching in the background -- boot output and button")
    print("presses/releases print here as they happen.\n")
    time.sleep(2.5)  # let the boot burst print before anything else interleaves

    try:
        if args.seq:
            run_sequence(link)
        else:
            print("\nType `help` for commands, `quit` to exit.\n")
            while True:
                try:
                    line = input("screens> ")
                except (EOFError, KeyboardInterrupt):
                    break
                if not run_command(link, line):
                    break
    finally:
        reader.close()
        link.close()
        print("\nClosed.")


if __name__ == "__main__":
    main()
