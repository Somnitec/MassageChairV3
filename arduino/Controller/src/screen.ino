
void OnSetScreen() {
  String screenraw = "";//cmdMessenger.readStringArg();
  int screen = screenraw.toInt();
  String text = "";//cmdMessenger.readStringArg();
  if (text)  writeToScreen(screen, text);
  else writeToScreen(screen, " ");

}




void writeToScreen(int screen, String text) {

  if (screen!=0 &&screen!=1&&screen!=2) text = " "; // could be done more cleanly
  //Serial.println(text);
  if (text == "")text = " "; //bugfix to prevent crashing on an empty string

  String text1 = text.substring(0 * CHARACTERWIDTH, 1 * CHARACTERWIDTH + 1);
  String text2 = text.substring(1 * CHARACTERWIDTH, 2 * CHARACTERWIDTH + 1);
  String text3 = text.substring(2 * CHARACTERWIDTH, 3 * CHARACTERWIDTH + 1);
  String text4 = text.substring(3 * CHARACTERWIDTH, 4 * CHARACTERWIDTH + 1);
  String text5 = text.substring(4 * CHARACTERWIDTH, 5 * CHARACTERWIDTH + 1);


  text1.toCharArray(charBuf1, CHARACTERWIDTH+1) ;
  text2.toCharArray(charBuf2, CHARACTERWIDTH+1) ;
  text3.toCharArray(charBuf3, CHARACTERWIDTH+1) ;
  text4.toCharArray(charBuf4, CHARACTERWIDTH+1) ;
  text5.toCharArray(charBuf5, CHARACTERWIDTH+1) ;

  if (screen != 1&&screen != 2) {
    OLED0.firstPage();
    do {
      //52 characters right now
      OLED0.drawStr( 0, 0 * LINESPACE + STARTSPACE, charBuf1);
      OLED0.drawStr( 0, 1 * LINESPACE + STARTSPACE, charBuf2);
      OLED0.drawStr( 0, 2 * LINESPACE + STARTSPACE, charBuf3);
      OLED0.drawStr( 0, 3 * LINESPACE + STARTSPACE, charBuf4);
      OLED0.drawStr( 0, 4 * LINESPACE + STARTSPACE, charBuf5);
    } while ( OLED0.nextPage() );
  }
  if (screen != 0&&screen != 2) {
    OLED1.firstPage();
    do {
      //65 characters
      OLED1.drawStr( 0, 0 * LINESPACE + STARTSPACE, charBuf1);
      OLED1.drawStr( 0, 1 * LINESPACE + STARTSPACE, charBuf2);
      OLED1.drawStr( 0, 2 * LINESPACE + STARTSPACE, charBuf3);
      OLED1.drawStr( 0, 3 * LINESPACE + STARTSPACE, charBuf4);
      OLED1.drawStr( 0, 4 * LINESPACE + STARTSPACE, charBuf5);
    } while ( OLED1.nextPage() );
  }
  if (screen != 0&&screen != 1) {
    OLED2.firstPage();
    do {
      //65 characters
      OLED2.drawStr( 0, 0 * LINESPACE + STARTSPACE, charBuf1);
      OLED2.drawStr( 0, 1 * LINESPACE + STARTSPACE, charBuf2);
      OLED2.drawStr( 0, 2 * LINESPACE + STARTSPACE, charBuf3);
      OLED2.drawStr( 0, 3 * LINESPACE + STARTSPACE, charBuf4);
      OLED2.drawStr( 0, 4 * LINESPACE + STARTSPACE, charBuf5);
    } while ( OLED2.nextPage() );
  }
  /*
    int mod = 0;
    if (screen == 0)mod = -1;
    oledFill(0x0, 1);
    oledWriteString(0, 5, 2 + mod, (char *)charBuf1, FONT_NORMAL, 0, 1);
    oledWriteString(0, 5, 3 + mod, (char *)charBuf2, FONT_NORMAL, 0, 1);
    oledWriteString(0, 5, 4 + mod, (char *)charBuf3, FONT_NORMAL, 0, 1);
    oledWriteString(0, 5, 5 + mod, (char *)charBuf4, FONT_NORMAL, 0, 1);
    oledWriteString(0, 5, 6 + mod, (char *)charBuf5, FONT_NORMAL, 0, 1);
    //Serial.println(text1);
    //Serial.println(text2);
    //Serial.println(text3);
    //Serial.println(text4);
    //Serial.println(text5);
    //
    //cmdMessenger.sendCmd(kAcknowledge, "screen set");
    //delay(100);
  */
}
