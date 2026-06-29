bool queueAck = false;
void sendAck() {
  queueAck = true;
}

elapsedMillis ackTimer;
int maxAckInterval = 100;

void doAck() {
    if (ackTimer > maxAckInterval)
  {
    ackTimer = 0;
  if (queueAck) {
    queueAck = false;

    unsigned long timeCheck = millis();
    //JSONify


    Serial.print(F("{"));
    Serial.print(F("\n\t\"time_since_started\":"));
    Serial.print(millis());
    Serial.print(maxStringLength);
    Serial.print(F(",\n\t\"last_command\":\""));
    Serial.print(last_command);
    Serial.print(F("\",\n\t\"serial_error\":\""));
    Serial.print(serial_error);
    Serial.print(F("\",\n\t\"blinkTime\":"));
    Serial.print(blinkTime);
    Serial.print(F(",\n\t\"chair_position_estimated\":"));
    Serial.print(chair_position_estimated);
    Serial.print(F(",\n\t\"chair_position_target\":"));
    Serial.print(chair_position_target);
    Serial.print(F(",\n\t\"chair_position_target_range\":"));
    Serial.print(chair_position_target_range);
    Serial.print(F(",\n\t\"chair_position_motor_direction\":"));
    Serial.print(chair_position_motor_direction);
    Serial.print(F(",\n\t\"chair_position_move_time_max\":"));
    Serial.print(chair_position_move_time_max);
    Serial.print(F(",\n\t\"chair_position_move_time_up\":"));
    Serial.print(chair_position_move_time_up);
    Serial.print(F(",\n\t\"chair_position_move_time_down\":"));
    Serial.print(chair_position_move_time_down);
    Serial.print(F(",\n\t\"roller_kneading_on\":"));
    Serial.print(roller_kneading_on);
    Serial.print(F(",\n\t\"roller_kneading_speed\":"));
    Serial.print(roller_kneading_speed);
    Serial.print(F(",\n\t\"roller_pounding_on\":"));
    Serial.print(roller_pounding_on);
    Serial.print(F(",\n\t\"roller_pounding_speed\":"));
    Serial.print(roller_pounding_speed);
    Serial.print(F(",\n\t\"roller_position_estimated\":"));
    Serial.print(roller_position_estimated);
    Serial.print(F(",\n\t\"roller_position_target\":"));
    Serial.print(roller_position_target);
    Serial.print(F(",\n\t\"roller_position_target_range\":"));
    Serial.print(roller_position_target_range);
    Serial.print(F(",\n\t\"roller_position_motor_direction\":"));
    Serial.print(roller_position_motor_direction);
    Serial.print(F(",\n\t\"roller_sensor_top\":"));
    Serial.print(roller_sensor_top.read());
    Serial.print(F(",\n\t\"roller_sensor_bottom\":"));
    Serial.print(roller_sensor_bottom.read());
    Serial.print(F(",\n\t\"roller_move_time_up\":"));
    Serial.print(roller_move_time_up);
    Serial.print(F(",\n\t\"roller_move_time_down\":"));
    Serial.print(roller_move_time_down);
    Serial.print(F(",\n\t\"kneading_position\":"));
    Serial.print(kneading_position);
    Serial.print(F(",\n\t\"feet_roller_on\":"));
    Serial.print(feet_roller_on);
    Serial.print(F(",\n\t\"feet_roller_speed\":"));
    Serial.print(feet_roller_speed);
    Serial.print(F(",\n\t\"airpump_on\":"));
    Serial.print(digitalRead(pump));
    Serial.print(F(",\n\t\"airbag_shoulders_on\":"));
    Serial.print(digitalRead(shoulders));
    Serial.print(F(",\n\t\"airbag_arms_on\":"));
    Serial.print(digitalRead(arms));
    Serial.print(F(",\n\t\"airbag_legs_on\":"));
    Serial.print(digitalRead(legs));
    Serial.print(F(",\n\t\"airbag_outside_on\":"));
    Serial.print(digitalRead(outside));
    Serial.print(F(",\n\t\"airbag_time_max\":"));
    Serial.print(airbag_time_max);
    Serial.print(F(",\n\t\"butt_vibration_on\":"));
    Serial.print(digitalRead(vibration));
    Serial.print(F(",\n\t\"backlight_on\":"));
    Serial.print(backlight_on);
    Serial.print(F(",\n\t\"backlight_color\":["));
    Serial.print(backlight_color[0]);
    Serial.print(",");
    Serial.print(backlight_color[1]);
    Serial.print(",");
    Serial.print(backlight_color[2]);
    Serial.print(F("],\n\t\"backlight_LED\":["));
    Serial.print(backlight_LED[0]);
    Serial.print(",");
    Serial.print(backlight_LED[1]);
    Serial.print(F("],\n\t\"blacklight_program\":["));
    Serial.print(blacklight_program[0]);
    Serial.print(",");
    Serial.print(blacklight_program[1]);
    Serial.print(",");
    Serial.print(blacklight_program[2]);
    Serial.print(",");
    Serial.print(blacklight_program[3]);
    Serial.print(F("],\n\t\"redgreen_statuslight\":"));
    Serial.print(redgreen_statuslight);
    Serial.print(F(",\n\t\"button_bounce_time\":"));
    Serial.print(button_bounce_time);
    Serial.print(F(",\n\t\"maxStringLength\":"));
    Serial.print(maxStringLength);
    Serial.print(F(",\n\t\"maxAckInterval\":"));
    Serial.print(maxAckInterval);
    Serial.print(F(",\n\t\"ackTime\":"));
    Serial.print(millis() - timeCheck);
    Serial.println(F("\n}"));
  }
  }
}
