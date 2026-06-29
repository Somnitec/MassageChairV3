elapsedMillis chairPositionTimer;

long startChairPosition = 0;
int previousChairMotorDirection = 0;

bool chairNewInput = false;

void chairPositionRoutine() {

  //0 is flat and 1 is upright

  //reset position counter if direction is changed


  //estimating position
  if (chair_position_motor_direction == 1) {
    chair_position_estimated = startChairPosition + map(chairPositionTimer, 0, chair_position_move_time_up, 0, 10000);
  }
  else if (chair_position_motor_direction == -1) {
    chair_position_estimated = startChairPosition - map(chairPositionTimer, 0, chair_position_move_time_down, 0, 10000);

  }

  if (chair_position_target == 10000) {
    //Serial.println(chairPositionTimer);
    if (chairNewInput) {
      chair_position_motor_direction = 1;
      chairNewInput=false;
    }
    else if (chairPositionTimer > chair_position_move_time_up)  chair_position_motor_direction = 0;
  }
  else if (chair_position_target == 0) {
    //Serial.println(chairPositionTimer);
    if (chairNewInput){
      chair_position_motor_direction = -1;
      chairNewInput=false;
    }
    else if(chairPositionTimer > chair_position_move_time_down) chair_position_motor_direction = 0;
  }
  /* disabled all other positions than the extremes to make sure those are always functional
    //checking if position or endpoint is reached
    else if ( (chair_position_estimated > chair_position_target - chair_position_target_range  &&
               chair_position_estimated < chair_position_target + chair_position_target_range  )
            ) {//stop when it is in range
      chair_position_motor_direction = 0;
      //Serial.println("positionReached");
      //found position
    }
    else if (chair_position_target < chair_position_estimated) { // && chair_position_motor_direction != -1) {
      chair_position_motor_direction = -1;
      //chair should move down
    }
    else if (chair_position_target > chair_position_estimated) { // && chair_position_motor_direction != 1) {
      chair_position_motor_direction = 1;
      //chair should move down
    }
  */

  //setting motors
  if (chair_position_motor_direction == 1) {
    digitalWrite(chairdown, LOW);
    digitalWrite(chairup, HIGH);
  } else if (chair_position_motor_direction == -1) {
    digitalWrite(chairup, LOW);
    digitalWrite(chairdown, HIGH);
  } else {
    digitalWrite(chairup, LOW);
    digitalWrite(chairdown, LOW);
  }


  if (previousChairMotorDirection != chair_position_motor_direction) {
    //Serial.println("direction changed");
    chairPositionTimer = 0;
    startChairPosition = chair_position_estimated;
    previousChairMotorDirection = chair_position_motor_direction;
  }



}

void moveChairUp() {
  chairPositionTimer = 0;
  digitalWrite(chairdown, LOW);
  digitalWrite(chairup, HIGH);
  while (chairPositionTimer < chair_position_move_time_up) {}
  digitalWrite(chairup, LOW);
  digitalWrite(chairdown, LOW);

  chair_position_estimated = 10000;
  chair_position_target = 10000;
}
