"""Streaming text-to-speech for the phase-1 laptop simulation.

Speaks the chair's `spoken_text` sentence-by-sentence as it generates. Uses two
parallel threads so sentence N+1 is being synthesised while sentence N is still
playing — audio is continuous with no inter-sentence gap.

  synthesis thread: sentence text → PCM bytes  (blocks on piper per sentence)
  playback  thread: PCM bytes → audio output   (single persistent player per turn)

All sentences in one turn flow through the same player process stdin, eliminating
the per-sentence process reconnection that causes audio pops/distortion.

Engine-agnostic: piper (neural), espeak-ng/espeak (robotic), or a custom shell
pipeline. Falls back to a silent no-op if nothing is found.
"""

import array
import json
import math
import os
import queue
import re
import shutil
import subprocess
import threading

import config

# Markdown emphasis markers piper reads aloud literally.
_MD_EMPH = re.compile(r'\*{1,2}|_{1,2}')

# Raw-PCM players, preference order. Each entry returns an argv for a given rate.
_PLAYERS = {
    "paplay": lambda r: ["paplay", "--raw", f"--rate={r}",
                         "--format=s16le", "--channels=1"],
    "pw-play": lambda r: ["pw-play", f"--rate={r}", "--format=s16",
                          "--channels=1", "-"],
    "ffplay":  lambda r: ["ffplay", "-loglevel", "quiet", "-f", "s16le",
                          "-ar", str(r), "-ch_layout", "mono",
                          "-nodisp", "-autoexit", "-i", "-"],
}

# Sentinel: threads through synth_q → play_q to signal end of a turn.
# The play worker closes the player stdin on this, letting it drain cleanly.
_TURN_END = object()


def _split_sentences(buf):
    """Pull complete sentences off the front of `buf`.

    Returns (sentences, remainder). Requires the sentence-ending punctuation to
    be followed by whitespace so a mid-stream "3." (as in "3.5 sec") is never
    emitted early — the tail is always drained by flush() at end of turn.
    """
    sents, start, i, n = [], 0, 0, len(buf)
    while i < n:
        if buf[i] in ".!?…":
            j = i + 1
            while j < n and buf[j] in ".!?…\"')]":
                j += 1
            if j < n and buf[j].isspace():
                seg = buf[start:j].strip()
                if seg:
                    sents.append(seg)
                start = j
                i = j
                continue
        i += 1
    return sents, buf[start:]


def _pick_player():
    for name, builder in _PLAYERS.items():
        if shutil.which(name):
            return name, builder
    return None


def _piper_ready():
    return (os.path.exists(config.TTS_PIPER_BIN)
            and os.path.exists(config.TTS_PIPER_MODEL)
            and _pick_player() is not None)


def _piper_sample_rate():
    try:
        with open(config.TTS_PIPER_MODEL + ".json") as fh:
            return int(json.load(fh)["audio"]["sample_rate"])
    except (OSError, KeyError, ValueError):
        return 22050


def _resolve_backend():
    """Returns (kind, payload) or None."""
    if config.TTS_COMMAND.strip():
        return ("shell", config.TTS_COMMAND.strip())
    want = config.TTS_ENGINE
    if want in ("auto", "piper") and _piper_ready():
        return ("piper", None)
    candidates = ["espeak-ng", "espeak"] if want == "auto" else [want]
    for binary in candidates:
        if binary in ("espeak-ng", "espeak") and shutil.which(binary):
            return ("espeak", binary)
    return None


