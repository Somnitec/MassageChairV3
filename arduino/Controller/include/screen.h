#pragma once

// Layout + animation engine for the 3 status OLEDs. See screen.cpp for the
// word-wrap/font-fit/marquee-fallback/transition-effect implementation.

#include <Arduino.h>
#include <U8g2lib.h>
#include <elapsedMillis.h>

#define SCREEN_W 128
#define SCREEN_H 64
#define MARGIN 3
#define TEXT_MAX 80
#define MAX_LINES 4
#define LINE_MAX 22

#define SCREEN_A 0
#define SCREEN_B 1
#define SCREEN_C 2
#define SCREEN_COUNT 3

enum Effect { EFFECT_INSTANT, EFFECT_WIPE, EFFECT_FLASH, EFFECT_TYPEWRITER, EFFECT_MARQUEE };

struct ScreenState {
  U8G2 *oled;
  char text[TEXT_MAX];
  char lines[MAX_LINES][LINE_MAX];
  uint8_t lineCount;
  const uint8_t *font;
  int8_t ascent, descent;
  uint8_t lineHeight;

  bool marquee;
  int16_t marqueeOffset;
  uint16_t marqueeTextWidth;
  elapsedMillis marqueeTimer;

  Effect effect;
  bool effectActive;
  uint8_t effectFrame;
  uint16_t effectRevealChars;
  uint16_t effectTotalChars;
  elapsedMillis effectTimer;

  bool pulse;
  elapsedMillis pulseTimer;
};

extern ScreenState screens[SCREEN_COUNT];

void initScreens();

// Text takes an optional transition effect; the 2-arg overload defaults to
// EFFECT_WIPE. Text too long to fit even the smallest font auto-scrolls
// (marquee) instead of getting clipped.
void setScreenText(uint8_t idx, const char *text, Effect fx);
void setScreenText(uint8_t idx, const char *text);

void setScreenPulse(uint8_t idx, bool on);
void clearAllScreens();
void updateScreens();

Effect parseEffect(const char *name, Effect fallback);
const char *effectName(Effect fx);
