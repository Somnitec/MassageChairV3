/*
  Inbound serial: fixed-size framing (no Arduino String, no heap growth)
  plus the command dispatch table. Mirrors the ChairSystem MCU's approach
  so the two firmwares stay easy to cross-reference.
*/

#include "serial_io.h"

#include <Arduino.h>
#include <ArduinoJson.h>

#include "app.h"
#include "logging.h"
#include "screen.h"
#include "send_command.h"
#include "state.h"

#define MAX_MESSAGE_LEN 200
static char readBuffer[MAX_MESSAGE_LEN + 1];
static unsigned int readLen = 0;
static bool readingMessage = false;

// JSON tree only (not string content -- deserializeJson gets a mutable
// char* below, so ArduinoJson stores zero-copy pointers into it instead of
// duplicating string data). A fixed StaticJsonDocument means zero heap
// allocation for parsing, which matters on an 8KB-RAM MCU that has to run
// unattended for hours: no fragmentation, no slow leak to chase down.
static StaticJsonDocument<200> doc;

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '{' && !readingMessage) {
      readingMessage = true;
      readLen = 0;
    }
    if (!readingMessage) continue;

    if (readLen >= MAX_MESSAGE_LEN) {
      readLen = 0;
      readingMessage = false;
      printError("overflow");
      continue;
    }
    readBuffer[readLen++] = c;
    if (c == '}') {
      readBuffer[readLen] = '\0';
      receiveMessage(readBuffer);
      readLen = 0;
      readingMessage = false;
    }
  }
}

void printError(const char *error) {
  Serial.print(F("{\n\t\"error\":\""));
  Serial.print(error);
  Serial.println(F("\"\n}"));
  logEvent("ERR", "%s", error);
}

void unknownCommand(const char *message) {
  Serial.print(F("{\n\t\"no useful message\":\""));
  Serial.print(message);
  Serial.println(F("\"\n}"));
  logEvent("WARN", "unrecognized command: %s", message);
}

static bool validateInput(const __FlashStringHelper *command, int expectedArguments) {
  if (expectedArguments == 0) return false;
  for (int i = 0; i < expectedArguments; i++) {
    if (doc[command][i].isNull()) return false;
  }
  return true;
}

// Non-const on purpose: passing a mutable buffer puts ArduinoJson in
// zero-copy mode, so it stores pointers into `message` instead of
// duplicating every string value -- one less allocation-shaped thing to
// worry about on an 8KB-RAM MCU.
void receiveMessage(char *message) {
  DeserializationError error = deserializeJson(doc, message);
  if (error) {
    printError(error.c_str());
    return;
  }

  if (validateInput(F("test"), 1)) {
    const char *text = doc[F("test")][0] | "";
    sendCommand("test", text);
  }

  else if (validateInput(F("customScreenA"), 1)) {
    const char *text = doc[F("customScreenA")][0] | "";
    Effect fx = parseEffect(doc[F("customScreenA")][1] | (const char *)nullptr, EFFECT_WIPE);
    setScreenText(SCREEN_A, text, fx);
    sendCommand("customScreenA", text);
  }
  else if (validateInput(F("customScreenB"), 1)) {
    const char *text = doc[F("customScreenB")][0] | "";
    Effect fx = parseEffect(doc[F("customScreenB")][1] | (const char *)nullptr, EFFECT_WIPE);
    setScreenText(SCREEN_B, text, fx);
    sendCommand("customScreenB", text);
  }
  else if (validateInput(F("customScreenC"), 1)) {
    const char *text = doc[F("customScreenC")][0] | "";
    Effect fx = parseEffect(doc[F("customScreenC")][1] | (const char *)nullptr, EFFECT_WIPE);
    setScreenText(SCREEN_C, text, fx);
    sendCommand("customScreenC", text);
  }

  else if (validateInput(F("screenPulseA"), 1)) {
    bool on = doc[F("screenPulseA")][0];
    setScreenPulse(SCREEN_A, on);
    sendCommand("screenPulseA", on);
  }
  else if (validateInput(F("screenPulseB"), 1)) {
    bool on = doc[F("screenPulseB")][0];
    setScreenPulse(SCREEN_B, on);
    sendCommand("screenPulseB", on);
  }
  else if (validateInput(F("screenPulseC"), 1)) {
    bool on = doc[F("screenPulseC")][0];
    setScreenPulse(SCREEN_C, on);
    sendCommand("screenPulseC", on);
  }

  else if (validateInput(F("clearScreen"), 1)) {
    bool on = doc[F("clearScreen")][0];
    if (on) clearAllScreens();
    sendCommand("clearScreen", on);
  }

  else if (validateInput(F("allLeds"), 1)) {
    LEDSOn = doc[F("allLeds")][0];
    sendCommand("allLeds", LEDSOn);
  }
  else if (validateInput(F("buttonBounceTime"), 1)) {
    buttonBounceTime = doc[F("buttonBounceTime")][0];
    for (int i = 0; i < buttonAmount; i++) {
      debouncedButtons[i].interval(buttonBounceTime);
    }
    sendCommand("buttonBounceTime", (int)buttonBounceTime);
  }
  else if (validateInput(F("buttonFadeTimeSettings"), 1)) {
    buttonFadeTimeSettings = doc[F("buttonFadeTimeSettings")][0];
    sendCommand("buttonFadeTimeSettings", (int)buttonFadeTimeSettings);
  }
  else if (validateInput(F("buttonBrightnessSettings"), 1)) {
    buttonBrightnessSettings = doc[F("buttonBrightnessSettings")][0];
    sendCommand("buttonBrightnessSettings", (int)buttonBrightnessSettings);
  }
  else if (validateInput(F("settingsLed"), 1)) {
    settingsLed = doc[F("settingsLed")][0];
    sendCommand("settingsLed", settingsLed);
  }
  else if (validateInput(F("yesLed"), 1)) {
    yesLed = doc[F("yesLed")][0];
    sendCommand("yesLed", yesLed);
  }
  else if (validateInput(F("noLed"), 1)) {
    noLed = doc[F("noLed")][0];
    sendCommand("noLed", noLed);
  }
  else if (validateInput(F("reset"), 1)) {
    const char *msg = doc[F("reset")][0] | "";
    sendCommand("reset", msg);
    resetBasicState();
  }
  else {
    unknownCommand(message);
    return;
  }
}
