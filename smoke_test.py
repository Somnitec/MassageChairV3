#!/usr/bin/env python3
"""Hardware smoke test for the massage chair motors.

Talks to the ChairSystem MCU over serial (locally or via a TCP serial bridge)
and lets you fire individual actuators by hand. stdlib-only.

Examples
--------
  # see which /dev/tty* is which MCU
  python3 smoke_test.py --list

  # interactive control of the motor MCU on this machine
  python3 smoke_test.py /dev/ttyACM0

  # control it from another machine via a socat bridge on the LattePanda
  python3 smoke_test.py tcp:lattepanda.local:7000

  # run the canned gentle sequence (LED -> vibration -> low kneading -> stop)
  python3 smoke_test.py /dev/ttyACM0 --seq

Interactive commands (type `help`):
  vib on|off            butt vibration
  knead on|off [speed]  kneading roller motor   (speed 0-255)
  pound on|off [speed]  pounding roller motor
  feet on|off [speed]   foot roller motor
  pump on|off           air pump
  shoulders|arms|legs|outside on|off   airbag valves
  led R G B             backlight colour (harmless, good first test)
  status                request a state dump
  raw {"key":[1]}       send a literal JSON command
  stop                  turn everything off (reset)
  quit
"""

import argparse
import sys
import time

from chair.hardware import ChairLink, identify, list_serial_ports

BOOT_WAIT = 2.0  # Arduino resets when the port is opened


def stop_all(link):
    # reset() in firmware kills kneading/pounding/feet + all airbags
    link.send("reset", 1)
    link.drain(0.1)
    for k in ("roller_kneading_on", "roller_pounding_on", "feet_roller_on",
              "butt_vibration_on", "airpump_on", "airbag_shoulders_on",
              "airbag_arms_on", "airbag_legs_on", "airbag_outside_on"):
        link.send(k, 0)
        link.drain(0.05)


def show(blobs):
    for b in blobs:
        if "_raw" in b:
            print("  <raw>", b["_raw"].strip())
            continue
        # compress the giant ack to the interesting motor fields
        interesting = {k: b[k] for k in (
            "last_command", "roller_kneading_on", "roller_kneading_speed",
            "roller_pounding_on", "feet_roller_on", "butt_vibration_on",
            "airpump_on", "roller_sensor_top", "roller_sensor_bottom",
            "controllerCommand", "controllerValue", "error", "no useful message",
        ) if k in b}
        print("  <-", interesting if interesting else b)


SEQUENCE = [
    ("led 0 0 255", "backlight blue (harmless visual check)"),
    ("led 0 0 0", "backlight off"),
    ("vib on", "vibration ON for 1.5s"),
    ("vib off", None),
    ("knead on 120", "kneading at low speed (120/255) for 2s"),
    ("knead off", None),
    ("stop", "all off"),
]


def run_command(link, line):
    parts = line.split()
    if not parts:
        return True
    cmd, args = parts[0].lower(), parts[1:]

    def onoff(a):
        return 1 if a and a[0] in ("on", "1", "true") else 0

    if cmd in ("quit", "exit", "q"):
        return False
    elif cmd == "help":
        print(__doc__)
    elif cmd == "stop":
        stop_all(link)
    elif cmd == "status":
        link.send("status", 1)
    elif cmd == "vib":
        link.send("butt_vibration_on", onoff(args))
    elif cmd in ("knead", "pound", "feet"):
        key = {"knead": "roller_kneading", "pound": "roller_pounding", "feet": "feet_roller"}[cmd]
        if len(args) >= 2:
            link.send(key + "_speed", int(args[1]))
        link.send(key + "_on", onoff(args))
    elif cmd == "pump":
        link.send("airpump_on", onoff(args))
    elif cmd in ("shoulders", "arms", "legs", "outside"):
        link.send("airbag_%s_on" % cmd, onoff(args))
    elif cmd == "led":
        rgb = [int(x) for x in args[:3]] or [0, 0, 0]
        while len(rgb) < 3:
            rgb.append(0)
        link.send("backlight_color", *rgb)
        link.send("backlight_on", 1)
    elif cmd == "raw":
        link.send_raw(line[3:].strip())
    else:
        print("  ? unknown command (try `help`)")
        return True

    time.sleep(0.15)
    show(link.drain(0.3))
    return True


def main():
    ap = argparse.ArgumentParser(description="Massage chair motor smoke test")
    ap.add_argument("port", nargs="?", help="/dev/ttyACM0  or  tcp:host:port")
    ap.add_argument("--list", action="store_true", help="scan & identify serial ports")
    ap.add_argument("--seq", action="store_true", help="run the canned gentle sequence")
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
    print("Connected. Reading boot/ack output:")
    show(link.drain(2.5))

    try:
        if args.seq:
            for line, note in SEQUENCE:
                if note:
                    print("\n>> %s" % note)
                run_command(link, line)
                time.sleep(1.5)
            print("\nSequence done.")
        else:
            print("\nType `help` for commands, `stop` to kill all, `quit` to exit.\n")
            while True:
                try:
                    line = input("chair> ")
                except (EOFError, KeyboardInterrupt):
                    break
                if not run_command(link, line):
                    break
    finally:
        print("\nStopping everything...")
        try:
            stop_all(link)
        except Exception as e:
            print("  (stop failed: %s)" % e)
        link.close()
        print("Closed.")


if __name__ == "__main__":
    main()
