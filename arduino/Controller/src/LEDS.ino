void ledStates() {
 
    if (digitalRead(buttonSettings) && LEDSOn&&settingsLed)
      analogWrite(LEDSettings, buttonBrightnessSettings);
    else
      analogWrite(LEDSettings, 0);

    if (digitalRead(buttonYes)&& LEDSOn&&yesLed)
      analogWrite(LEDYes, buttonBrightnessSettings);
    else
      analogWrite(LEDYes, 0);

    if (digitalRead(buttonNo)&& LEDSOn&&noLed)
      analogWrite(LEDNo, buttonBrightnessSettings);
    else
      analogWrite(LEDNo, 0);
  
  if (!LEDSOn) {
    for (int i = 0; i < ledAmount; i++)
      analogWrite(LEDs[i], 0);
  }
}
