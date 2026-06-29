
elapsedMillis shoulderTimer;
elapsedMillis legsTimer;
elapsedMillis armsTimer;
elapsedMillis outsideTimer;


void airbagRoutine() {

  digitalWrite(pump,  airpump_on);

  if (shoulderTimer > airbag_time_max)     digitalWrite(shoulders, LOW);
  else digitalWrite(shoulders, airbag_shoulders_on);

  if (legsTimer > airbag_time_max)digitalWrite(legs, LOW);
  else digitalWrite(legs, airbag_legs_on);

  if (armsTimer > airbag_time_max)digitalWrite(arms, LOW);
  else digitalWrite(arms, airbag_arms_on);

  if (outsideTimer > airbag_time_max)digitalWrite(outside, LOW);
  else digitalWrite(outside, airbag_outside_on);


}

void allAirbagsOff() {
  airpump_on = false;
  airbag_shoulders_on = false;
  airbag_arms_on = false;
  airbag_legs_on = false;
  airbag_outside_on = false;
  digitalWrite(pump,  LOW);
  digitalWrite(shoulders,  LOW);
  digitalWrite(arms,  LOW);
  digitalWrite(legs,  LOW);
  digitalWrite(outside,  LOW);

}
