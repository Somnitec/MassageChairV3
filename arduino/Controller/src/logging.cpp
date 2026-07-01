#include "logging.h"

#include <Arduino.h>
#include <stdarg.h>
#include <stdio.h>

void logEvent(const char *tag, const char *fmt, ...) {
  char msg[140];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(msg, sizeof(msg), fmt, ap);
  va_end(ap);

  Serial.print(F("# ["));
  Serial.print(millis());
  Serial.print(F("ms] "));
  Serial.print(tag);
  Serial.print(F(": "));
  Serial.println(msg);
}
