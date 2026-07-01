#pragma once

void readSerial();
void receiveMessage(char *message);
void printError(const char *error);
void unknownCommand(const char *message);
