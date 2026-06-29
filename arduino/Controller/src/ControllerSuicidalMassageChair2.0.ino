/*
  OUTPUT
  {
  "controllerCommand":"..."
  "controllerValue':"..." 0..1-5
  }

  InputParse
  buttonKill, => bool
  buttonCustomA, => bool
  buttonCustomB, => bool
  buttonCustomC, => bool
  buttonSettings,  => bool
  buttonThumbUpUp,
  buttonThumbUpDown,
  buttonYes,
  buttonNo,
  buttonRepeat,
  buttonHorn,
  buttonLanguage,
  buttonSlider => int 1..5

  InfoParse
  customScreenA => string
  customScreenB => string
  customScreenC => string
  clearScreen = bool
  buttonBounceTime = int in MS
  buttonFadeTimeSettings = int in MS
  buttonBrightnessSettings = 0 .. 255
  allLeds = bool
  settingsLed = bool
  yesLed  = bool
  noLed = bool
  reset

  For example
  {
    "controllerCommand": "buttonKill",
    "controllerValue": "1"
  }


*/


#include <Bounce2.h>
#include <U8g2lib.h>
#include <elapsedMillis.h>
#include <ArduinoJson.h>

#define buttonCustomA 0
#define buttonCustomB 1
#define buttonCustomC 2
#define buttonLanguage 3
#define LEDSettings 4
#define buttonSettings 5
#define buttonThumbUp 6
#define buttonRepeat 7
#define buttonNo 11
#define LEDNo 10
#define LEDYes 9
#define buttonYes 8
#define buttonHorn 14
#define buttonKill 15
#define sliderNumbers 24
#define buttonThumbDown 25
#define volume0 21
#define volume1 20
#define sda0 18
#define scl0 19
#define sda1 23
#define scl1 22

//########SETTINGS
int buttonBounceTime = 100;
int buttonFadeTimeSettings = 100;
int buttonBrightnessSettings = 255;
//######


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
String buttonsString[] = {"buttonKill",
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
byte buttonAmount = sizeof(buttons) / sizeof(buttons[0]);
byte  LEDs[] = {LEDSettings, LEDNo, LEDYes, 13};
byte ledAmount = sizeof(buttons) / sizeof(buttons[0]);
Bounce *debouncedButtons = new Bounce[buttonAmount];
byte lastSliderValue = 0;

boolean LEDSOn = true;

bool    settingsLed = true;
bool   yesLed  = true;
bool   noLed = true;


StaticJsonDocument<100> doc;


U8G2_SH1106_128X64_NONAME_1_SW_I2C OLED0(U8G2_R0, /* clock=*/ 16, /* data=*/ 17, /* reset=*/ U8X8_PIN_NONE);   // All Boards without Reset of the Display
U8G2_SH1106_128X64_NONAME_1_SW_I2C OLED1(U8G2_R0, /* clock=*/ 22, /* data=*/ 23, /* reset=*/ U8X8_PIN_NONE);   // All Boards without Reset of the Display
U8G2_SH1106_128X64_NONAME_1_SW_I2C OLED2(U8G2_R0, /* clock=*/ 19, /* data=*/ 18, /* reset=*/ U8X8_PIN_NONE);   // All Boards without Reset of the Display

#define STARTSPACE 11
#define LINESPACE 16
#define CHARACTERWIDTH 13
#define LINESAMOUNT 5


char charBuf1[CHARACTERWIDTH+1];
char charBuf2[CHARACTERWIDTH+1];
char charBuf3[CHARACTERWIDTH+1];
char charBuf4[CHARACTERWIDTH+1];
char charBuf5[CHARACTERWIDTH+1];
char szTemp[CHARACTERWIDTH+1];

void setup() {
  Serial.begin(115200);

  for (int i = 0; i < ledAmount; i++)
    pinMode(LEDs[i], OUTPUT);

  for (int i = 0; i < buttonAmount; i++)
  {
    debouncedButtons[i].attach(buttons[i], INPUT_PULLUP);
    debouncedButtons[i].interval(buttonBounceTime);
  }

  pinMode(sliderNumbers, INPUT);

  OLED0.begin();
  OLED0.setFont(u8g2_font_courB12_tr   );
  
  OLED1.begin();
  OLED1.setFont(u8g2_font_courB12_tr   );
  
  OLED2.begin();
  OLED2.setFont(u8g2_font_courB12_tr   );

  writeToScreen(0, F("...." ));
  writeToScreen(1, F(".....")  );
  writeToScreen(2, F("...") );

  pinMode(13, OUTPUT);
  digitalWrite(13, HIGH);

  sendCommand("started", String(millis()));

sendCommand("buttonLanguage", digitalRead(buttonLanguage));
}

void resetBasicState() {
  LEDSOn = false;
  settingsLed = true;
  yesLed  = true;
  noLed = true;
  writeToScreen(4, F("nope"));
}

void loop() {
  readSerial();
  readButtons();
  ledStates();
}
