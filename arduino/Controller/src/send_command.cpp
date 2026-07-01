#include "send_command.h"

#include <Arduino.h>

// Writes `value` inside the surrounding JSON string quotes, escaping the
// two characters that would otherwise break the enclosing JSON. Screen
// text ultimately comes from an LLM and can contain quotes/backslashes.
static void writeJsonEscaped(const char *value) {
  for (const char *p = value; *p; p++) {
    if (*p == '"' || *p == '\\') Serial.write('\\');
    if ((unsigned char)*p < 0x20) continue; // drop stray control chars
    Serial.write(*p);
  }
}

static void sendMessage(const char *command, const char *value) {
  Serial.print(F("{\n\t\"controllerCommand\":\""));
  Serial.print(command);
  Serial.print(F("\",\n\t\"controllerValue\":\""));
  writeJsonEscaped(value);
  Serial.println(F("\"\n}"));
}

void sendCommand(const char *command, const char *value) {
  sendMessage(command, value);
}

void sendCommand(const char *command, bool value) {
  sendMessage(command, value ? "1" : "0");
}

void sendCommand(const char *command, int value) {
  char num[12];
  snprintf(num, sizeof(num), "%d", value);
  sendMessage(command, num);
}

void sendCommand(const char *command, long value) {
  char num[16];
  snprintf(num, sizeof(num), "%ld", value);
  sendMessage(command, num);
}
