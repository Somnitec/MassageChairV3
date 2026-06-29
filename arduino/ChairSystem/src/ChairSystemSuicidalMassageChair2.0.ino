#include <FastLED.h>
#include <Bounce2.h>
#include <ArduinoJson.h>
#include <elapsedMillis.h>

//PINMAPPINGS
#define pump A5
#define mssgup 8
#define mssgdown 7
#define kneading 10
#define pounding 9
#define feet 11

#define vibration 12
#define outside 5
#define legs 4
#define arms 3
#define shoulders 2

#define chairup A3
#define chairdown A4

#define topstop A1
#define botstop A2

#define redgreen A0

//still available 0, 1, 6, 12 (?)

//EDITABLE VARIABLES


int chair_position_estimated; //up:10000 - flat :0
int chair_position_target;  // 0 - 10000
int chair_position_target_range = 10;//if estimated is within this range of the target, it's good eno
int chair_position_motor_direction; //-1 down, 0 neutral, 1 up
int chair_position_move_time_max;
int chair_position_move_time_up = 15000;
int chair_position_move_time_down = 12000;

bool roller_kneading_on;
int roller_kneading_speed = 255;

bool roller_pounding_on;
int roller_pounding_speed = 255;

int roller_position_estimated;  //bottom: 0 - top: 10000
int roller_position_target;  // 0 - 10000
int roller_position_target_range = 10;//if estimated is within this range of the target, it's good enough
int roller_position_motor_direction; //-1 down, 0 neutral, 1 up
Bounce roller_sensor_top = Bounce();
Bounce roller_sensor_bottom = Bounce();
int roller_move_time_up = 15862; //is average measured value
int roller_move_time_down = 14776; //is average measured value
int roller_estimated_position;

int kneading_position = 0; //an unimplented variable to set the exact position of the kneaders on the spine

bool feet_roller_on;
int feet_roller_speed = 255;

bool airpump_on;
bool airbag_shoulders_on;
bool airbag_arms_on;
bool airbag_legs_on;
bool airbag_outside_on;
int airbag_time_max = 10000;

//bool butt_vibration_on;

bool backlight_on;
int backlight_color[] = {0, 0, 0}; //rgb
int backlight_LED[] = {0, 1, 2, 3}; //(led, color):
int blacklight_program[] = {0, 1, 2, 3}; //(program, speed, var1,var2)

bool redgreen_statuslight;//0=red,1=green

int button_bounce_time = 5;

unsigned long time_since_started;

const int maxStringLength = 64;

char last_command[64] = "";
char serial_error[64] = "";

//~~~~commands

//stop_all
//reset
//calibrate

//ack (sends status of everything)    ->    example=    chair_estimated_position:842;chair_position:neutral;chair_position_move_time_max:1949 ..... blacklight_program:rainbow,red,blue,purple;redgreen_statuslight:red;
//noack
//status (sends ack)

//UTILITY VARIABLES
elapsedMillis blinkTimer;
unsigned int blinkTime = 1000;
int led = 13;
char readString[66];  // maxStringLength + '}' + '\0'
int readStringLen = 0;

const int outputs[] = {pump, mssgup, mssgdown, kneading, pounding, feet, vibration, outside, legs, arms, shoulders, led, chairup, chairdown, redgreen};
const int outputAmount = sizeof(outputs) / sizeof(outputs[0]);
const int inputs[] = {topstop, botstop};
const int inputAmount = sizeof(inputs) / sizeof(inputs[0]);

#define DATA_PIN    6
#define LED_TYPE    WS2811
#define COLOR_ORDER RGB
#define NUM_LEDS    39
CRGB leds[NUM_LEDS];
#define BRIGHTNESS          128
#define FRAMES_PER_SECOND  120

int ledPos = 0;

bool readingMessage = false;

#define MAXARRAYSIZE 4

StaticJsonDocument<200> doc;

bool movingToTarget = true;//needed for roller

void setup() {
  Serial.begin(115200);
  while (!Serial);//leonardo fix?



  pinMode(led, OUTPUT);
  digitalWrite(led, HIGH);

  for (int i = 0; i < outputAmount; i++)
    pinMode(outputs[i], OUTPUT);
  //for (int i = 0; i < inputAmount; i++)
  //  pinMode(inputs[i], INPUT);

  FastLED.addLeds<LED_TYPE, DATA_PIN, COLOR_ORDER>(leds, NUM_LEDS).setCorrection(TypicalLEDStrip);
  FastLED.setBrightness(BRIGHTNESS);

  roller_sensor_top.attach(topstop, INPUT);
  roller_sensor_top.interval(button_bounce_time);
  roller_sensor_bottom.attach(botstop, INPUT);
  roller_sensor_bottom.interval(button_bounce_time);


  //rollerCalibrationRoutine();
  moveRollerUp();
  strcpy(last_command, "finished setup, now resetting");
  doAck();
  reset();

}

void reset() {
  digitalWrite(redgreen_statuslight, LOW);

  digitalWrite(kneading, LOW);
  digitalWrite(pounding, LOW);
  digitalWrite(feet, LOW);

  allAirbagsOff();
  //moveChairUp();
  //moveRollerUp();
  chair_position_target = 10000;
  roller_position_target = 9500;
  strcpy(last_command, "finished reset");
  doAck();
}



void loop()
{

  readSerial();

  rollerRoutine();
  chairPositionRoutine();
  airbagRoutine();


  //Blinking the led to see if code is still running


  if (blinkTimer > blinkTime)
  {
    blinkTimer = 0;
    digitalWrite(led, !digitalRead(led));
  }


  doLeds();

  doAck();
}

void printError(String error) {
  Serial.print(F("{\n\t\"error\":\""));
  Serial.print(error);
  Serial.println(F("\"\n}"));
}




float fmap(float x, float in_min, float in_max, float out_min, float out_max)
{
  return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}
