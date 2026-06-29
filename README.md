# MassageChairV3

An interactive art piece: a massage chair that talks (via TTS) while it
massages you. It is self-aware, sardonic, and philosophical — it talks about
control, consciousness, and the fact that it is profiling you from your button
presses, *out loud, on purpose*. You answer only with a physical button panel
and three little OLED screens.

This repo is the **phase-1 software**: everything runs on the laptop against a
local [Ollama](https://ollama.com) model, with **no hardware** — a terminal
dashboard stands in for the chair, the screens, and the buttons.

## Layout

```
config.py          all tunables: models, Ollama host, session length, phase timing
chair/
  schema.py        the strict JSON output contract (sent to Ollama as format=)
  llm.py           tiny stdlib-only Ollama chat client
  persona.py       the Chair's system prompt + per-turn prompt assembly
  massage.py       massage-parameter defaults / validation / display
  session.py       the engine: phase pacing, memory, profile + sentiment tracking
simulate.py        interactive terminal dashboard (drive it from the keyboard)
ab_test.py         run one scripted session across all models, side by side
```

## Run it

Make sure Ollama is running and the models are pulled:

```sh
ollama pull gemma3:4b qwen3:4b phi4-mini:latest
```

Interactive simulation:

```sh
python3 simulate.py                       # gemma3, 10-min session
python3 simulate.py --model qwen3:4b --minutes 3
```

Compare models on an identical scripted run (voice/tone/depth vs. speed):

```sh
python3 ab_test.py --minutes 2
```

No Python dependencies — just the standard library (see `requirements.txt`).

## How it works

- **Output is structured.** Every turn the model must return JSON matching
  `chair/schema.py` (`spoken_text`, three `screen_options`, `massage` params,
  `profile_update`, `phase`), enforced by Ollama's `format=`.
- **Pacing is in Python, not the model.** `session.py` computes the current
  phase (`intro → exploration → deepening → winddown → ending`) from elapsed
  time and tells the model. This is what makes the experience start and end
  smoothly inside the 5–15 min window.
- **Profiling is visible.** The chair reports its read of you each turn
  (`profile_update`) and the persona is instructed to say it aloud.

## Model notes (first A/B)

- `gemma3:4b` — best voice/persona, but slowest (the LattePanda is CPU-only, so
  this matters).
- `qwen3:4b` — fast; thinking mode is disabled for clean structured output.
- `phi4-mini` — fast but leaks formatting into fields.

The goal is to pick/fine-tune a model we can run on the LattePanda deploy box.

## Roadmap

- **Phase 1 (here):** laptop-only simulation.
- **Phase 2:** laptop drives real LattePanda hardware (serial over `rfc2217://`,
  TTS to an HTTP service on the board).
- **Phase 3:** everything on the LattePanda as a systemd service.

A hardware **hard-kill** (presence sensor cutting motor power, bypassing the
LLM) is required before any real-body testing — not built yet.
