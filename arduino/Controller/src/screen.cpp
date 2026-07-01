/*
  Given arbitrary text, layoutScreenText() greedily word-wraps it at the
  largest of a few fonts that both (a) fits within MAX_LINES and (b) never
  overflows the screen width on any line. If nothing fits even at the
  smallest font, it falls back to that smallest font and truncates with a
  trailing "..." -- callers never have to pre-measure strings. Explicit
  effect "marquee" (EFFECT_MARQUEE) still scrolls instead, if ever wanted.

  Redraws are driven from updateScreens(), called once per loop(); each
  screen only actually repaints when its own timer says a frame is due, so
  three screens animating at once don't serialize into one big stall.
*/

#include "screen.h"

#include <string.h>
#include "logging.h"

#define WIPE_FRAMES 6
#define FLASH_FRAMES 4
#define EFFECT_STEP_MS 35
#define TYPEWRITER_CHARS_PER_STEP 1

#define MARQUEE_STEP_MS 40
#define MARQUEE_SPEED_PX 3
#define MARQUEE_GAP_PX 24

#define PULSE_STEP_MS 30
#define PULSE_PERIOD_MS 1600
#define PULSE_MIN 40

// Software I2C displays, one per bus -- kept file-local; every other file
// talks to a screen only through its index (SCREEN_A/B/C).
static U8G2_SH1106_128X64_NONAME_1_SW_I2C oledA(U8G2_R0, /* clock=*/ 16, /* data=*/ 17, /* reset=*/ U8X8_PIN_NONE);
static U8G2_SH1106_128X64_NONAME_1_SW_I2C oledB(U8G2_R0, /* clock=*/ 22, /* data=*/ 23, /* reset=*/ U8X8_PIN_NONE);
static U8G2_SH1106_128X64_NONAME_1_SW_I2C oledC(U8G2_R0, /* clock=*/ 19, /* data=*/ 18, /* reset=*/ U8X8_PIN_NONE);

ScreenState screens[SCREEN_COUNT];

static const uint8_t *const STATIC_FONTS[] = {
  u8g2_font_helvB14_tr, u8g2_font_helvB12_tr, u8g2_font_helvB10_tr, u8g2_font_helvB08_tr
};
static const uint8_t STATIC_FONT_COUNT = sizeof(STATIC_FONTS) / sizeof(STATIC_FONTS[0]);
static const uint8_t *const MARQUEE_FONT = u8g2_font_helvB10_tr;

// -------------------------------------------------------------- helpers --

const char *effectName(Effect fx) {
  switch (fx) {
    case EFFECT_INSTANT: return "instant";
    case EFFECT_WIPE: return "wipe";
    case EFFECT_FLASH: return "flash";
    case EFFECT_TYPEWRITER: return "typewriter";
    case EFFECT_MARQUEE: return "marquee";
  }
  return "?";
}

Effect parseEffect(const char *name, Effect fallback) {
  if (!name || !name[0]) return fallback;
  if (!strcmp(name, "instant")) return EFFECT_INSTANT;
  if (!strcmp(name, "wipe")) return EFFECT_WIPE;
  if (!strcmp(name, "flash")) return EFFECT_FLASH;
  if (!strcmp(name, "typewriter")) return EFFECT_TYPEWRITER;
  if (!strcmp(name, "marquee")) return EFFECT_MARQUEE;
  return fallback;
}

// Collapses tabs/newlines/runs of spaces into single spaces and trims the
// ends, so layout only ever has to reason about one kind of whitespace.
static void collapseWhitespace(const char *in, char *out, size_t outSize) {
  size_t o = 0;
  bool lastSpace = true;
  for (const char *p = in; *p && o + 1 < outSize; p++) {
    char c = (*p == '\t' || *p == '\n' || *p == '\r') ? ' ' : *p;
    if (c == ' ') {
      if (lastSpace) continue;
      lastSpace = true;
    } else {
      lastSpace = false;
    }
    out[o++] = c;
  }
  while (o > 0 && out[o - 1] == ' ') o--;
  out[o] = '\0';
}

