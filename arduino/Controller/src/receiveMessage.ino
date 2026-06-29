bool readingMessage = false;
String readString;
unsigned int maxStringLength = 127;
String last_command = "";

void readSerial() {
  if (Serial.available())  {
    char c = Serial.read();  //gets one byte from serial buffer
    if (c == '{' && !readingMessage)readingMessage = true;
    if (readingMessage) {
      if (c == '}') {  //looks for end of data packet marker
        readString += c;
        receiveMessage(readString); //prints string to serial port out
        //do stuff with captured readString
        readString = ""; //clears variable for new input
        readingMessage = false;
      }
      else {
        readString += c; //makes the string readString
        if (readString.length() > maxStringLength) {//preventing buffer overflow
          readString = "";
          readingMessage = false;
          printError("overflow");
        }
      }

    }
  }
}

void printError(String error) {
  Serial.print(F("{\n\t\"error\":\""));
  Serial.print(error);
  Serial.println(F("\"\n}"));
}


bool validateInput(String command, int expectedArguments) {
  if ( expectedArguments == 0) return false;//always get one argument (for now)
  else {
    for (int i = 0; i < expectedArguments; i++) {
      String item = doc[command][i];
      if (item.equals("null"))return false;
    }
  }
  last_command = command;
  return true;
}

void receiveMessage( String message) {
  last_command = "";

  DeserializationError error = deserializeJson(doc, message);
  // Test if parsing succeeds.
  if (error) {
    printError(error.c_str());
    return;
  }
  if (validateInput(F("test"), 1)) {
    String message =  doc[F("test")][0];
    sendCommand("test", message);
  }
  else if (validateInput(F("customScreenA"), 1)) {
    String message =  doc[F("customScreenA")][0];
    writeToScreen(0, message);
    sendCommand("customScreenA", message);
  }
  else if (validateInput(F("customScreenB"), 1)) {
    String message =  doc[F("customScreenB")][0];
    writeToScreen(1, message);
    sendCommand("customScreenB", message);
  }
  else if (validateInput(F("customScreenC"), 1)) {
    String message =  doc[F("customScreenC")][0];
    writeToScreen(2, message);
    sendCommand("customScreenC", message);
  }
  else if (validateInput(F("clearScreen"), 1)) {
    bool message =  doc[F("clearScreen")][0];
    if (message) writeToScreen(4, String(message));
    sendCommand("clearScreen", message);
  }
  else if (validateInput(F("allLeds"), 1)) {
    LEDSOn  =  doc[F("allLeds")][0];
    sendCommand("allLeds", LEDSOn);
  }
  else if (validateInput(F("buttonBounceTime"), 1)) {
    buttonBounceTime   =  doc[F("buttonBounceTime")][0];
    for (int i = 0; i < buttonAmount; i++)
    {
      debouncedButtons[i].interval(buttonBounceTime);
    }
    sendCommand("buttonBounceTime", buttonBounceTime );
  }
  else if (validateInput(F("buttonFadeTimeSettings"), 1)) {
    buttonFadeTimeSettings  =  doc[F("buttonFadeTimeSettings")][0];
    sendCommand("buttonFadeTimeSettings", buttonFadeTimeSettings );
  }
  else if (validateInput(F("buttonBrightnessSettings"), 1)) {
    buttonBrightnessSettings   =  doc[F("buttonBrightnessSettings")][0];
    sendCommand("buttonBrightnessSettings", buttonBrightnessSettings );
  }
  else if (validateInput(F("settingsLed "), 1)) {
    settingsLed   =  doc[F("settingsLed ")][0];
    sendCommand("settingsLed ", settingsLed  );
  }
  else if (validateInput(F("yesLed  "), 1)) {
    yesLed    =  doc[F("yesLed  ")][0];
    sendCommand("yesLed  ", yesLed   );
  }
  else if (validateInput(F("noLed "), 1)) {
    noLed    =  doc[F("noLed ")][0];
    sendCommand("noLed ", noLed  );
  }
  else if (validateInput(F("reset"), 1)) {
    String message    =  doc[F("reset")][0];

    sendCommand("reset", message  );
    resetBasicState();
  }
  /*

    buttonBounceTime = int in MS
    buttonFadeTimeSettings = int in MS
    buttonBrightnessSettings = 0 .. 255
     = bool
    settingsLed = bool
    yesLed  = bool
    noLed = bool
    reset
  */
}
