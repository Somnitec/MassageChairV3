#pragma once

// Outbound serial helpers: {"controllerCommand":..., "controllerValue":...}
// acks/events. All implemented with F() flash-string literals and
// char*/numeric args -- no Arduino String concatenation anywhere, so
// nothing on this path can fragment the 8KB heap over a multi-hour
// unattended run.
void sendCommand(const char *command, const char *value);
void sendCommand(const char *command, bool value);
void sendCommand(const char *command, int value);
void sendCommand(const char *command, long value);