// Greedy word-wrap of `text` into `lines` at the given font. Returns false
// (tier rejected) if it needs more than maxLines, or if any resulting line
// -- including an unavoidably long single word -- still exceeds maxWidth.
static bool wrapText(U8G2 *oled, const char *text, char lines[][LINE_MAX],
                      uint8_t maxLines, uint8_t *lineCountOut, uint16_t maxWidth) {
  uint8_t lineCount = 0;
  char current[LINE_MAX] = "";
  uint8_t currentLen = 0;

  const char *p = text;
  while (*p) {
    while (*p == ' ') p++;
    if (!*p) break;
    const char *wordStart = p;
    while (*p && *p != ' ') p++;
    uint8_t wordLen = p - wordStart;
    if (wordLen >= LINE_MAX) wordLen = LINE_MAX - 1;

    char word[LINE_MAX];
    memcpy(word, wordStart, wordLen);
    word[wordLen] = '\0';

    // Compute the joined length ourselves (rather than snprintf-and-check,
    // which truncates and would silently hide an overflow) before touching
    // any buffer, so a too-long candidate is rejected instead of clipped.
    size_t wordLen2 = strlen(word);
    size_t needed = currentLen + (currentLen > 0 ? 1 : 0) + wordLen2;
    bool fitsChars = needed < LINE_MAX;

    char candidate[LINE_MAX];
    if (fitsChars) {
      if (currentLen > 0) {
        memcpy(candidate, current, currentLen);
        candidate[currentLen] = ' ';
        memcpy(candidate + currentLen + 1, word, wordLen2);
        candidate[needed] = '\0';
      } else {
        memcpy(candidate, word, wordLen2);
        candidate[wordLen2] = '\0';
      }
    }
    uint16_t candidateWidth = fitsChars ? oled->getStrWidth(candidate) : 0xFFFF;

    if (fitsChars && candidateWidth <= maxWidth) {
      strncpy(current, candidate, LINE_MAX - 1);
      current[LINE_MAX - 1] = '\0';
      currentLen = strlen(current);
    } else {
      if (currentLen > 0) {
        if (lineCount >= maxLines) return false;
        strncpy(lines[lineCount], current, LINE_MAX - 1);
        lines[lineCount][LINE_MAX - 1] = '\0';
        lineCount++;
      }
      strncpy(current, word, LINE_MAX - 1);
      current[LINE_MAX - 1] = '\0';
      currentLen = strlen(current);
    }
  }
  if (currentLen > 0) {
    if (lineCount >= maxLines) return false;
    strncpy(lines[lineCount], current, LINE_MAX - 1);
    lines[lineCount][LINE_MAX - 1] = '\0';
    lineCount++;
  }
  *lineCountOut = lineCount;

  for (uint8_t i = 0; i < lineCount; i++) {
    if (oled->getStrWidth(lines[i]) > maxWidth) return false;
  }
  return true;
}

// Shortens `line` in place, one character at a time, until "<line>..." fits
// within maxWidth. Cheap: a handful of getStrWidth() calls, no I2C
// involved, run once per screen text update rather than per frame.
static void truncateWithEllipsis(U8G2 *oled, char *line, uint16_t maxWidth) {
  if (oled->getStrWidth(line) <= maxWidth) return;
  size_t len = strlen(line);
  char buf[LINE_MAX];
  while (len > 0) {
    len--;
    while (len > 0 && line[len - 1] == ' ') len--; // no "word ..." double space
    snprintf(buf, sizeof(buf), "%.*s...", (int)len, line);
    if (oled->getStrWidth(buf) <= maxWidth) {
      strncpy(line, buf, LINE_MAX - 1);
      line[LINE_MAX - 1] = '\0';
      return;
    }
  }
  strncpy(line, "...", LINE_MAX - 1);
  line[LINE_MAX - 1] = '\0';
}

