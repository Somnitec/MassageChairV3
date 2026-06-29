//still to implement: direct motor overides



//also makes sure that the sensors (supposedly) never really get pressed
elapsedMillis rollerStartTimer;
long startRollerPosition = 0;
int previousRollerMotorDirection = 0;




void rollerRoutine() {
  //

  //see if top or bottom sensor is pressed, if so reset range
  //check if estimated if below or above the range of the target
  //if changing direction, set a timestamp from when the direction was changed
  //looping to see if the target or sensors are hit
  //update estimated position



  //reset position counter
  if (previousRollerMotorDirection != roller_position_motor_direction) {
    //Serial.println("direction changed");
    rollerStartTimer = 0;
    startRollerPosition = roller_position_estimated;
    previousRollerMotorDirection = roller_position_motor_direction;
  }

  //estimating position
  if (roller_position_motor_direction == 1) {
    roller_position_estimated = startRollerPosition + map(rollerStartTimer, 0, roller_move_time_up, 0, 10000);
  }
  else if (roller_position_motor_direction == -1) {
    roller_position_estimated = startRollerPosition - map(rollerStartTimer, 0, roller_move_time_down, 0, 10000);

  }

  //act on estimated position
  /*if (roller_position_target == 0 || roller_position_target == 10000) {
    //if the extremes are asked, go all the way to the sensor //not yet functional
    }
    else*/ if ( (roller_position_estimated > roller_position_target - roller_position_target_range  &&
                 roller_position_estimated < roller_position_target + roller_position_target_range  )
              ) {//stop when it is in range
    if (roller_position_motor_direction != 0) {
      strcpy(last_command, "roller position reached");
      sendAck();
    }
    roller_position_motor_direction = 0;

    //found position
  }
  else if (roller_position_target < roller_position_estimated && roller_position_motor_direction != -1) {
    roller_position_motor_direction = -1;

    //roller should move down
  }
  else if (roller_position_target > roller_position_estimated && roller_position_motor_direction != 1) {
    roller_position_motor_direction = 1;

    //roller should move down
  }

  //update sensors
  roller_sensor_top.update();
  roller_sensor_bottom.update();

  //updating motors
  //if the sensor is hit, then stop moving immediatly
  if ( (roller_sensor_top.read() && roller_position_motor_direction == 1) ||
       (roller_sensor_bottom.read() && roller_position_motor_direction == -1 )) {
    digitalWrite(mssgup, false);
    digitalWrite(mssgdown, false);
    roller_position_motor_direction = 0;
    if (roller_sensor_top.read())roller_position_estimated = 10000;
    if (roller_sensor_bottom.read())roller_position_estimated = 0;
    //Serial.println("sensor triggered");
    strcpy(last_command, "roller sensor triggered");
    sendAck();
  } else  {
    if (roller_position_motor_direction == 1) {
      digitalWrite(mssgup, true);
      digitalWrite(mssgdown, false);
    }
    else if (roller_position_motor_direction == -1) {
      digitalWrite(mssgdown, true);
      digitalWrite(mssgup, false);
    }
    else {
      digitalWrite(mssgup, false);
      digitalWrite(mssgdown, false);
    }
  }

}


/*
  else {
  if ( (roller_position_target - chair_position_target_range < roller_position_estimated &&
        roller_position_target + chair_position_target_range > roller_position_estimated )
       && roller_position_motor_direction != 0) {
    roller_position_motor_direction = 0;
    //digitalWrite(mssgup, false);
    //digitalWrite(mssgdown, false);
    Serial.println("found position");

  }
  else if (roller_position_target < roller_position_estimated && roller_position_motor_direction != -1) {
    roller_position_motor_direction = -1;
    //digitalWrite(mssgdown, true);
    rollerStartTimer = millis();
    Serial.println("have to move down");
    //roller should move down
  }
  else if (roller_position_target > roller_position_estimated && roller_position_motor_direction != 1) {
    roller_position_motor_direction = 1;
    //digitalWrite(mssgup, true);
    rollerStartTimer = millis();
    Serial.println("have to move down");
    //roller should move down
  }
  }

  //moving up estimator
  if (roller_position_motor_direction == 1) {
  roller_position_estimated -= map(millis() - rollerStartTimer, 0, roller_move_time_up, 0, 10000);
  }


  //moving down estimator
  if (roller_position_motor_direction == -1) {
  roller_position_estimated += map(millis() - rollerStartTimer, 0, roller_move_time_down, 0, 10000);
  }

  //    roller_position_estimated; //up: 0 - flat: 10000
  //roller_position_target;
*/
/*
    if (!roller_sensor_top.read() || !roller_sensor_bottom.read()) {
      if (roller_position_motor_direction == 1) digitalWrite(mssgup, true);
      else if (roller_position_motor_direction == -1) digitalWrite(mssgdown, true);
      else {
        digitalWrite(mssgup, false);
        digitalWrite(mssgdown, false);
      }
    }
*/


void moveRollerUp() {
  //move to top to always start from the same spot
  //Serial.println("moving up");
  digitalWrite(mssgup, true);
  while (!roller_sensor_top.read()) {
    roller_sensor_bottom.update();
    roller_sensor_top.update();
  }
  digitalWrite(mssgup, false);
  roller_position_estimated = 10000;

  roller_position_target = 9500;
}


void rollerCalibrationRoutine() {
  //to write, will move the roller up and down, counting the time that it needs.



  //move to bottom and count time

  //Serial.println("moving down");
  digitalWrite(mssgdown, true);
  roller_move_time_down = millis();
  while (!roller_sensor_bottom.read()) {
    roller_sensor_bottom.update();
    roller_sensor_top.update();
  }
  digitalWrite(mssgdown, false);
  roller_move_time_down = millis() - roller_move_time_down;
  //Serial.println(roller_move_time_down); //14740/14807/14783/14777 in test


  //move to top and count time
  //Serial.println("moving up again");
  digitalWrite(mssgup, true);
  roller_move_time_up = millis();
  while (!roller_sensor_top.read()) {
    roller_sensor_bottom.update();
    roller_sensor_top.update();
  }
  digitalWrite(mssgup, false);
  roller_move_time_up = millis() - roller_move_time_up;
  //Serial.println(roller_move_time_up); //15822/15850/15822/15955  in test
  Serial.println("{\n\t\"calibration finished\"\n}");
  strcpy(last_command, "calibrated rollers");
  roller_position_estimated = 10000;
  //sendAck();

}
