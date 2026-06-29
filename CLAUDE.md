# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An interactive art installation: a self-aware, sardonic massage chair that talks (via TTS) while massaging you. It profiles you from your button presses — out loud, on purpose. The software side is Python, stdlib-only, talking to a local Ollama LLM and driving a neural TTS (piper) on the laptop.

## How to run

```sh
# Interactive terminal dashboard (keyboard-driven, no hardware needed)
python3 simulate.py
python3 simulate.py --model qwen3:4b --minutes 3
python3 simulate.py --model 3 --minutes 3   # model 1/2/3 = slots in config.MODELS

# Web dashboard (browser + SSE; the main UI going forward)
python3 host.py
python3 host.py --model 3 --minutes 5 --port 8000
# then open http://localhost:8000

# A/B model comparison (scripted session across all models)
python3 ab_test.py --minutes 2

# Quick module smoke-tests (no test runner)
python3 -c "from chair import panel; ..."
python3 -c "import host"
```

No pip installs. Ollama must be running locally with models pulled:
```sh
ollama pull gemma3:4b qwen3:4b phi4-mini:latest
```

TTS (piper) requires a separate venv setup under `.venv-tts/` with the voice model at `voices/en_US-ryan-medium.onnx`. Both are gitignored. The system falls back silently to no audio if piper isn't found.

## Architecture

Everything is Python stdlib. No frameworks, no pip dependencies in the core.

```
config.py           all tunables (models, Ollama host, session/phase timing, TTS paths, dashboard port)
chair/
  schema.py         Ollama format= JSON schema: spoken_text, screen_options, massage, button_leds, profile_update, phase
  llm.py            Ollama /api/chat client; streams spoken_text token-by-token via on_text callback
  persona.py        SYSTEM_PROMPT + build_messages(); brevity budget injected from config
  session.py        Session class: phase pacing (Python-authoritative), history, profile/sentiment tracking
  massage.py        massage dict normalization and validation
  panel.py          massage dict → panel state dict (which overlay layers to show, roller position, LED CSS)
  buttons.py        button kind constants + event_for() → event string for the LLM; parse_typed() for terminal
  tts.py            Speaker: parallel synth+playback threads (piper per sentence via proc.communicate)
  states.py         4-state presence machine (IDLE/HEADPHONES_ONLY/SITTING_ONLY/ACTIVE), screen message sets, idle ambient lines
simulate.py         terminal front-end: renders header/body, feeds speaker, hot-swaps model mid-session
host.py             HTTP host: ChairHost (session + state machine + SSE fan-out) + ThreadingHTTPServer
ab_test.py          scripted A/B harness with a fake clock
dashboard/
  index.html        single-page app: left=chair graphic with hotspots, right=interface + controls
  app.js            SSE client, buildChair() compositing, sensor toggles, all event handlers
  style.css         dark theme, sensor-btn / state-pill / gen-pill / hotspot styles
assets/chair/       23 transparent 799×1701 PNGs (all same canvas size; stack with position:absolute)
```

### Data flow

1. `Session.step(event, on_text=cb)` → calls `llm.chat()` which streams `spoken_text` tokens via `cb`
2. `cb` in `host.py` does two things: `broadcast("delta", text=delta)` (SSE to browser) + `speaker.feed(delta)` (sentence-boundary TTS)
3. `Speaker.feed()` accumulates text, calls `_split_sentences()`, queues complete sentences to the synth thread; synth thread calls piper per sentence and passes PCM to the play thread
4. When `step()` returns, `host.py` broadcasts a `"turn"` event with the full structured response

### State machine (host.py ChairHost)

Two boolean sensors (headphones, sitting) drive four states via `states.state_for()`. `POST /sensor {"headphones": bool, "sitting": bool}` triggers `update_sensors()` which handles all transitions:
- IDLE → ACTIVE: injects `session_start` event into LLM queue
- ACTIVE → HEADPHONES_ONLY: sets `_abort` Event, cancels speaker, shows "put back on" screens
- ACTIVE → SITTING_ONLY: injects `person_left` event into LLM queue
- Back → ACTIVE: injects `headphones_back` or `sitting_back` event

The idle loop daemon thread cycles `IDLE_SCREEN_SETS` every 12s, runs breathing airbag animation (4s in/out), and fires ambient TTS lines every 45–90s.

### JSON output contract

Every LLM turn returns structured JSON (enforced via Ollama `format=`): `spoken_text`, `screen_options` (3 strings for the OLED buttons), `massage` dict (technique/intensity/speed/areas/airbags/vibration/led_color), `button_leds` (PWM 0-100 for settings/yes/no), `profile_update` (sentiment + note), `phase`.

### Chair graphic compositing

All 23 sprites are the same 799×1701 canvas size (transparent PNGs). `buildChair()` in `app.js` stacks them as `position:absolute; inset:0` layers. `panel.py` computes which overlay names are active; `renderPanel()` toggles `.hidden` on each `<img>` by name.

### Model hot-swap

`resolve_model("1"|"2"|"3")` maps to `config.MODELS[n-1]`. Works both as `--model 3` CLI arg and mid-session `model 3` command in simulate.py, or via the dashboard settings panel.

## Key config knobs

- `config.MODELS` / `DEFAULT_MODEL` — LLM presets
- `config.MAX_SPOKEN_SENTENCES` / `MAX_SPOKEN_WORDS` — TTS brevity budget (injected into persona prompt)
- `config.SESSION_SECONDS` — experience duration; `PHASE_BOUNDARIES` — phase timing fractions
- `config.TTS_PIPER_BIN` / `TTS_PIPER_MODEL` — piper paths (relative to repo root)
- `config.DASHBOARD_PORT` — default 8001

## Deployment target

Phase 1 (current): laptop simulation. Phase 2: browser dashboard on dev laptop, chair brain on LattePanda (no extra deps). Phase 3: everything on LattePanda as systemd service. Hardware hard-kill (presence sensor bypassing LLM entirely) is required before any real-body testing — not yet built.