// Same greedy word-wrap as wrapText(), but never rejects: once `maxLines`
// lines are filled the rest of `text` is dropped (and any lone word wider
// than the screen is hard-cut), always leaving a trailing "..." behind so
// a cut reads as "cut off", not as silently missing text.
static void wrapTextClip(U8G2 *oled, const char *text, char lines[][LINE_MAX],
                          uint8_t maxLines, uint8_t *lineCountOut, uint16_t maxWidth) {
  uint8_t lineCount = 0;
  char current[LINE_MAX] = "";
  uint8_t currentLen = 0;
  bool clipped = false;

  const char *p = text;
  while (*p) {
    while (*p == ' ') p++;
    if (!*p) break;
    if (lineCount >= maxLines) { clipped = true; break; }

    const char *wordStart = p;
    while (*p && *p != ' ') p++;
    uint8_t wordLen = p - wordStart;
    if (wordLen >= LINE_MAX) wordLen = LINE_MAX - 1;
    char word[LINE_MAX];
    memcpy(word, wordStart, wordLen);
    word[wordLen] = '\0';

    size_t wl = strlen(word);
    size_t needed = currentLen + (currentLen > 0 ? 1 : 0) + wl;
    bool fitsChars = needed < LINE_MAX;
    uint16_t candidateWidth = 0xFFFF;
    char candidate[LINE_MAX];
    if (fitsChars) {
      if (currentLen > 0) {
        memcpy(candidate, current, currentLen);
        candidate[currentLen] = ' ';
        memcpy(candidate + currentLen + 1, word, wl);
        candidate[needed] = '\0';
      } else {
        memcpy(candidate, word, wl);
        candidate[wl] = '\0';
      }
      candidateWidth = oled->getStrWidth(candidate);
    }

    if (fitsChars && candidateWidth <= maxWidth) {
      memcpy(current, candidate, needed + 1);
      currentLen = needed;
    } else {
      if (currentLen > 0) {
        strncpy(lines[lineCount], current, LINE_MAX - 1);
        lines[lineCount][LINE_MAX - 1] = '\0';
        lineCount++;
        current[0] = '\0';
        currentLen = 0;
        if (lineCount >= maxLines) { clipped = true; break; }
      }
      strncpy(current, word, LINE_MAX - 1);
      current[LINE_MAX - 1] = '\0';
      currentLen = strlen(current);
    }
  }
  if (currentLen > 0) {
    if (lineCount < maxLines) {
      strncpy(lines[lineCount], current, LINE_MAX - 1);
      lines[lineCount][LINE_MAX - 1] = '\0';
      lineCount++;
    } else {
      clipped = true;
    }
  }
  while (*p == ' ') p++;
  if (*p) clipped = true;

  // a lone word wider than the screen never got width-checked above
  for (uint8_t i = 0; i < lineCount; i++) {
    if (oled->getStrWidth(lines[i]) > maxWidth) truncateWithEllipsis(oled, lines[i], maxWidth);
  }
  if (clipped && lineCount > 0) {
    truncateWithEllipsis(oled, lines[lineCount - 1], maxWidth);
  }

  *lineCountOut = lineCount;
}

static void layoutScreenText(ScreenState &s, const char *rawText, bool forceMarquee) {
  char clean[TEXT_MAX];
  collapseWhitespace(rawText, clean, sizeof(clean));
  strncpy(s.text, clean, TEXT_MAX - 1);
  s.text[TEXT_MAX - 1] = '\0';

  const uint16_t maxWidth = SCREEN_W - 2 * MARGIN;
  const uint16_t maxHeight = SCREEN_H - 2 * MARGIN;

  if (forceMarquee && clean[0] != '\0') {
    s.oled->setFont(MARQUEE_FONT);
    s.font = MARQUEE_FONT;
    s.ascent = s.oled->getAscent();
    s.descent = s.oled->getDescent();
    s.lineHeight = s.ascent - s.descent + 2;
    s.lineCount = 0;
    s.marquee = true;
    s.marqueeTextWidth = s.oled->getStrWidth(clean);
    s.marqueeOffset = maxWidth;
    s.marqueeTimer = 0;
    return;
  }
  s.marquee = false;

  if (clean[0] != '\0') {
    for (uint8_t f = 0; f < STATIC_FONT_COUNT; f++) {
      const uint8_t *font = STATIC_FONTS[f];
      s.oled->setFont(font);
      uint8_t lh = s.oled->getAscent() - s.oled->getDescent() + 2;
      uint8_t maxLines = maxHeight / lh;
      if (maxLines < 1) maxLines = 1;
      if (maxLines > MAX_LINES) maxLines = MAX_LINES;

      uint8_t lc = 0;
      if (wrapText(s.oled, clean, s.lines, maxLines, &lc, maxWidth)) {
        s.font = font;
        s.lineCount = lc;
        s.lineHeight = lh;
        s.ascent = s.oled->getAscent();
        s.descent = s.oled->getDescent();
        return;
      }
    }
  }

  // Nothing fit even at the smallest font (or the text is empty): use the
  // smallest font and just cut off whatever doesn't fit, marking the cut
  // with "..." -- explicit effect "marquee" is still available if scrolling
  // is ever wanted instead.
  const uint8_t *font = STATIC_FONTS[STATIC_FONT_COUNT - 1];
  s.oled->setFont(font);
  uint8_t lh = s.oled->getAscent() - s.oled->getDescent() + 2;
  uint8_t maxLines = maxHeight / lh;
  if (maxLines < 1) maxLines = 1;
  if (maxLines > MAX_LINES) maxLines = MAX_LINES;

  uint8_t lc = 0;
  wrapTextClip(s.oled, clean, s.lines, maxLines, &lc, maxWidth);
  s.font = font;
  s.lineCount = lc;
  s.lineHeight = lh;
  s.ascent = s.oled->getAscent();
  s.descent = s.oled->getDescent();
}

