"""Serial link to the chair's two MCUs (stdlib-only).

Protocol (reverse-engineered from SuicidalMassagechairV2 Arduino firmware):

ChairSystem MCU (the one that drives all the motors/airbags/LEDs):
  - 115200 baud, 8N1, raw.
  - Host -> MCU: one JSON object per packet, framed by '{' .. '}'. Every value
    is wrapped in an array, e.g.  {"roller_kneading_on":[1]}
                                  {"backlight_color":[255,0,0]}
  - MCU -> host: after every command (and periodically) it prints a big JSON
    status/ack blob containing the full state (roller_kneading_on, etc).

Controller MCU (buttons + 3 OLEDs, NOT motors):
  - 115200 baud. MCU -> host: {"controllerCommand":"buttonYes","controllerValue":"1"}
  - Host -> MCU: {"<infoKey>":[...]} e.g. {"customScreenA":["hello"]}

This module talks to either, but the motor smoke test only needs the ChairSystem
MCU. A `port` may be a local device path ("/dev/ttyACM0") or a network bridge
("tcp:HOSTNAME:7000") when the MCUs are plugged into a different machine
(e.g. the LattePanda) and exposed via socat/ser2net.
"""

import json
import os
import select
import socket
import subprocess
import time


class ChairLink:
    def __init__(self, port, baud=115200, boot_wait=0.0):
        self.port = port
        self.baud = baud
        self.boot_wait = boot_wait
        self._fd = None          # local serial: raw os fd
        self._sock = None        # tcp bridge: socket
        self._rxbuf = ""

    # ---- connection -------------------------------------------------
    def open(self):
        if self.port.startswith("tcp:"):
            _, host, p = self.port.split(":", 2)
            self._sock = socket.create_connection((host, int(p)), timeout=5)
            self._sock.setblocking(False)
        else:
            # configure line discipline first; raw = 8N1, no echo, no canon
            subprocess.run(
                ["stty", "-F", self.port, str(self.baud), "raw", "-echo", "-echoe",
                 "-echok", "-echoctl", "-echoke", "-ixon", "-crtscts"],
                check=True,
            )
            self._fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            # Many Arduinos reset on port open; give the sketch time to boot.
            if self.boot_wait:
                time.sleep(self.boot_wait)
        return self

    def close(self):
        try:
            if self._fd is not None:
                os.close(self._fd)
            if self._sock is not None:
                self._sock.close()
        finally:
            self._fd = None
            self._sock = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    # ---- low level io -----------------------------------------------
    def _fileno(self):
        return self._sock.fileno() if self._sock is not None else self._fd

    def _write(self, data: bytes):
        if self._sock is not None:
            self._sock.sendall(data)
        else:
            os.write(self._fd, data)

    def _read_available(self) -> str:
        out = []
        while True:
            r, _, _ = select.select([self._fileno()], [], [], 0)
            if not r:
                break
            try:
                if self._sock is not None:
                    chunk = self._sock.recv(4096)
                else:
                    chunk = os.read(self._fd, 4096)
            except (BlockingIOError, InterruptedError):
                break
            if not chunk:
                break
            out.append(chunk.decode("utf-8", "replace"))
        return "".join(out)

    # ---- protocol ---------------------------------------------------
    def send(self, key: str, *values):
        """Send one command, e.g. send("roller_kneading_on", 1)."""
        if not values:
            values = (1,)
        payload = json.dumps({key: list(values)}, separators=(",", ":"))
        self._write(payload.encode())
        return payload

    def send_raw(self, text: str):
        self._write(text.encode())
        return text

    def drain(self, seconds=0.3):
        """Collect MCU output for `seconds`, return list of complete JSON blobs
        (and any leftover non-JSON lines)."""
        deadline = time.time() + seconds
        blobs = []
        while time.time() < deadline:
            self._rxbuf += self._read_available()
            blobs.extend(self._extract_objects())
            time.sleep(0.02)
        self._rxbuf += self._read_available()
        blobs.extend(self._extract_objects())
        return blobs

    def _extract_objects(self):
        """Pull balanced {...} objects out of the rx buffer."""
        objs, depth, start = [], 0, None
        i = 0
        consumed = 0
        buf = self._rxbuf
        while i < len(buf):
            c = buf[i]
            if c == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif c == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0:
                        chunk = buf[start:i + 1]
                        try:
                            objs.append(json.loads(chunk))
                        except json.JSONDecodeError:
                            objs.append({"_raw": chunk})
                        consumed = i + 1
            i += 1
        self._rxbuf = buf[consumed:]
        return objs


def list_serial_ports():
    import glob
    return sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))


def identify(port, listen=2.5):
    """Open a port, watch its chatter, and guess which MCU it is."""
    with ChairLink(port, boot_wait=0.0) as link:
        # nudge the chair MCU to emit a status ack
        try:
            link.send("status", 1)
        except Exception:
            pass
        blobs = link.drain(listen)
    role = "unknown"
    keys = set()
    for b in blobs:
        keys |= set(b.keys())
    if "controllerCommand" in keys:
        role = "controller (buttons/OLED)"
    elif {"roller_kneading_on", "chair_position_estimated"} & keys:
        role = "chair-system (MOTORS)"
    return role, blobs
