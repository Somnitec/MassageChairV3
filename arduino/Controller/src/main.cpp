/*
  Controller MCU firmware -- buttons + 3 status OLEDs for the massage chair rig.
  Teensy LC (8KB RAM), stdlib Arduino only (Bounce2, U8g2, ArduinoJson, elapsedMillis).

  ------------------------------------------------------------------------
  Wire protocol (matches chair/hardware.py: ChairLink)
  ------------------------------------------------------------------------
  MCU -> host, one compact object per event:
    {"controllerCommand":"<name>","controllerValue":"<value>"}
  Every button press AND release (value 1/0), the slider, and an ack for
  each applied host command are reported this way.

  MCU -> host, human-only debug lines: start with "# ", never contain '{'
  or '}', so a raw serial monitor is readable and the host's brace-matching
  parser (chair/hardware.py ChairLink._extract_objects) can never mistake
  them for protocol objects -- it surfaces them separately as {"_log": ...}.

  Host -> MCU, one JSON object per packet, every value wrapped in an array:
    {"customScreenA":["some text"]}              draw text, default "wipe" transition
    {"customScreenA":["some text","instant"]}     effect: instant|wipe|flash|typewriter|marquee
    {"customScreenB":[...]}  {"customScreenC":[...]}   same, other two OLEDs
    {"screenPulseA":[true]}  {"screenPulseB":[...]}  {"screenPulseC":[...]}
                                                   continuous "breathing" brightness pulse
                                                   (e.g. a "thinking" indicator); false stops it
    {"clearScreen":[true]}                        blank all three OLEDs
    {"allLeds":[bool]}
    {"buttonBounceTime":[ms]}
    {"buttonFadeTimeSettings":[ms]}
    {"buttonBrightnessSettings":[0..255]}
    {"settingsLed":[bool]}  {"yesLed":[bool]}  {"noLed":[bool]}
    {"reset":[1]}

  Text that doesn't fit even at the smallest font gets truncated with a
  trailing "..." rather than clipped mid-glyph -- callers never have to
  think about length. Effect "marquee" scrolls instead, if ever wanted.
*/

#include <Arduino.h>
#include <Bounce2.h>

#include "app.h"
#include "buttons.h"
#include "leds.h"
#include "logging.h"
#include "pins.h"
#include "screen.h"
#include "send_command.h"
#include "serial_io.h"
#include "state.h"

// No hardware watchdog: the Teensy LC (Kinetis KL26) only has the simple
// SIM_COPC "COP" watchdog, not the full WDOG peripheral used on Teensy 3.x
// -- and Teensyduino's own startup code already disables it (SIM_COPC = 0
// in mk20dx128.c) before setup() ever runs. An earlier version of this file
// re-enabled a K-series-style WDOG at the wrong address for this chip,
// which hard-faulted before Serial.begin() ran on every boot. Not worth
// re-attempting with the real (coarse, ~1s max) COP module for what this
// firmware needs; if a watchdog is wanted later, implement it against
// SIM_COPC/SIM_SRVCOP specifically, and bring the board up on a serial
// monitor first to confirm it survives before trusting it unattended.

// ------------------------------------------------------------- settings --
unsigned int buttonBounceTime = 25; // ms; override live via {"buttonBounceTime":[ms]}
unsigned int buttonFadeTimeSettings = 100;
uint8_t buttonBrightnessSettings = 255;

int buttons[] = {
  buttonKill,
  buttonCustomA,
  buttonCustomB,
  buttonCustomC,
  buttonLanguage,
  buttonSettings,
  buttonThumbUp,
  buttonYes,
  buttonNo,
  buttonRepeat,
  buttonThumbDown,
  buttonHorn,
};
const char *buttonsString[] = {"buttonKill",
                                "buttonCustomA",
                                "buttonCustomB",
                                "buttonCustomC",
                                "buttonLanguage",
                                "buttonSettings",
                                "buttonThumbUp",
                                "buttonYes",
                                "buttonNo",
                                "buttonRepeat",
                                "buttonThumbDown",
                                "buttonHorn"
                               };
const byte buttonAmount = sizeof(buttons) / sizeof(buttons[0]);
byte LEDs[] = {LEDSettings, LEDNo, LEDYes, 13};
const byte ledAmount = sizeof(LEDs) / sizeof(LEDs[0]);
Bounce *debouncedButtons = new Bounce[buttonAmount];

bool LEDSOn = true;
bool settingsLed = true;
bool yesLed = true;
bool noLed = true;

void setup() {
  Serial.begin(115200);
  logEvent("BOOT", "controller firmware starting, build " __DATE__ " " __TIME__);

  for (int i = 0; i < ledAmount; i++)
    pinMode(LEDs[i], OUTPUT);

  for (int i = 0; i < buttonAmount; i++) {
    debouncedButtons[i].attach(buttons[i], INPUT_PULLUP);
    debouncedButtons[i].interval(buttonBounceTime);
  }

  pinMode(sliderNumbers, INPUT);

  logEvent("BOOT", "initializing screens...");
  initScreens();

  pinMode(13, OUTPUT);
  digitalWrite(13, HIGH);

  logEvent("BOOT", "controller firmware up");
  sendCommand("started", (long)millis());
  sendCommand("buttonLanguage", digitalRead(buttonLanguage));
}

void resetBasicState() {
  LEDSOn = false;
  settingsLed = true;
  yesLed = true;
  noLed = true;
  clearAllScreens();
  logEvent("RESET", "basic state reset");
}

void loop() {
  readSerial();
  readButtons();
  ledStates();
  updateScreens();
}