// -------------------------------------------------------------- drawing --

static void drawScreenLines(ScreenState &s, uint16_t revealChars) {
  s.oled->setFont(s.font);
  uint16_t blockHeight = s.lineCount * s.lineHeight;
  int16_t startY = (SCREEN_H - blockHeight) / 2;
  if (startY < 0) startY = 0;

  uint16_t shown = 0;
  for (uint8_t i = 0; i < s.lineCount; i++) {
    const char *line = s.lines[i];
    uint8_t lineLen = strlen(line);
    char buf[LINE_MAX];
    const char *toDraw = line;
    if (revealChars != 0xFFFF) {
      uint16_t remaining = (revealChars > shown) ? (revealChars - shown) : 0;
      uint8_t take = remaining < lineLen ? remaining : lineLen;
      memcpy(buf, line, take);
      buf[take] = '\0';
      toDraw = buf;
      shown += lineLen;
      if (take == 0) continue; // nothing to show yet on this or later lines
    }
    uint16_t w = s.oled->getStrWidth(toDraw);
    int16_t x = (SCREEN_W - w) / 2;
    if (x < 0) x = 0;
    int16_t y = startY + i * s.lineHeight;
    s.oled->drawStr(x, y, toDraw);
  }
}

static void drawScreenMarquee(ScreenState &s) {
  s.oled->setFont(s.font);
  int16_t y = (SCREEN_H - s.lineHeight) / 2;
  if (y < 0) y = 0;
  s.oled->drawStr(s.marqueeOffset, y, s.text);
}

static void renderScreen(ScreenState &s) {
  s.oled->firstPage();
  do {
    if (s.marquee) {
      drawScreenMarquee(s);
    } else if (s.lineCount > 0) {
      if (s.effectActive && s.effect == EFFECT_WIPE) {
        int16_t clipX = (int32_t)(s.effectFrame + 1) * SCREEN_W / WIPE_FRAMES;
        if (clipX > SCREEN_W) clipX = SCREEN_W;
        s.oled->setClipWindow(0, 0, clipX, SCREEN_H);
        drawScreenLines(s, 0xFFFF);
        s.oled->setMaxClipWindow();
      } else if (s.effectActive && s.effect == EFFECT_FLASH) {
        bool showText = (s.effectFrame % 2) == 1; // blank, text, blank, text
        if (showText) drawScreenLines(s, 0xFFFF);
      } else if (s.effectActive && s.effect == EFFECT_TYPEWRITER) {
        drawScreenLines(s, s.effectRevealChars);
      } else {
        drawScreenLines(s, 0xFFFF);
      }
    }
  } while (s.oled->nextPage());
}

// ------------------------------------------------------------- controls --

void initScreens() {
  screens[SCREEN_A].oled = &oledA;
  screens[SCREEN_B].oled = &oledB;
  screens[SCREEN_C].oled = &oledC;

  for (uint8_t i = 0; i < SCREEN_COUNT; i++) {
    ScreenState &s = screens[i];
    s.oled->begin();
    s.oled->setFontMode(1);
    s.oled->setFontPosTop();
    s.text[0] = '\0';
    s.lineCount = 0;
    s.font = MARQUEE_FONT;
    s.marquee = false;
    s.effect = EFFECT_INSTANT;
    s.effectActive = false;
    s.pulse = false;
  }

  setScreenText(SCREEN_A, "....", EFFECT_INSTANT);
  setScreenText(SCREEN_B, ".....", EFFECT_INSTANT);
  setScreenText(SCREEN_C, "...", EFFECT_INSTANT);
}

