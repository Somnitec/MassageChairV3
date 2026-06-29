elapsedMillis sliderTimer;
bool sliderMoved = false;

void readButtons() {
  for (int i = 0; i < buttonAmount; i++)//fixes a bug where customA and B buttons stopped working after screen reset
  {
    pinMode(buttons[i], INPUT_PULLUP);
  }
  
  for (int i = 0; i < buttonAmount; i++)
  {
    // Update the Bounce instance :
    debouncedButtons[i].update();
    if (i == 0)//if kill is pressed, it's NC so different behavious from the others
    { 
      if (debouncedButtons[i].rose())
      {
        //Serial.print(buttonsString[i]);
        //Serial.println();
        sendCommand( buttonsString[i], true);
      }
    }
    else if (i == 4)
    { //if language switch if flipped
      if (debouncedButtons[i].rose() || debouncedButtons[i].fell())
      {
        //Serial.print(buttonsString[i]);
        //Serial.print(" = ");
        //Serial.print(debouncedButtons[i].read());
        //Serial.println();
        sendCommand( buttonsString[i], debouncedButtons[i].read());

      }
    }
    else if (debouncedButtons[i].fell())
    {
      //Serial.print(buttonsString[i]);
      //Serial.println();
      sendCommand( buttonsString[i], String(true));
      //cmdMessenger.sendCmd(kSendInput, "triggered");
    }
  }


  int newSliderValue = sliderConversion(analogRead(sliderNumbers));
  if (lastSliderValue != newSliderValue)
  {
    sliderMoved = true;
    sliderTimer = 0;
    lastSliderValue = newSliderValue;
    //Serial.print("sliderNumbers = ");
    //Serial.print(newSliderValue);
    //Serial.println();
  }
  if (sliderTimer > buttonBounceTime && sliderMoved) {
    sliderMoved = false;
    sendCommand( "buttonSlider", newSliderValue);
  }

}

int sliderConversion(int input)
{
  //1 730
  //    695
  //2 660
  //    570
  //3 480
  //    407
  //4 335
  //    293
  //5 250
  if (input > 695)
    return 1;
  else if (input > 570)
    return 2;
  else if (input > 407)
    return 3;
  else if (input > 293)
    return 4;
  else
    return 5;
}
