#pragma once

// Human-only debug log. Every line starts with "# " and never contains '{'
// or '}', so it reads cleanly in a raw serial monitor and can never be
// mistaken for a protocol object by the host's brace-matching parser
// (chair/hardware.py ChairLink._extract_objects surfaces these separately
// as {"_log": "..."} instead of trying to JSON-parse them).
void logEvent(const char *tag, const char *fmt, ...);
