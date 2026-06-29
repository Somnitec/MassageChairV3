"""Thin Ollama chat client (stdlib only, so it runs unchanged on the LattePanda).

We deliberately avoid the `ollama` python package and `requests` to keep the
deploy box dependency-free. Talks to /api/chat with a JSON schema in `format=`.
"""

import json
import time
import urllib.request
import urllib.error

import config


class LLMError(RuntimeError):
    pass


def chat(model, messages, schema, *, temperature=config.TEMPERATURE,
         timeout=config.REQUEST_TIMEOUT, on_text=None):
    """Send a chat turn, return (parsed_dict, meta).

    `meta` carries latency and token counts so the A/B harness can compare
    speed across models. Raises LLMError on transport or JSON failure.

    If `on_text` is given, the turn is streamed and `on_text(delta)` is called
    with each new chunk of the `spoken_text` value as it is generated (the rest
    of the JSON is still assembled and parsed before returning).
    """
    body = {
        "model": model,
        "messages": messages,
        "stream": on_text is not None,
        "format": schema,
        "options": {"temperature": temperature},
    }
    # qwen3 is a "thinking" model; the reasoning trace wrecks structured output
    # and is slow, so turn it off explicitly.
    if model.startswith("qwen3"):
        body["think"] = False

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{config.OLLAMA_HOST}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )

    t0 = time.time()
    try:
        if on_text is None:
            content, final = _read_whole(req, timeout)
        else:
            content, final = _read_stream(req, timeout, on_text)
    except (urllib.error.URLError, TimeoutError) as e:
        raise LLMError(f"Ollama request failed for {model}: {e}") from e
    latency = time.time() - t0

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise LLMError(f"{model} returned non-JSON: {content[:200]!r}") from e

    meta = {
        "model": model,
        "latency_s": round(latency, 2),
        "eval_count": final.get("eval_count"),
        "prompt_eval_count": final.get("prompt_eval_count"),
    }
    return parsed, meta


def _read_whole(req, timeout):
    """Non-streaming path: one JSON response. Returns (content, final_payload)."""
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    return payload.get("message", {}).get("content", ""), payload


def _read_stream(req, timeout, on_text):
    """Streaming path: NDJSON deltas. Emits spoken_text as it arrives.

    Returns (full_content, final_payload). We accumulate the raw JSON the model
    is emitting, and after each delta re-derive how much of the `spoken_text`
    string is complete so far, pushing only the new tail to `on_text`.
    """
    parts = []
    emitted = 0
    final = {}
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for line in resp:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                parts.append(piece)
                spoken = _spoken_so_far("".join(parts))
                if spoken is not None and len(spoken) > emitted:
                    on_text(spoken[emitted:])
                    emitted = len(spoken)
            if chunk.get("done"):
                final = chunk
    return "".join(parts), final


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\",
            "/": "/", "b": "\b", "f": "\f"}


def _spoken_so_far(buf):
    """Decode the `spoken_text` string value from a partial JSON buffer.

    Returns the text decoded so far (growing as more arrives), or None if the
    value hasn't started yet. Stops cleanly at an incomplete trailing escape so
    we never emit a half-decoded character. Relies on spoken_text being the
    first property in the schema, so it streams before anything else.
    """
    i = buf.find('"spoken_text"')
    if i == -1:
        return None
    j = buf.find(":", i + 13)
    if j == -1:
        return None
    k = buf.find('"', j + 1)        # opening quote of the value
    if k == -1:
        return None

    out = []
    p = k + 1
    n = len(buf)
    while p < n:
        c = buf[p]
        if c == '"':                # closing quote: value is complete
            break
        if c == "\\":
            if p + 1 >= n:          # escape not fully arrived yet
                break
            nxt = buf[p + 1]
            if nxt == "u":
                if p + 6 > n:       # \uXXXX not fully arrived yet
                    break
                try:
                    out.append(chr(int(buf[p + 2:p + 6], 16)))
                except ValueError:
                    pass
                p += 6
                continue
            out.append(_ESCAPES.get(nxt, nxt))
            p += 2
            continue
        out.append(c)
        p += 1
    return "".join(out)
