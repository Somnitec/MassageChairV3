#include "leds.h"

#include <Arduino.h>

#include "pins.h"
#include "state.h"

void ledStates() {
  if (!LEDSOn) {
    for (int i = 0; i < ledAmount; i++)
      analogWrite(LEDs[i], 0);
    return;
  }

  analogWrite(LEDSettings, (digitalRead(buttonSettings) && settingsLed) ? buttonBrightnessSettings : 0);
  analogWrite(LEDYes, (digitalRead(buttonYes) && yesLed) ? buttonBrightnessSettings : 0);
  analogWrite(LEDNo, (digitalRead(buttonNo) && noLed) ? buttonBrightnessSettings : 0);
}
