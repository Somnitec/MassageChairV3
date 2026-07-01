#pragma once

// Shared runtime settings: mutated by the serial protocol (serial_io.cpp)
// and read by buttons.cpp / leds.cpp / main.cpp. Defined in main.cpp.

#include <Arduino.h>
#include <Bounce2.h>

extern unsigned int buttonBounceTime;
extern unsigned int buttonFadeTimeSettings;
extern uint8_t buttonBrightnessSettings;

extern bool LEDSOn;
extern bool settingsLed;
extern bool yesLed;
extern bool noLed;

extern int buttons[];
extern const char *buttonsString[];
extern const byte buttonAmount;
extern byte LEDs[];
extern const byte ledAmount;
extern Bounce *debouncedButtons;
