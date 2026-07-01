#include "buttons.h"

#include <Arduino.h>
#include <Bounce2.h>
#include <elapsedMillis.h>

#include "logging.h"
#include "pins.h"
#include "send_command.h"
#include "state.h"

// Debounced like the digital buttons, but by *value* rather than edge: a
// reading only counts once it has held steady for buttonBounceTime -- ADC
// noise flickering across a band boundary just keeps resetting the timer
// instead of re-arming a send, so it can't spam the same settled value.
static int sliderPendingValue = -1; // -1: no reading seen yet
static int sliderSentValue = -1;
static elapsedMillis sliderStableTimer;

static int sliderConversion(int input) {
  // potentiometer ADC bands, empirically measured; 1 (min) .. 5 (max)
  if (input > 695) return 1;
  else if (input > 570) return 2;
  else if (input > 407) return 3;
  else if (input > 293) return 4;
  else return 5;
}

void readButtons() {
  for (int i = 0; i < buttonAmount; i++) // re-attach: works around a bug where customA/B stop responding after a screen reset
    pinMode(buttons[i], INPUT_PULLUP);

  for (int i = 0; i < buttonAmount; i++) {
    debouncedButtons[i].update();
    if (i == 0) { // kill switch is normally-closed, so its edges are inverted vs the rest
      if (debouncedButtons[i].rose()) {
        sendCommand(buttonsString[i], true);
        logEvent("BTN", "%s pressed", buttonsString[i]);
      } else if (debouncedButtons[i].fell()) {
        sendCommand(buttonsString[i], false);
        logEvent("BTN", "%s released", buttonsString[i]);
      }
    } else if (i == 4) { // language toggle: a switch, so both edges are reported
      if (debouncedButtons[i].rose() || debouncedButtons[i].fell()) {
        int value = debouncedButtons[i].read();
        sendCommand(buttonsString[i], value);
        logEvent("BTN", "%s = %d", buttonsString[i], value);
      }
    } else if (debouncedButtons[i].fell()) {
      sendCommand(buttonsString[i], true);
      logEvent("BTN", "%s pressed", buttonsString[i]);
    } else if (debouncedButtons[i].rose()) {
      sendCommand(buttonsString[i], false);
      logEvent("BTN", "%s released", buttonsString[i]);
    }
  }

  int reading = sliderConversion(analogRead(sliderNumbers));
  if (reading != sliderPendingValue) {
    sliderPendingValue = reading;
    sliderStableTimer = 0;
  }
  if (sliderStableTimer > buttonBounceTime && sliderPendingValue != sliderSentValue) {
    sliderSentValue = sliderPendingValue;
    sendCommand("buttonSlider", sliderSentValue);
    logEvent("BTN", "buttonSlider = %d", sliderSentValue);
  }
}
