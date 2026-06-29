void sendCommand(String command, String variable){
  sendMessage(command,variable);
}

void sendCommand(String command, bool variable){
  sendMessage(command,String(variable));
}


void sendCommand(String command, int variable){
  sendMessage(command,String(variable));
}

void sendMessage(String command, String variable){
  Serial.print(F("{\n\t\"controllerCommand\":\""));
  Serial.print(command);
  Serial.print(F("\",\n\t\"controllerValue\":\""));
  Serial.print(variable);
  Serial.println(F("\"\n}"));
}
