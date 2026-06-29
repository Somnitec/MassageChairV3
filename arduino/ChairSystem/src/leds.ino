int ledRefreshTime = 120;//Hz
int ledBreathMin = 100;
int ledBreathMax = 255;
float breathingTime = 5;


elapsedMicros ledRefreshTimer;
elapsedMicros ledFadeTimer;


void doLeds() {

  if (ledRefreshTimer > 1000000 / ledRefreshTime) {

    if(ledFadeTimer>breathingTime*1000)ledFadeTimer =0;
    ledRefreshTimer = 0;


    CHSV hsv;  //pick random HSV
    CRGB rgb( backlight_color[0], backlight_color[1], backlight_color[2]);
    hsv=rgb2hsv_approximate(rgb);  //convert HSV to RGB
    
    float brightnessNow = ledFadeTimer - int(breathingTime * 1000) / 2; //fmap(sin(millis() / 100), -1, 1, ledBreathMin, ledBreathMax);
    brightnessNow = map(abs(brightnessNow), 0,  (breathingTime * 1000) / 2,ledBreathMin, ledBreathMax);
    //Serial.println(brightnessNow);//debugging

    for (int i = 0; i < NUM_LEDS; i ++) {
      leds[i] = CHSV( hsv.h, hsv.s, brightnessNow );
    }
    ledPos += 0.1;
    FastLED.show();
    //Serial.print('\t');
    //Serial.print(brightnessNow);
    //Serial.print('\t');
    //Serial.println(ledRefreshTimer);//debugging
  }
}