void setScreenText(uint8_t idx, const char *text, Effect fx) {
  if (idx >= SCREEN_COUNT) return;
  ScreenState &s = screens[idx];
  bool forceMarquee = (fx == EFFECT_MARQUEE);
  layoutScreenText(s, text ? text : "", forceMarquee);

  s.effect = forceMarquee ? EFFECT_INSTANT : fx;
  s.effectFrame = 0;
  s.effectTimer = 0;
  s.effectActive = false;

  if (!s.marquee) {
    switch (s.effect) {
      case EFFECT_WIPE:
      case EFFECT_FLASH:
        s.effectActive = true;
        break;
      case EFFECT_TYPEWRITER: {
        uint16_t total = 0;
        for (uint8_t i = 0; i < s.lineCount; i++) total += strlen(s.lines[i]);
        s.effectTotalChars = total;
        s.effectRevealChars = 0;
        s.effectActive = (total > 0);
        break;
      }
      default:
        break;
    }
  }

  renderScreen(s); // paint frame 0 immediately, don't wait for the next loop tick

  logEvent("SCR", "%c <- \"%s\" (%dpx font, %d line%s, %s%s)", 'A' + idx, s.text,
           (int)(s.ascent - s.descent), s.lineCount, s.lineCount == 1 ? "" : "s",
           effectName(fx), s.marquee ? ", auto-marquee" : "");
}

void setScreenText(uint8_t idx, const char *text) {
  setScreenText(idx, text, EFFECT_WIPE);
}

void clearAllScreens() {
  for (uint8_t i = 0; i < SCREEN_COUNT; i++) {
    setScreenText(i, "", EFFECT_INSTANT);
  }
}

void setScreenPulse(uint8_t idx, bool on) {
  if (idx >= SCREEN_COUNT) return;
  ScreenState &s = screens[idx];
  s.pulse = on;
  s.pulseTimer = 0;
  if (!on) s.oled->setContrast(255);
  logEvent("SCR", "%c pulse=%s", 'A' + idx, on ? "on" : "off");
}

static void applyPulseContrast(ScreenState &s) {
  unsigned long t = millis() % PULSE_PERIOD_MS;
  unsigned long half = PULSE_PERIOD_MS / 2;
  unsigned long phase = (t < half) ? t : (PULSE_PERIOD_MS - t);
  uint8_t level = PULSE_MIN + (uint8_t)((uint32_t)(255 - PULSE_MIN) * phase / half);
  s.oled->setContrast(level);
}

static void updateScreenEffect(ScreenState &s) {
  bool needsRedraw = false;

  if (s.marquee) {
    if (s.marqueeTimer > MARQUEE_STEP_MS) {
      s.marqueeTimer = 0;
      s.marqueeOffset -= MARQUEE_SPEED_PX;
      int16_t maxWidth = SCREEN_W - 2 * MARGIN;
      if (s.marqueeOffset < -(int16_t)s.marqueeTextWidth - MARQUEE_GAP_PX) {
        s.marqueeOffset = maxWidth;
      }
      needsRedraw = true;
    }
  } else if (s.effectActive) {
    if (s.effectTimer > EFFECT_STEP_MS) {
      s.effectTimer = 0;
      s.effectFrame++;
      needsRedraw = true;
      switch (s.effect) {
        case EFFECT_WIPE:
          if (s.effectFrame >= WIPE_FRAMES) s.effectActive = false;
          break;
        case EFFECT_FLASH:
          if (s.effectFrame >= FLASH_FRAMES) s.effectActive = false;
          break;
        case EFFECT_TYPEWRITER:
          s.effectRevealChars += TYPEWRITER_CHARS_PER_STEP;
          if (s.effectRevealChars >= s.effectTotalChars) {
            s.effectRevealChars = s.effectTotalChars;
            s.effectActive = false;
          }
          break;
        default:
          s.effectActive = false;
          break;
      }
    }
  }

  if (s.pulse && s.pulseTimer > PULSE_STEP_MS) {
    s.pulseTimer = 0;
    applyPulseContrast(s);
  }

  if (needsRedraw) renderScreen(s);
}

void updateScreens() {
  for (uint8_t i = 0; i < SCREEN_COUNT; i++) {
    updateScreenEffect(screens[i]);
  }
}
