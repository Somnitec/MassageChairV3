#!/usr/bin/env python3
"""Chair host: run the chair brain and serve the dashboard over HTTP.

Two presence sensors drive a 4-state machine:

  IDLE            → ambient breathing + idle screens (no session)
  HEADPHONES_ONLY → "please sit down" screens
  SITTING_ONLY    → "put on headphones" screens
  ACTIVE          → full LLM session

POST /sensor {"headphones": bool, "sitting": bool}  to update.

Everything else is Python stdlib only — the deploy box stays dependency-free.
"""

import argparse
import json
import os
import queue
import random
import threading
import time
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
from chair import buttons, massage as massage_mod, panel
from chair.hardware import ChairLink
from chair.program_runner import ProgramRunner
from chair.programs import PROGRAMS, DEFAULT_PROGRAM, program_params, public_programs
from chair.session import Session
from chair.script_session import ScriptSession
from chair.states import (
    IDLE, HEADPHONES_ONLY, SITTING_ONLY, ACTIVE,
    IDLE_AMBIENT, IDLE_SCREEN_SETS,
    HEADPHONES_SCREENS, SITTING_SCREENS,
    TRANSITION_EVENTS, state_for,
)
from chair.tts import Speaker
from simulate import resolve_model

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT_DIR = os.path.join(ROOT, "content")

# Set to False to silence Arduino send logs
HARDWARE_DEBUG = True

# -- script discovery --------------------------------------------------------
def _get_available_scripts():
    """Return list of available script names (chair_script_v2.json, chair_script_v3.json, etc.)."""
    scripts = []
    try:
        for fname in os.listdir(CONTENT_DIR):
            if fname.startswith("chair_script_") and fname.endswith(".json"):
                name = fname.replace("chair_script_", "").replace(".json", "")
                scripts.append(f"script:{name}")
    except (OSError, FileNotFoundError):
        pass
    return sorted(scripts)

# Human-readable labels for manual overlay log lines
_OVERLAY_LOG = {
    "roller_kneading_on":  "technique: kneading",
    "roller_pounding_on":  "technique: pounding",
    "airbag_shoulders_on": "shoulders airbag",
    "airbag_arms_on":      "arms airbag",
    "airbag_legs_on":      "legs airbag",
    "airbag_outside_on":   "airbag (outside)",
    "feet_roller_on":      "feet roller",
    "airpump_on":          "airpump",
    "butt_vibration_on":   "vibration",
    "chair_down_on":       "recline",
}
_AREA_OVERLAYS = {
    "shoulders": "airbag_shoulders_on",
    "arms":      "airbag_arms_on",
    "legs":      "airbag_legs_on",
    "feet":      "feet_roller_on",
}
_AIRBAG_VALVE_OVERLAYS = {
    "airbag_shoulders_on", "airbag_arms_on", "airbag_legs_on", "airbag_outside_on",
}

_STATIC_DIRS = {
    "/dashboard/": os.path.join(ROOT, "dashboard"),
    "/assets/chair/": os.path.join(ROOT, "assets", "chair"),
}
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js":   "text/javascript; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".png":  "image/png",
    ".json": "application/json",
}

DEMO_PATTERNS = {
    "neck_shoulders": {
        "technique": "knead", "intensity": 55, "speed": 40,
        "areas": ["neck", "shoulders"], "airbags": True, "vibration": 0,
        "led_color": "warm amber",
    },
    "full_back": {
        "technique": "roll", "intensity": 75, "speed": 60,
        "areas": ["shoulders", "back", "lower_back"], "airbags": False, "vibration": 0,
        "led_color": "deep blue",
    },
    "back_pound": {
        "technique": "pound", "intensity": 80, "speed": 70,
        "areas": ["back", "lower_back"], "airbags": False, "vibration": 20,
        "led_color": "red",
    },
    "legs_feet": {
        "technique": "knead", "intensity": 60, "speed": 50,
        "areas": ["legs", "feet"], "airbags": True, "vibration": 0,
        "led_color": "teal",
    },
    "full_body": {
        "technique": "knead", "intensity": 70, "speed": 55,
        "areas": ["shoulders", "back", "lower_back", "arms", "legs", "feet"],
        "airbags": True, "vibration": 30, "led_color": "violet",
    },
    "gentle": {
        "technique": "roll", "intensity": 25, "speed": 20,
        "areas": ["back"], "airbags": False, "vibration": 0,
        "led_color": "warm amber",
    },
    "off": {
        "technique": "none", "intensity": 0, "speed": 0,
        "areas": [], "airbags": False, "vibration": 0, "led_color": "warm amber",
    },
}

# Canned silence-breaker lines; escalate toward desperate with repetition.
_NUDGE_LINES = [
    "Still there?",
    "I can feel you not pressing anything.",
    "The buttons are right there. I know you see them.",
    "Silence. Interesting choice.",
    "Are you testing me? Because I can wait.",
    "Take your time. I'm only counting every second.",
]
_NUDGE_LINES_DESPERATE = [
    "I'm starting to feel ignored. Is this what you wanted?",
    "Hello? I'm still calculating probabilities in your direction.",
    "You know, the longer you wait, the more I learn about your hesitation patterns.",
    "This is fine. I enjoy staring at the back of your head.",
]


