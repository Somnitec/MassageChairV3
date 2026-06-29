void readSerial() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == '{' && !readingMessage) {
      readingMessage = true;
      readStringLen = 0;
    }
    if (readingMessage) {
      if (c == '}') {
        readString[readStringLen++] = c;
        readString[readStringLen] = '\0';
        receiveMessage(readString);
        readStringLen = 0;
        readingMessage = false;
      } else {
        readString[readStringLen++] = c;
        if (readStringLen >= maxStringLength) {
          readStringLen = 0;
          readingMessage = false;
          printError("overflow");
        }
      }
    }
  }
}



void receiveMessage(const char* message) {
  last_command[0] = '\0';

  DeserializationError error = deserializeJson(doc, message);
  if (error) {
    printError(error.c_str());
    return;
  }

  if (validateInput(F("blinkTime"), 1)) {
    blinkTime = doc[F("blinkTime")][0];
  }
  else if (validateInput(F("chair_position_estimated"), 1)) {
    //just ack
  }
  else if (validateInput(F("chair_position_target"), 1)) {
    chair_position_target = doc[F("chair_position_target")][0];
    chairNewInput = true;
  }
  else if (validateInput(F("chair_position_target_range"), 1)) {
    roller_position_target_range = doc[F("chair_position_target_range")][0];
  }
  else if (validateInput(F("chair_position_motor_direction"), 1)) {
    chair_position_motor_direction = doc[F("chair_position_motor_direction")][0];
  }
  else if (validateInput(F("chair_position_move_time_max"), 1)) {
    chair_position_move_time_max = doc[F("chair_position_move_time_max")][0];
  }
  else if (validateInput(F("chair_position_move_time_up"), 1)) {
    chair_position_move_time_up = doc[F("chair_position_move_time_up")][0];
  }
  else if (validateInput(F("chair_position_move_time_down"), 1)) {
    chair_position_move_time_down = doc[F("chair_position_move_time_down")][0];
  }

  else if (validateInput(F("roller_kneading_on"), 1)) {
    roller_kneading_on = doc[F("roller_kneading_on")][0];
    analogWrite(kneading, roller_kneading_on * roller_kneading_speed);
  }
  else if (validateInput(F("roller_kneading_speed"), 1)) {
    roller_kneading_speed = doc[F("roller_kneading_speed")][0];
    analogWrite(kneading, roller_kneading_on * roller_kneading_speed);
  }

  else if (validateInput(F("roller_pounding_on"), 1)) {
    roller_pounding_on = doc[F("roller_pounding_on")][0];
    analogWrite(pounding, roller_pounding_on * roller_pounding_speed);
  }
  else if (validateInput(F("roller_pounding_speed"), 1)) {
    roller_pounding_speed = doc[F("roller_pounding_speed")][0];
    analogWrite(pounding, roller_pounding_on * roller_pounding_speed);
  }

  else if (validateInput(F("roller_position_estimated"), 1)) {
    //only ack
  }
  else if (validateInput(F("roller_position_target"), 1)) {
    roller_position_target = doc[F("roller_position_target")][0];
    movingToTarget = true;
  }
  else if (validateInput(F("roller_position_target_range"), 1)) {
    roller_position_target_range = doc[F("roller_position_target_range")][0];
  }
  else if (validateInput(F("roller_position_motor_direction"), 1)) {
    roller_position_motor_direction = doc[F("roller_position_motor_direction")][0];
    movingToTarget = false;
  }
  else if (validateInput(F("roller_sensor_top"), 1)) {
    //cannot be set
  }
  else if (validateInput(F("roller_sensor_bottom"), 1)) {
    //cannot be set
  }
  else if (validateInput(F("roller_move_time_up"), 1)) {
    roller_move_time_up = doc[F("roller_move_time_up")][0];
  }
  else if (validateInput(F("roller_move_time_down"), 1)) {
    roller_move_time_down = doc[F("roller_move_time_down")][0];
  }
  else if (validateInput(F("kneading_position"), 1)) {
    kneading_position = doc[F("kneading_position")][0];
  }

  else if (validateInput(F("feet_roller_on"), 1)) {
    feet_roller_on = doc[F("feet_roller_on")][0];
    analogWrite(feet, feet_roller_on * feet_roller_speed);
  }
  else if (validateInput(F("feet_roller_speed"), 1)) {
    feet_roller_speed = doc[F("feet_roller_speed")][0];
    analogWrite(feet, feet_roller_on * feet_roller_speed);
  }

  else if (validateInput(F("airpump_on"), 1)) {
    airpump_on = doc[F("airpump_on")][0];
  }
  else if (validateInput(F("airbag_shoulders_on"), 1)) {
    airbag_shoulders_on = doc[F("airbag_shoulders_on")][0];
    shoulderTimer = 0;
  }
  else if (validateInput(F("airbag_arms_on"), 1)) {
    airbag_arms_on = doc[F("airbag_arms_on")][0];
    armsTimer = 0;
  }
  else if (validateInput(F("airbag_legs_on"), 1)) {
    airbag_legs_on = doc[F("airbag_legs_on")][0];
    legsTimer = 0;
  }
  else if (validateInput(F("airbag_outside_on"), 1)) {
    airbag_outside_on = doc[F("airbag_outside_on")][0];
    outsideTimer = 0;
  }
  else if (validateInput(F("airbag_time_max"), 1)) {
    airbag_time_max = doc[F("airbag_time_max")][0];
  }

  else if (validateInput(F("butt_vibration_on"), 1)) {
    digitalWrite(vibration, doc[F("butt_vibration_on")][0].as<bool>());
  }

  else if (validateInput(F("backlight_on"), 1)) {
    backlight_on = doc[F("backlight_on")][0];
  }
  else if (validateInput(F("backlight_color"), 3)) {
    backlight_color[0] = doc[F("backlight_color")][0];
    backlight_color[1] = doc[F("backlight_color")][1];
    backlight_color[2] = doc[F("backlight_color")][2];
  }
  else if (validateInput(F("backlight_LED"), 4)) {
    backlight_LED[0] = doc[F("backlight_LED")][0];
    backlight_LED[1] = doc[F("backlight_LED")][1];
    backlight_LED[2] = doc[F("backlight_LED")][2];
    backlight_LED[3] = doc[F("backlight_LED")][3];
  }
  else if (validateInput(F("blacklight_program"), 4)) {
    blacklight_program[0] = doc[F("blacklight_program")][0];
    blacklight_program[1] = doc[F("blacklight_program")][1];
    blacklight_program[2] = doc[F("blacklight_program")][2];
    blacklight_program[3] = doc[F("blacklight_program")][3];

    if (blacklight_program[0] == 0) {
      ledBreathMin = blacklight_program[1];
      ledBreathMax = blacklight_program[2];
      breathingTime = blacklight_program[3];
    }
  }

  else if (validateInput(F("redgreen_statuslight"), 1)) {
    redgreen_statuslight = doc[F("redgreen_statuslight")][0];
    digitalWrite(redgreen, redgreen_statuslight);
  }

  else if (validateInput(F("button_bounce_time"), 1)) {
    button_bounce_time = doc[F("button_bounce_time")][0];
    roller_sensor_top.interval(button_bounce_time);
    roller_sensor_bottom.interval(button_bounce_time);
  }

  else if (validateInput(F("time_since_started"), 1)) {
    //cannot be set
  }
  else if (validateInput(F("status"), 1)) {
    //cannot be set
  }
  else if (validateInput(F("reset"), 1)) {
    reset();
  }
  else if (validateInput(F("recalibrate"), 1)) {
    rollerCalibrationRoutine();
  }
  else if (validateInput(F("maxAckInterval"), 1)) {
    maxAckInterval = doc[F("maxAckInterval")][0];
  }
  else return incorrectMessage(message);

  sendAck();
}



void incorrectMessage(const char* mssg) {
  Serial.print(F("{\n\t\"no useful message\":\""));
  Serial.print(mssg);
  Serial.println(F("\"\n}"));
}

bool validateInput(const __FlashStringHelper* command, int expectedArguments) {
  if (expectedArguments == 0) return false;
  for (int i = 0; i < expectedArguments; i++) {
    if (doc[command][i].isNull()) return false;
  }
  strcpy_P(last_command, (const char*)command);
  return true;
}