class Speaker:
    """Sentence-streaming TTS with parallel synthesis + playback."""

    def __init__(self, enabled=True):
        self._backend = _resolve_backend() if (enabled and config.TTS_ENABLED) else None
        self._buf = ""
        if self._backend:
            if self._backend[0] == "piper":
                self._synth_q = queue.Queue()
                self._play_q  = queue.Queue()
                self._rate    = _piper_sample_rate()
                self._player_builder = _pick_player()[1]
                # Persistent player process shared across sentences in a turn.
                self._player_proc = None
                self._player_lock = threading.Lock()
                threading.Thread(target=self._synth_worker, daemon=True).start()
                threading.Thread(target=self._play_worker,  daemon=True).start()
            else:
                self._q = queue.Queue()
                threading.Thread(target=self._seq_worker, daemon=True).start()

    # -- public API -------------------------------------------------------

    @property
    def active(self):
        return self._backend is not None

    @property
    def engine_name(self):
        if not self._backend:
            return None
        kind, _ = self._backend
        if kind == "piper":
            player = _pick_player()
            label = player[0] if player else "?"
            return f"piper ({os.path.basename(config.TTS_PIPER_MODEL)} → {label})"
        return "shell" if kind == "shell" else str(_)

    def feed(self, delta):
        """Accumulate streamed text; speak each completed sentence immediately."""
        if not self._backend:
            return
        self._buf += delta
        sents, self._buf = _split_sentences(self._buf)
        for s in sents:
            self._enqueue(s)

    def flush(self):
        """Speak any trailing text and signal end-of-turn to the player."""
        if not self._backend:
            return
        rest, self._buf = self._buf.strip(), ""
        if rest:
            self._enqueue(rest)
        if self._backend[0] == "piper":
            # _TURN_END threads through synth_q so it arrives in play_q only
            # after all PCM for this turn has been queued.
            self._synth_q.put(_TURN_END)

    def wait(self):
        """Block until all queued audio has finished playing."""
        if not self._backend:
            return
        if self._backend[0] == "piper":
            self._synth_q.join()
            self._play_q.join()
        else:
            self._q.join()

    def wait_async(self, callback):
        """Call callback in a background thread once all audio has finished."""
        def _wait():
            self.wait()
            callback()
        threading.Thread(target=_wait, daemon=True).start()

    def cancel(self):
        """Stop playback immediately: kill the player process, drain queues."""
        self._buf = ""
        if not self._backend:
            return
        if self._backend[0] == "piper":
            # Kill the active player process so audio stops mid-sentence.
            with self._player_lock:
                proc = self._player_proc
                self._player_proc = None
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=1)
                except Exception:  # noqa: BLE001
                    pass
            # Drain both queues so the workers don't play anything further.
            for q in (self._synth_q, self._play_q):
                while not q.empty():
                    try:
                        q.get_nowait()
                        q.task_done()
                    except Exception:  # noqa: BLE001
                        break
        else:
            while not self._q.empty():
                try:
                    self._q.get_nowait()
                    self._q.task_done()
                except Exception:  # noqa: BLE001
                    break

    def play_click(self):
        """Play a short soft click tone immediately in a background thread."""
        if not self._backend or self._backend[0] != "piper":
            return
        rate = self._rate
        dur  = 0.055
        freq = 520
        n    = int(rate * dur)
        buf  = array.array('h', [0] * n)
        for i in range(n):
            env = min(i, n - i) / max(1, n * 0.18)
            env = min(1.0, env)
            buf[i] = int(env * 3200 * math.sin(2 * math.pi * freq * i / rate))
        threading.Thread(target=self._play_click_raw, args=(buf.tobytes(),),
                         daemon=True).start()

    # -- internals --------------------------------------------------------

    def _enqueue(self, text):
        text = _MD_EMPH.sub('', text).strip()
        if len(text) < 3:
            return
        if self._backend[0] == "piper":
            self._synth_q.put(text)
        else:
            self._q.put(text)

    # piper: synthesis worker — text → PCM
    def _synth_worker(self):
        while True:
            item = self._synth_q.get()
            try:
                if item is _TURN_END:
                    # Pass the sentinel downstream so play_worker knows to close
                    # the player after all PCM it already queued has been written.
                    self._play_q.put(_TURN_END)
                else:
                    pcm = self._piper_synthesize(item)
                    if pcm:
                        self._play_q.put(pcm)
            except Exception:  # noqa: BLE001
                pass
            finally:
                self._synth_q.task_done()

    # piper: play worker — persistent player process per turn
    def _play_worker(self):
        while True:
            item = self._play_q.get()
            try:
                if item is _TURN_END:
                    # Close stdin and wait for the player to drain its buffer.
                    with self._player_lock:
                        proc = self._player_proc
                        self._player_proc = None
                    if proc:
                        try:
                            proc.stdin.close()
                        except OSError:
                            pass
                        try:
                            proc.wait(timeout=10)
                        except Exception:  # noqa: BLE001
                            pass
                else:
                    # PCM bytes: write to the persistent player, starting it if needed.
                    with self._player_lock:
                        if self._player_proc is None or self._player_proc.poll() is not None:
                            self._player_proc = subprocess.Popen(
                                self._player_builder(self._rate),
                                stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
                        proc = self._player_proc
                    try:
                        proc.stdin.write(item)
                        proc.stdin.flush()
                    except OSError:
                        pass
            except Exception:  # noqa: BLE001
                pass
            finally:
                self._play_q.task_done()

    def _piper_synthesize(self, text):
        """Run piper on one sentence and return raw PCM bytes."""
        proc = subprocess.Popen(
            [config.TTS_PIPER_BIN, "-m", config.TTS_PIPER_MODEL,
             "--output-raw", "--sentence-silence", "0.15"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)
        pcm, _ = proc.communicate(text.strip().encode() + b"\n")
        return pcm if pcm else None

    def _play_click_raw(self, pcm):
        """Spawn a one-shot player for the click tone (bypass the turn queue)."""
        try:
            proc = subprocess.Popen(
                self._player_builder(self._rate),
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.communicate(pcm)
        except Exception:  # noqa: BLE001
            pass

    # espeak / shell: simple sequential worker
    def _seq_worker(self):
        while True:
            text = self._q.get()
            try:
                kind, payload = self._backend
                if kind == "shell":
                    subprocess.run(payload, shell=True, input=text.encode(),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    cmd = [payload, "-s", str(config.TTS_RATE)]
                    if config.TTS_VOICE:
                        cmd += ["-v", config.TTS_VOICE]
                    subprocess.run(cmd, input=text, text=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:  # noqa: BLE001
                pass
            finally:
                self._q.task_done()
