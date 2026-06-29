"""ProgramRunner: background thread that executes a named massage program.

Owns the *timing* side of a program while the LLM/dashboard own intensity and
technique selection for any given turn:

  - Airbag breathing loop (inflate/deflate with human-breath variability)
  - Zone duty cycling (shoulders / arms / legs, plus the outside wrapper bag)
  - Butt vibration duty cycle
  - Roller choreography (technique + direction sequence)
  - All-off cleanup whenever the program stops or is swapped

Hardware writes go through the caller-supplied `send_hw(key, *values)`.
Dashboard updates go through `broadcast(event_type, **kwargs)` (SSE fan-out).

Pump rule: whenever any zone airbag (or the outside bag) is inflated, the
pump must be on; when all are deflated, the pump goes off. This module is the
single place that flips zone valves during a running program, so the rule is
enforced inline in `_breathing_loop` — pump on/off brackets every zone write.

Dashboard slider overrides (self.overrides) are read fresh on every breath /
duty cycle, so changing a slider takes effect on the next cycle without
restarting the runner.
"""

import random
import threading

from chair.programs import (
    PROGRAMS, DEFAULT_PROGRAM, BREATHING_PROFILES,
    effective_breath, effective_butt,
)

_ZONE_CMDS = {
    "shoulders": "airbag_shoulders_on",
    "arms":      "airbag_arms_on",
    "legs":      "airbag_legs_on",
}


class ProgramRunner:
    def __init__(self, send_hw, broadcast):
        self._send_hw   = send_hw
        self._broadcast = broadcast

        self._lock   = threading.Lock()
        self._stop   = threading.Event()
        self._thread = None

        self.program_name = None
        self.phase         = "idle"
        self.sentiment     = "neutral"
        self.overrides     = {}   # dashboard slider overrides

    # ---- public API --------------------------------------------------

    def start(self, program_name, phase="idle", sentiment="neutral"):
        """Stop whatever is running and start `program_name` fresh."""
        self.stop()
        self._stop = threading.Event()
        stop = self._stop
        with self._lock:
            self.program_name = program_name
            self.phase         = phase
            self.sentiment      = sentiment
        t = threading.Thread(target=self._run, args=(program_name, stop), daemon=True)
        self._thread = t
        t.start()

    def stop(self):
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=6.0)
        self._thread = None

    def update_phase(self, phase):
        with self._lock:
            self.phase = phase

    def update_sentiment(self, sentiment):
        with self._lock:
            self.sentiment = sentiment

    def set_overrides(self, partial):
        with self._lock:
            self.overrides.update(partial)

    # ---- internals ----------------------------------------------------

    def _run(self, program_name, stop):
        prog = PROGRAMS.get(program_name) or PROGRAMS[DEFAULT_PROGRAM]
        threads = []

        has_airbags = bool(prog["airbag_zones"]) or prog.get("airbag_on_s", 0) > 0
        has_butt    = prog.get("butt_on_s", 0) > 0
        has_choreo  = bool(prog.get("roller_choreography"))

        if has_airbags:
            t = threading.Thread(target=self._breathing_loop, args=(prog, stop), daemon=True)
            threads.append(t); t.start()
        if has_butt:
            t = threading.Thread(target=self._butt_loop, args=(prog, stop), daemon=True)
            threads.append(t); t.start()
        if has_choreo:
            t = threading.Thread(target=self._roller_loop, args=(prog, stop), daemon=True)
            threads.append(t); t.start()

        stop.wait()
        self._cleanup(prog)
        for t in threads:
            t.join(timeout=4.0)

    def _breathing_loop(self, prog, stop):
        zones = prog["airbag_zones"]
        profile = BREATHING_PROFILES.get(prog.get("breathing_profile", "active"),
                                         BREATHING_PROFILES["active"])
        var = profile["variability"]

        while not stop.is_set():
            with self._lock:
                phase     = self.phase
                overrides = dict(self.overrides)

            on_s, off_s = effective_breath(prog, phase, overrides)
            jitter = random.uniform(1 - var, 1 + var)
            actual_on  = max(0.5, on_s  * jitter)
            actual_off = max(0.5, off_s * jitter)

            # inhale — pump rule: pump on brackets every zone valve write
            self._send_hw("airpump_on", 1)
            for z in zones:
                cmd = _ZONE_CMDS.get(z)
                if cmd:
                    self._send_hw(cmd, 1)
            self._send_hw("airbag_outside_on", 1)
            self._broadcast("breath", phase="inhale",
                            on_s=actual_on, off_s=actual_off)

            if stop.wait(actual_on):
                break

            # exhale — close every valve, then drop the pump
            for z in zones:
                cmd = _ZONE_CMDS.get(z)
                if cmd:
                    self._send_hw(cmd, 0)
            self._send_hw("airbag_outside_on", 0)
            self._send_hw("airpump_on", 0)
            self._broadcast("breath", phase="exhale",
                            on_s=actual_on, off_s=actual_off)

            if stop.wait(actual_off):
                break

    def _butt_loop(self, prog, stop):
        while not stop.is_set():
            with self._lock:
                overrides = dict(self.overrides)
            on_s, off_s = effective_butt(prog, overrides)
            if on_s <= 0:
                if stop.wait(1.0):
                    break
                continue
            self._send_hw("butt_vibration_on", 1)
            if stop.wait(on_s):
                break
            self._send_hw("butt_vibration_on", 0)
            if stop.wait(off_s):
                break
        self._send_hw("butt_vibration_on", 0)

    def _roller_loop(self, prog, stop):
        choreo = prog["roller_choreography"]
        if not choreo:
            return

        idx = 0
        while not stop.is_set():
            step = choreo[idx % len(choreo)]
            idx += 1

            knead = step.get("knead", False)
            pound = step.get("pound", False)
            direc = step.get("direction", "stop")
            dur_s = step.get("duration_s", 5.0) * random.uniform(0.88, 1.12)

            self._send_hw("roller_kneading_on", 1 if knead else 0)
            self._send_hw("roller_pounding_on", 1 if pound else 0)

            if direc == "up":
                self._send_hw("roller_position_target_range", 10)
                self._send_hw("roller_position_target", 10000)
            elif direc == "down":
                self._send_hw("roller_position_target_range", 10)
                self._send_hw("roller_position_target", 0)
            else:
                self._send_hw("roller_position_target_range", 10000)

            self._broadcast("program_step", knead=knead, pound=pound, direction=direc)

            if stop.wait(dur_s):
                break

        self._send_hw("roller_kneading_on", 0)
        self._send_hw("roller_pounding_on", 0)
        self._send_hw("roller_position_target_range", 10000)
        self._broadcast("program_step", knead=False, pound=False, direction="stop")

    def _cleanup(self, prog):
        for z in prog.get("airbag_zones", []):
            cmd = _ZONE_CMDS.get(z)
            if cmd:
                self._send_hw(cmd, 0)
        self._send_hw("airbag_outside_on", 0)
        self._send_hw("airpump_on", 0)
        self._send_hw("butt_vibration_on", 0)
        self._send_hw("roller_kneading_on", 0)
        self._send_hw("roller_pounding_on", 0)
        self._send_hw("roller_position_target_range", 10000)