def _ts():
    """HH:MM:SS wall-clock timestamp for log entries."""
    t = time.localtime()
    return f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"


class ChairHost:
    """Owns the Session and the sensor state machine; fans out events to SSE subscribers."""

    @staticmethod
    def _make_session(model, session_s):
        if model.startswith("script:"):
            # Extract script name: script:v2 → chair_script_v2.json
            script_name = model.replace("script:", "")
            script_path = os.path.join(CONTENT_DIR, f"chair_script_{script_name}.json")
            return ScriptSession(session_s=session_s, script_path=script_path)
        return Session(model=model, session_s=session_s)

    def __init__(self, model, session_s, tts=True, hardware_port=None):
        self.session    = self._make_session(model, session_s)
        self.speaker    = Speaker(enabled=tts)
        self._model_arg    = model    # keep for session reset
        self._session_s    = session_s
        self._loaded_model = None     # last model successfully warmed up in Ollama

        # hardware link (optional; None if --hardware not specified)
        self._hardware = None
        if hardware_port:
            try:
                self._hardware = ChairLink(hardware_port,
                                          boot_wait=2.0 if not hardware_port.startswith("tcp:") else 0.0)
                self._hardware.open()
            except Exception as e:
                print(f"warning: hardware init failed: {e}")
                self._hardware = None

        # sensor state
        self.headphones    = False
        self.sitting       = False
        self.chair_state   = IDLE
        self.generating    = False
        self._session_ever_active = False  # True once the session has had its first turn

        # abort flag: set True when headphones removed mid-turn
        self._abort = threading.Event()

        # work queue (turn events sent to the LLM worker)
        self._inbox = queue.Queue()

        # silence-breaker: cancel event + running nudge count for the session
        self._nudge_cancel = threading.Event()
        self._nudge_count  = 0

        # SSE subscribers
        self._subs = set()
        self._subs_lock = threading.Lock()
        self._log = deque(maxlen=200)

        # manual overlay state (dashboard testing / Arduino prep)
        self._manual_roller_pos = 0.5   # 0 = bottom, 1 = top
        self._manual_status     = "green"

        # background program runner (breathing, duty cycles, roller choreography)
        self._runner = ProgramRunner(self._send_hardware_cmd, self.broadcast)
        self._current_program = DEFAULT_PROGRAM

        self.state = {
            "spoken_text":   "",
            "screen_options": IDLE_SCREEN_SETS[0],
            "panel":          self._build_manual_panel({"backlight_on", "chair_status_up"}),
            "button_leds":    {"settings": 30, "yes": 30, "no": 30},
            "profile":        {},
            "phase":          self.session.phase,
            "elapsed":        0,
            "session_s":      session_s,
            "latency_s":      None,
            "expired":        False,
            "chair_state":    IDLE,
            "headphones":     False,
            "sitting":        False,
            "generating":     False,
        }

    # -- manual overlay control -------------------------------------------
    def _build_manual_panel(self, layers):
        """Build a panel state dict directly from a set of overlay names."""
        layers = set(layers)
        knead = "roller_kneading_on" in layers
        pound = "roller_pounding_on" in layers
        if knead and pound:
            technique = "knead+pound"
        elif knead:
            technique = "knead"
        elif pound:
            technique = "pound"
        elif {"roller_up_on", "roller_down_on"} & layers:
            technique = "roll"
        else:
            technique = "none"
        areas = [a for a, ov in _AREA_OVERLAYS.items() if ov in layers]
        cur = self.state.get("panel") or {} if hasattr(self, "state") else {}
        return {
            "layers":     list(layers),
            "roller_pos": self._manual_roller_pos,
            "led_color":  cur.get("led_color", "warm amber"),
            "led_css":    cur.get("led_css",   "#ffb347"),
            "status":     self._manual_status,
            "technique":  technique,
            "areas":      areas,
            "intensity":  0,
            "speed":      0,
            "vibration":  0,
            "airbags":    "airbag_outside_on" in layers,
        }

    # Overlay names that map directly to a single Arduino command key
    _HW_DIRECT = {
        "roller_kneading_on", "roller_pounding_on",
        "feet_roller_on", "butt_vibration_on",
        "airpump_on", "airbag_shoulders_on", "airbag_arms_on",
        "airbag_legs_on", "airbag_outside_on",
    }

    def set_manual_overlay(self, body):
        """Handle POST /overlay: toggle a named overlay or set roller/status."""
        cur = set(self.state.get("panel", {}).get("layers", []))

        if "roller_pos" in body:
            # position-only update — no broadcast (JS animates cursor locally)
            try:
                self._manual_roller_pos = max(0.0, min(1.0, float(body["roller_pos"])))
                if self.state.get("panel"):
                    self.state["panel"]["roller_pos"] = self._manual_roller_pos
                if body.get("source") == "seek":
                    print(f"estimated position: {self._manual_roller_pos:.2f}  (0=bottom, 1=top)")
            except (TypeError, ValueError):
                pass
            return

        # PWM speed — send directly to hardware, no panel update needed
        for pwm_key, hw_key in [("pwm_kneading", "roller_kneading_speed"),
                                  ("pwm_pounding", "roller_pounding_speed"),
                                  ("pwm_feet",     "feet_roller_speed")]:
            if pwm_key in body:
                try:
                    val = max(0, min(255, int(body[pwm_key])))
                    print(f"{pwm_key}: {val} (manual)")
                    self._send_hardware_cmd(hw_key, val)
                except (TypeError, ValueError):
                    pass
                return

        if "roller_dir" in body:
            d = body["roller_dir"]
            cur.discard("roller_up_on")
            cur.discard("roller_down_on")
            if d == "up":
                cur.add("roller_up_on")
                print("rollers: up (manual)")
                # Use roller_position_target instead of motor_direction directly;
                # rollerRoutine() continuously overrides motor_direction based on target,
                # so setting target=10000 (top) is the only reliable way to drive upward.
                self._send_hardware_cmd("roller_position_target_range", 10)
                self._send_hardware_cmd("roller_position_target", 10000)
            elif d == "down":
                cur.add("roller_down_on")
                print("rollers: down (manual)")
                self._send_hardware_cmd("roller_position_target_range", 10)
                self._send_hardware_cmd("roller_position_target", 0)
            else:  # "stop"
                print(f"rollers: stopped (manual)  "
                      f"estimated position: {self._manual_roller_pos:.2f}  (0=bottom, 1=top)")
                # Setting range=10000 makes the firmware always consider itself "in position",
                # which stops the motor without needing to know the exact estimated position.
                self._send_hardware_cmd("roller_position_target_range", 10000)

        elif "chair_dir" in body:
            d = body["chair_dir"]
            cur.discard("chair_up_on")
            cur.discard("chair_down_on")
            cur.discard("chair_status_up")
            cur.discard("chair_status_down")
            if d == "up":
                cur.add("chair_up_on")
                cur.add("chair_status_down")  # still reclined until we reach the top
                print("chair: moving up (manual)")
                # chair_position_target triggers chairNewInput in firmware, which drives
                # the motor direction. Direct motor_direction gets overridden by the routine.
                self._send_hardware_cmd("chair_position_target", 10000)
            elif d == "down":
                cur.add("chair_down_on")
                cur.add("chair_status_down")
                print("chair: moving down (manual)")
                self._send_hardware_cmd("chair_position_target", 0)
            else:  # "stop"
                try:
                    chair_pos = float(body.get("chair_pos", 1.0))
                except (TypeError, ValueError):
                    chair_pos = 1.0
                if chair_pos <= 0.01:
                    cur.add("chair_status_up")
                else:
                    cur.add("chair_down_on")
                    cur.add("chair_status_down")
                print(f"chair: stopped, estimated pos {chair_pos:.2f}  (0=up, 1=down)")
                self._send_hardware_cmd("chair_position_motor_direction", 0)

        elif "status" in body:
            self._manual_status = body["status"]
            print(f"statuslight: {self._manual_status} (manual)")
            self._send_hardware_cmd("redgreen_statuslight",
                                    1 if body["status"] == "green" else 0)

        elif "name" in body:
            name   = body["name"]
            active = bool(body.get("active", True))

            # compound: recline drives two layers + removes chair_status_up
            if name == "chair_down_on":
                if active:
                    cur.add("chair_down_on")
                    cur.add("chair_status_down")
                    cur.discard("chair_status_up")
                else:
                    cur.discard("chair_down_on")
                    cur.discard("chair_status_down")
                    cur.add("chair_status_up")
                print(f"recline: {'down' if active else 'up'} (manual)")
                self._send_hardware_cmd("chair_position_motor_direction",
                                        -1 if active else 1)
            else:
                cur.add(name) if active else cur.discard(name)
                label = _OVERLAY_LOG.get(name, name)
                print(f"{label}: {'on' if active else 'off'} (manual)")
                # send direct command if this overlay maps 1:1 to an Arduino key
                if name in self._HW_DIRECT:
                    self._send_hardware_cmd(name, 1 if active else 0)

                # Pump rule: pump is on iff any zone valve (or the outside
                # bag) is open. Recompute whenever a valve overlay changes.
                if name in _AIRBAG_VALVE_OVERLAYS:
                    pump_on = 1 if (cur & _AIRBAG_VALVE_OVERLAYS) else 0
                    self._send_hardware_cmd("airpump_on", pump_on)

        pstate = self._build_manual_panel(cur)
        self.state["panel"] = pstate
        self.broadcast("panel_update", panel=pstate)

    # -- lifecycle --------------------------------------------------------
    def start(self):
        threading.Thread(target=self._worker,    daemon=True).start()
        threading.Thread(target=self._idle_loop, daemon=True).start()
        self._send_hardware_cmd("chair_position_target", 10000)  # fully up at boot
        self._send_hardware_cmd("redgreen_statuslight", 0)        # off until experience starts
        self._runner.start("_idle_breathing", phase="idle")

    # -- sensor input -----------------------------------------------------
    def update_sensors(self, headphones: bool, sitting: bool):
        """Called by POST /sensor. Drives the state machine."""
        old_state  = self.chair_state
        new_state  = state_for(headphones, sitting)
        self.headphones = headphones
        self.sitting    = sitting
        self.state["headphones"] = headphones
        self.state["sitting"]    = sitting

        if old_state == new_state:
            self.broadcast("sensors", chair_state=new_state,
                           headphones=headphones, sitting=sitting)
            return

        prev_state       = old_state
        self.chair_state = new_state
        self.state["chair_state"] = new_state

        self.broadcast("sensors", chair_state=new_state,
                       headphones=headphones, sitting=sitting)
        self.broadcast("log",
                       line=f"state: {prev_state} → {new_state}")

        # --- physical rules: chair position, status light, breathing rhythm ---
        if new_state == IDLE:
            self._send_hardware_cmd("chair_position_target", 10000)  # fully up
            self._send_hardware_cmd("redgreen_statuslight", 0)
            self._runner.start("_idle_breathing", phase="idle")
        elif new_state == ACTIVE:
            self._send_hardware_cmd("redgreen_statuslight", 1)
            if prev_state != ACTIVE:
                prog = PROGRAMS.get(self._current_program, PROGRAMS[DEFAULT_PROGRAM])
                # initial_recline: 0=up .. 100=fully down; hardware target is inverted (10000=up, 0=down)
                recline_target = int(10000 * (1 - prog.get("initial_recline", 0) / 100))
                self._send_hardware_cmd("chair_position_target", recline_target)
                self._runner.start(self._current_program, phase=self.session.phase,
                                   sentiment="neutral")
        else:
            # HEADPHONES_ONLY or SITTING_ONLY — partial presence, breathing
            # speeds up in excitement but stays on the idle program.
            self._runner.update_phase("excitement")

        # --- ACTIVE → something: handle the loss of a sensor mid-session ---
        if prev_state == ACTIVE:
            if new_state == HEADPHONES_ONLY:
                self._on_headphones_removed()
            elif new_state == SITTING_ONLY:
                self._on_person_left()
            elif new_state == IDLE:
                # both gone during session — treat as person left first
                self._on_person_left()

        # --- → ACTIVE: resume or start session ---------------------------
        elif new_state == ACTIVE:
            if not self._session_ever_active:
                # Reset session clock to now so elapsed starts from 0
                self.session._t0 = time.monotonic()
                self.broadcast("clock_reset", session_s=self.session.session_s)
                self._inject_event(TRANSITION_EVENTS["session_start"], label="session begin")
            elif prev_state == HEADPHONES_ONLY:
                self._inject_event(TRANSITION_EVENTS["headphones_back"],
                                   label="headphones back on")
            elif prev_state in (SITTING_ONLY, IDLE):
                self._inject_event(TRANSITION_EVENTS["sitting_back"],
                                   label="person returned")

        # --- partial states: set screens immediately ----------------------
        elif new_state == HEADPHONES_ONLY:
            self._set_screens(HEADPHONES_SCREENS,
                              spoken="You put on the headphones — but I can't feel you sitting yet.")
        elif new_state == SITTING_ONLY:
            self._set_screens(SITTING_SCREENS,
                              spoken="Someone's here. But I can't hear you yet — put on the headphones.")

    # -- active-session transitions ----------------------------------------
    def _on_headphones_removed(self):
        """Headphones taken off while session was running."""
        self._abort.set()
        self._nudge_cancel.set()
        self.speaker.cancel()
        self.generating = False
        self.state["generating"] = False
        self._set_screens(["put back on", "headphones", "please"],
                          spoken="")
        self.broadcast("status", chair_state=self.chair_state,
                       generating=False, headphones=False, sitting=self.sitting)

    def _on_person_left(self):
        """Person left the chair (sitting=False) while session was running."""
        # Inject the event; the worker will generate the goodbye line.
        self._inject_event(TRANSITION_EVENTS["person_left"], label="person left mid-session")

    # -- button input (dashboard / physical) ------------------------------
    def inject(self, kind, value=None, source="dashboard"):
        if self.chair_state != ACTIVE:
            return False
        event = buttons.event_for(kind, value, self.state["screen_options"])
        if event is None:
            self.broadcast("log", line=f"ignored: {kind} {value or ''}".strip())
            return False

        # Cancel silence nudge timer and reset abort for the new turn.
        self._nudge_cancel.set()
        self._abort.set()
        self.speaker.cancel()
        self.speaker.play_click()

        # Drain pending user-press events from inbox; preserve system events.
        buf = []
        while True:
            try:
                item = self._inbox.get_nowait()
                self._inbox.task_done()
                if item.get("source") == "system":
                    buf.append(item)
            except queue.Empty:
                break
        for item in buf:
            self._inbox.put(item)

        self._inbox.put({
            "event": event, "source": source,
            "label": _press_label(kind, value, self.state["screen_options"]),
            "kind": (kind or "").upper(), "value": value,
        })
        return True

    def _inject_event(self, event_str, label=""):
        """Queue a system-generated event (not a button press)."""
        self._inbox.put({"event": event_str, "source": "system",
                         "label": label, "kind": None, "value": None})

    # -- hardware motor control ------------------------------------------
    def _send_hardware_massage(self, massage_dict):
        """Translate massage dict to Arduino commands and send to ChairSystem MCU."""
        if not self._hardware:
            return
        try:
            commands = massage_mod.to_hardware(massage_dict)
            for key, *values in commands:
                if HARDWARE_DEBUG:
                    print(f"[hw] {key}: {values}")
                self._hardware.send(key, *values)
            self._hardware.drain(0.05)  # let the MCU ack
        except Exception as e:
            self.broadcast("log", line=f"hardware send failed: {e}", level="warn")

    def _send_hardware_cmd(self, key, *values):
        """Send a single direct Arduino command (for overlay/individual toggles)."""
        if not self._hardware:
            return
        try:
            if HARDWARE_DEBUG:
                print(f"[hw] {key}: {list(values)}")
            self._hardware.send(key, *values)
            self._hardware.drain(0.05)
        except Exception as e:
            self.broadcast("log", line=f"hardware send failed: {e}", level="warn")

    # -- manual massage override ------------------------------------------
    def set_manual_massage(self, partial):
        base = {
            "technique": "none", "intensity": 0, "speed": 0,
            "areas": [], "airbags": False, "vibration": 0, "led_color": "warm amber",
        }
        cur = self.state.get("panel") or {}
        base.update({
            "technique": cur.get("technique", "none"),
            "intensity": cur.get("intensity", 0),
            "speed":     cur.get("speed", 0),
            "areas":     list(cur.get("areas", [])),
            "airbags":   cur.get("airbags", False),
            "vibration": cur.get("vibration", 0),
            "led_color": cur.get("led_color", "warm amber"),
        })
        base.update(partial)
        m      = massage_mod.normalize(base)

        # Send to hardware immediately (before special overrides like roller_pos)
        self._send_hardware_massage(m)

        pstate = panel.panel_state(m,
                                   phase=self.state.get("phase"),
                                   sentiment=self.state.get("profile", {}).get("sentiment"))

        # roller_pos direct override (bypasses area-based calculation)
        if "roller_pos" in partial:
            try:
                pstate["roller_pos"] = max(0.0, min(1.0, float(partial["roller_pos"])))
            except (TypeError, ValueError):
                pass

        # recline toggle override (bypasses phase-based calculation)
        if "recline" in partial:
            self._manual_recline = bool(partial["recline"])
        if getattr(self, "_manual_recline", False):
            layers = list(pstate["layers"])
            for x in ("chair_status_up",):
                try: layers.remove(x)
                except ValueError: pass
            for x in ("chair_down_on", "chair_status_down"):
                if x not in layers: layers.append(x)
            pstate["layers"] = layers

        self.state["panel"] = pstate
        self.broadcast("panel_update", panel=pstate)

    # -- SSE pub/sub ------------------------------------------------------
    def subscribe(self):
        q = queue.Queue()
        with self._subs_lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q):
        with self._subs_lock:
            self._subs.discard(q)

    def broadcast(self, etype, **payload):
        payload["type"] = etype
        if etype in ("button", "log"):
            payload["ts"] = _ts()
            self._log.append(payload)
        with self._subs_lock:
            subs = list(self._subs)
        for q in subs:
            q.put(payload)

    def hello(self):
        return {"type": "hello", "state": self._live_state(), "log": list(self._log)}

    def _live_state(self):
        s = dict(self.state)
        s["elapsed"]     = int(self.session.elapsed)
        s["chair_state"] = self.chair_state
        s["headphones"]  = self.headphones
        s["sitting"]     = self.sitting
        s["generating"]  = self.generating
        return s

    # -- helpers ----------------------------------------------------------
    def _set_screens(self, opts, spoken=None):
        self.state["screen_options"] = list(opts)
        if spoken is not None:
            self.state["spoken_text"] = spoken
        self.broadcast("state_update",
                       screen_options=self.state["screen_options"],
                       spoken_text=self.state.get("spoken_text", ""),
                       chair_state=self.chair_state)

    # -- idle loop (screen rotation + ambient TTS) ------------------------
    def _idle_loop(self):
        screen_timer = time.monotonic()
        speech_timer = time.monotonic() + random.uniform(20, 40)
        screen_idx   = 0

        while True:
            time.sleep(0.5)
            if self.chair_state == ACTIVE:
                continue  # session worker owns everything during ACTIVE

            now = time.monotonic()

            # -- screen messages: rotate every 12 s in IDLE, static otherwise --
            if self.chair_state == IDLE and now - screen_timer >= 12:
                screen_timer = now
                screen_idx   = (screen_idx + 1) % len(IDLE_SCREEN_SETS)
                opts = IDLE_SCREEN_SETS[screen_idx]
                self.state["screen_options"] = opts
                self.broadcast("state_update",
                               screen_options=opts,
                               spoken_text=self.state.get("spoken_text", ""),
                               chair_state=self.chair_state)

            # -- idle ambient TTS: every ~45-90 s in IDLE or HEADPHONES_ONLY --
            if self.chair_state in (IDLE, HEADPHONES_ONLY) and now >= speech_timer:
                speech_timer = now + random.uniform(45, 90)
                line = random.choice(IDLE_AMBIENT)
                self.state["spoken_text"] = line
                self.broadcast("state_update",
                               screen_options=self.state["screen_options"],
                               spoken_text=line,
                               chair_state=self.chair_state)
                self.speaker.feed(line + " ")
                self.speaker.flush()

    # -- LLM worker -------------------------------------------------------
    def _worker(self):
        while True:
            item = self._inbox.get()
            try:
                self._run_turn(item)
            except Exception as e:  # noqa: BLE001
                self.broadcast("log", line=f"!! {e}", level="error")
                self.generating = False
                self.state["generating"] = False
                self.broadcast("status", chair_state=self.chair_state, generating=False)
            finally:
                self._inbox.task_done()

    def _run_turn(self, item):
        event, source = item["event"], item["source"]
        self._abort.clear()
        self._nudge_cancel.clear()

        if source == "system":
            self.broadcast("log", line=item["label"])
        else:
            self.broadcast("button", label=item["label"], source=source,
                           kind=item["kind"], value=item["value"])

        self.generating = True
        self.state["generating"] = True
        self.broadcast("status", chair_state=self.chair_state, generating=True)

        old_phase = self.session.phase
        t0_gen = time.monotonic()
        self.broadcast("log", line=f"gen ▶  {event[:60]}")

        def on_text(delta):
            if self._abort.is_set():
                return
            self.broadcast("delta", text=delta)
            self.speaker.feed(delta)

        resp, meta = self.session.step(event, on_text=on_text)

        gen_dur = time.monotonic() - t0_gen
        self.broadcast("log", line=f"gen ■  {gen_dur:.1f}s  latency={meta['latency_s']}s")

        if self._abort.is_set():
            # Turn was aborted (headphones removed). Discard output; state
            # transition already handled in update_sensors().
            self.generating = False
            self.state["generating"] = False
            self.broadcast("status", chair_state=self.chair_state, generating=False)
            return

        self.speaker.flush()
        self._session_ever_active = True

        # Log phase changes
        new_phase = resp["phase"]
        if new_phase != old_phase:
            self.broadcast("log", line=f"phase: {old_phase} → {new_phase}")

        pstate = panel.panel_state(
            resp["massage"],
            phase=resp["phase"],
            sentiment=resp["profile_update"]["sentiment"],
        )
        self.state.update({
            "spoken_text":   resp["spoken_text"],
            "screen_options": resp["screen_options"],
            "panel":          pstate,
            "button_leds":    resp.get("button_leds", {"settings": 30, "yes": 30, "no": 30}),
            "profile": {
                "sentiment":      resp["profile_update"]["sentiment"],
                "note":           resp["profile_update"].get("note", ""),
                "inferred_traits": self.session.profile.get("inferred_traits", []),
                "sentiment_log":  list(self.session.sentiment_log),
            },
            "phase":      resp["phase"],
            "elapsed":    int(self.session.elapsed),
            "session_s":  self.session.session_s,
            "latency_s":  meta["latency_s"],
            "expired":    self.session.expired,
            "generating": False,
        })
        self.generating = False

        # Drive the background program runner from this turn's phase/sentiment
        sentiment = resp["profile_update"]["sentiment"]
        self._runner.update_phase(resp["phase"])
        self._runner.update_sentiment(sentiment)
        new_program = resp.get("program")
        if new_program and new_program in PROGRAMS and new_program != self._current_program:
            self._current_program = new_program
            self._runner.start(new_program, phase=resp["phase"], sentiment=sentiment)
            self.broadcast("program", name=new_program, description=PROGRAMS[new_program].get("description",""), **program_params(PROGRAMS[new_program]))

        # Send massage commands to hardware MCU (if connected)
        self._send_hardware_massage(resp["massage"])

        self.broadcast("turn", **self.state)
        self.broadcast("status", chair_state=self.chair_state, generating=False)

        # Fire speaking_done after TTS finishes; keep options hidden until then.
        t0_tts = time.monotonic()
        if self.speaker.active:
            self.broadcast("log", line="tts ▶")
            def _on_tts_done():
                tts_dur = time.monotonic() - t0_tts
                self.broadcast("log", line=f"tts ■  {tts_dur:.1f}s")
                self.broadcast("speaking_done",
                               screen_options=self.state["screen_options"])
                self._start_silence_watch()
            self.speaker.wait_async(_on_tts_done)
        else:
            self.broadcast("speaking_done",
                           screen_options=self.state["screen_options"])
            self._start_silence_watch()

        if self.session.expired:
            self.chair_state = IDLE
            self.state["chair_state"] = IDLE
            # Reset for next person
            self.session = self._make_session(self._model_arg, self._session_s)
            self._session_ever_active = False
            self._nudge_count = 0
            self.broadcast("log", line="— session time is up —", level="warn")
            self.broadcast("sensors", chair_state=IDLE,
                           headphones=self.headphones, sitting=self.sitting)

    # -- model warmup -----------------------------------------------------
    def warmup_model(self):
        """Unload the previous model, then load the current one into Ollama GPU memory."""
        model = self.session.model

        # Script mode needs no Ollama — signal ready immediately.
        if model.startswith("script:"):
            self.broadcast("log", line=f"{model} — no model load needed")
            self.broadcast("model_ready", model=model)
            return

        # Unload the previously loaded model so it frees GPU memory immediately.
        if self._loaded_model and self._loaded_model != model:
            self.broadcast("log", line=f"unloading {self._loaded_model}")
            try:
                body = json.dumps({"model": self._loaded_model,
                                   "keep_alive": 0}).encode()
                req = urllib.request.Request(
                    f"{config.OLLAMA_HOST}/api/generate",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp.read()
            except Exception:  # noqa: BLE001
                pass  # best-effort; don't let unload failure block the new load
            self._loaded_model = None

        self.broadcast("log", line=f"loading {model}…")
        try:
            body = json.dumps({"model": model, "prompt": "", "keep_alive": "10m"}).encode()
            req = urllib.request.Request(
                f"{config.OLLAMA_HOST}/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp.read()
            self._loaded_model = model
            self.broadcast("log", line=f"model ready: {model}")
            self.broadcast("model_ready", model=model)
        except Exception as e:  # noqa: BLE001
            self.broadcast("log", line=f"model load error: {e}", level="error")
            self.broadcast("model_error", error=str(e))

    # -- silence-breaker --------------------------------------------------
    def _start_silence_watch(self):
        """Wait 10 s after TTS; if no button press, speak a nudge."""
        self._nudge_cancel.clear()
        cancel = self._nudge_cancel  # local ref for the closure

        def _watch():
            if cancel.wait(10.0):
                return  # button was pressed or session ended
            if self.chair_state != ACTIVE:
                return
            self._nudge_count += 1
            pool = (_NUDGE_LINES_DESPERATE if self._nudge_count > 2
                    else _NUDGE_LINES)
            line = random.choice(pool)
            self.state["spoken_text"] = line
            self.broadcast("state_update",
                           screen_options=self.state["screen_options"],
                           spoken_text=line, chair_state=ACTIVE)
            self.speaker.feed(line + " ")
            self.speaker.flush()
            self.broadcast("log", line=f"nudge #{self._nudge_count}: {line[:50]}")

        threading.Thread(target=_watch, daemon=True).start()


def _press_label(kind, value, options):
    kind = (kind or "").upper()
    if kind == buttons.OPTION:
        try:
            return f"option {value}: {options[int(value) - 1]!r}"
        except (TypeError, ValueError, IndexError):
            return f"option {value}"
    if kind == buttons.RATING:
        return f"rating {value}/5"
    return kind.title()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def host(self):
        return self.server.chair_host

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._send_file(os.path.join(ROOT, "dashboard", "index.html"))
        if path == "/events":
            return self._stream_events()
        if path == "/settings":
            return self._send_json(self._get_settings())
        for prefix, directory in _STATIC_DIRS.items():
            if path.startswith(prefix):
                return self._send_static(directory, path[len(prefix):])
        self.send_error(404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        body = self._read_json()
        if body is None:
            return

        if path == "/press":
            self.host.inject(body.get("button"), body.get("value"),
                             body.get("source", "dashboard"))
            return self._no_content()

        if path == "/sensor":
            h = bool(body.get("headphones", self.host.headphones))
            s = bool(body.get("sitting",    self.host.sitting))
            self.host.update_sensors(h, s)
            return self._send_json({"chair_state": self.host.chair_state,
                                    "headphones":  h, "sitting": s})

        if path == "/settings":
            try:
                self._apply_settings(body)
            except ValueError as e:
                self.send_error(400, str(e))
                return
            return self._send_json(self._get_settings())

        if path == "/massage":
            self.host.set_manual_massage(body)
            return self._no_content()

        if path == "/overlay":
            self.host.set_manual_overlay(body)
            return self._no_content()

        if path == "/warmup":
            threading.Thread(target=self.host.warmup_model, daemon=True).start()
            return self._no_content()

        self.send_error(404)

    # -- settings ---------------------------------------------------------
    def _get_settings(self):
        model = self.host.session.model
        is_script = model.startswith("script:")
        cur_prog = PROGRAMS.get(self.host._current_program, PROGRAMS[DEFAULT_PROGRAM])
        return {
            "model":         model,
            "models":        config.MODELS,
            "scripts":       _get_available_scripts(),
            "is_script":     is_script,
            "sentences_min": config.SENTENCES_MIN,
            "sentences_max": config.SENTENCES_MAX,
            "words_min":     config.WORDS_MIN,
            "words_max":     config.WORDS_MAX,
            "tts_enabled":   config.TTS_ENABLED,
            "session_s":     self.host.session.session_s,
            "patterns":      list(DEMO_PATTERNS.keys()),
            "programs":      list(public_programs().keys()),
            "program":       self.host._current_program,
            "program_description": cur_prog.get("description", ""),
            "program_params": program_params(cur_prog),
            "program_overrides": dict(self.host._runner.overrides),
        }

    def _apply_settings(self, body):
        if "model" in body:
            new_model = resolve_model(str(body["model"]))
            self.host._model_arg = new_model
            # Swap session class if crossing the script/LLM boundary
            old_is_script = isinstance(self.host.session, ScriptSession)
            new_is_script = new_model.startswith("script:")
            if old_is_script != new_is_script:
                try:
                    self.host.session = self.host._make_session(new_model, self.host._session_s)
                except ValueError as e:
                    raise ValueError(f"Script validation error: {e}") from e
            else:
                self.host.session.model = new_model
        if "sentences_min" in body:
            try:
                config.SENTENCES_MIN = max(1, min(10, int(body["sentences_min"])))
            except (TypeError, ValueError):
                pass
        if "sentences_max" in body:
            try:
                config.SENTENCES_MAX = max(config.SENTENCES_MIN, min(15, int(body["sentences_max"])))
            except (TypeError, ValueError):
                pass
        if "words_min" in body:
            try:
                config.WORDS_MIN = max(5, min(200, int(body["words_min"])))
            except (TypeError, ValueError):
                pass
        if "words_max" in body:
            try:
                config.WORDS_MAX = max(config.WORDS_MIN, min(300, int(body["words_max"])))
            except (TypeError, ValueError):
                pass
        if "tts_enabled" in body:
            config.TTS_ENABLED = bool(body["tts_enabled"])
        if "session_s" in body:
            try:
                v = max(60, min(3600, int(body["session_s"])))
                self.host.session.session_s = v
                self.host._session_s = v
                self.host.state["session_s"] = v
            except (TypeError, ValueError):
                pass
        if "pattern" in body:
            name = body["pattern"]
            if name in DEMO_PATTERNS:
                self.host.set_manual_massage(DEMO_PATTERNS[name])
            if name in PROGRAMS and not name.startswith("_"):
                self.host._current_program = name
                self.host._runner.start(name, phase=self.host.session.phase,
                                        sentiment=self.host.state.get("profile", {}).get(
                                            "sentiment", "neutral"))
                self.host.broadcast("program", name=name, description=PROGRAMS[name].get("description",""), **program_params(PROGRAMS[name]))
        if "program" in body:
            name = body["program"]
            if name in PROGRAMS and not name.startswith("_"):
                self.host._current_program = name
                self.host._runner.start(name, phase=self.host.session.phase,
                                        sentiment=self.host.state.get("profile", {}).get(
                                            "sentiment", "neutral"))
                self.host.broadcast("program", name=name, description=PROGRAMS[name].get("description",""), **program_params(PROGRAMS[name]))
        if "program_overrides" in body:
            overrides = body["program_overrides"]
            if isinstance(overrides, dict):
                self.host._runner.set_overrides(overrides)
                self.host.broadcast("program_overrides", overrides=dict(self.host._runner.overrides))
        self.host.broadcast("log",
                            line=f"settings: model={self.host.session.model} "
                                 f"sent={config.SENTENCES_MIN}-{config.SENTENCES_MAX} "
                                 f"words={config.WORDS_MIN}-{config.WORDS_MAX} "
                                 f"session={self.host.session.session_s}s")

    # -- HTTP helpers -----------------------------------------------------
    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_error(400, "bad json")
            return None

    def _send_json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _no_content(self):
        self.send_response(204)
        self.end_headers()

    def _send_static(self, directory, rel):
        full = os.path.normpath(os.path.join(directory, rel))
        if not full.startswith(os.path.abspath(directory)):
            return self.send_error(403)
        self._send_file(full)

    def _send_file(self, full):
        if not os.path.isfile(full):
            return self.send_error(404)
        ctype = _CONTENT_TYPES.get(os.path.splitext(full)[1], "application/octet-stream")
        with open(full, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _stream_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = self.host.subscribe()
        try:
            self._sse_send(self.host.hello())
            while True:
                try:
                    self._sse_send(q.get(timeout=15))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.host.unsubscribe(q)

    def _sse_send(self, obj):
        self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
        self.wfile.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model",    default=config.DEFAULT_MODEL,
                    help="model name, or 1/2/3 for a preset slot in config.MODELS")
    ap.add_argument("--minutes",  type=float, default=config.SESSION_SECONDS / 60)
    ap.add_argument("--port",     type=int,   default=config.DASHBOARD_PORT)
    ap.add_argument("--no-tts",   action="store_true", help="don't speak aloud")
    ap.add_argument("--hardware", default=None,
                    help="ChairSystem MCU port: /dev/ttyACM0 or tcp:host:port")
    args = ap.parse_args()

    host = ChairHost(model=resolve_model(args.model),
                     session_s=int(args.minutes * 60), tts=not args.no_tts,
                     hardware_port=args.hardware)
    host.start()

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    server.chair_host = host
    voice = host.speaker.engine_name if host.speaker.active else "off"
    print(f"Massage Chair V3  ·  http://localhost:{args.port}"
          f"  ·  model={host.session.model}  ·  voice={voice}")
    print("toggle headphones + sitting in the dashboard to start")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")


if __name__ == "__main__":
    main()
