#include "diagnostics.h"
#include "power.h"
#include "battery_monitor.h"
#include "sensors.h"
#include "microwave.h"
#include "external_bus.h"
#include "command_interface.h"

void printMenu() {
  Serial.println("\n====================== PAYLOAD DEVELOPER CONSOLE ======================");
  Serial.println("Commands can be typed in full (e.g., 'rtd 1') or via quick shortcuts.");
  Serial.println("-----------------------------------------------------------------------");
  Serial.println("[POWER]");
  Serial.println("  pwr 5 [on|off]           - Turn 5V rail on/off       (shortcut: '1' toggle)");
  Serial.println("  pwr 10 [on|off]          - Turn 10V rail on/off      (shortcut: '2' toggle)");
  Serial.println("  pwr status               - Show rail states");
  Serial.println("\n[HEATERS]");
  Serial.println("  heat <1..4> [on|off]     - Set heater channel state  (shortcut: '8'..'b')");
  Serial.println("  heat all <on|off>        - Turn all heaters on/off");
  Serial.println("\n[SENSORS]");
  Serial.println("  rtd [all]                - Read all 7 RTD sensors    (shortcut: 'r')");
  Serial.println("  rtd <1..7>               - Read single RTD sensor    (shortcut: 'r1'..'r7')");
  Serial.println("  rtd cal                  - Calibrate RTDs            (shortcut: 'c')");
  Serial.println("  rtd mon                  - Continuous RTD stream     (shortcut: 't')");
  Serial.println("  pd                       - Read photodiode current   (shortcut: 'p')");
  Serial.println("  bat                      - Read INA228 bat monitor   (shortcut: '3')");
  Serial.println("\n[MICROWAVE / ODMR]");
  Serial.println("  mw test                  - Test synthesizer SPI      (shortcut: '5')");
  Serial.println("  mw freq <MHz>            - Set arbitrary VCO freq (25-3000 MHz)");
  Serial.println("  mw point <MHz>           - Measure ODMR point contrast (Cmd '4', 2800-2950)");
  Serial.println("  mw sweep                 - Full 151-pt sweep         (shortcut: 'w')");
  Serial.println("\n[COMMUNICATION]");
  Serial.println("  i2c                      - Scan external I2C bus     (shortcut: '6')");
  Serial.println("  uart test                - Test PyCubed UART link    (shortcut: '7')");
  Serial.println("  uart send <text>         - Send raw text to PyCubed  (or 'u:<text>')");
  Serial.println("  uart sim pd              - Send PD packet to PyCubed (shortcut: 'y')");
  Serial.println("  uart sim rtd             - Send RTD packet to PyCubed(shortcut: 'z')");
  Serial.println("\n[SYSTEM]");
  Serial.println("  status / s               - Display system dashboard");
  Serial.println("  diag / d                 - Run full automated self-test");
  Serial.println("  reset / reboot           - Restart ESP32");
  Serial.println("  help / m                 - Show this menu");
  Serial.println("=======================================================================");
}

void showStatus() {
  Serial.println("\n========================= SYSTEM DASHBOARD =========================");

  Serial.printf("Uptime: %lu s | Free Heap: %u bytes\n", millis() / 1000, ESP.getFreeHeap());

  Serial.println("\n[Power Rails & Heaters]");
  Serial.printf("  5V Rail:       %-8s | 10V Rail:      %s\n",
    v5_enabled ? "ENABLED" : "DISABLED",
    v10_enabled ? "ENABLED" : "DISABLED");
  Serial.printf("  Heater IN1:    %-8s | Heater IN2:    %s\n",
    digitalRead(IN1) ? "ON" : "OFF", digitalRead(IN2) ? "ON" : "OFF");
  Serial.printf("  Heater IN3:    %-8s | Heater IN4:    %s\n",
    digitalRead(IN3) ? "ON" : "OFF", digitalRead(IN4) ? "ON" : "OFF");

  Serial.println("\n[Battery Monitor (INA228)]");
  uint32_t raw_v = 0;
  if (readBatteryVoltage(raw_v)) {
    float vbus = (float)raw_v * 195.3125e-6f;
    Serial.printf("  Status: OK | Bus Voltage: %.3f V (raw: 0x%06X)\n", vbus, raw_v);
  } else {
    Serial.printf("  Status: %s\n", batmon_enabled ? "Read failed" : "Not initialized");
  }

  Serial.println("\n[Peripheral Status]");
  Serial.printf("  RTD ADCs:      %-10s | Microwave (HMC832): %s\n",
    rtd_enabled ? "INIT" : "NOT INIT", mic_enabled ? "INIT" : "NOT INIT");
  Serial.printf("  External I2C:  %-10s | External UART:     %s\n",
    exti2c_enabled ? "INIT" : "NOT INIT", extuart_enabled ? "INIT" : "NOT INIT");

  Serial.println("\n[Critical Pin States]");
  Serial.printf("  RTD_INT1: %-4s | RTD_INT2: %-4s | MIC_REGEN: %s\n",
    digitalRead(RTD_INT1) ? "HIGH" : "LOW",
    digitalRead(RTD_INT2) ? "HIGH" : "LOW",
    digitalRead(MIC_REGEN) ? "HIGH" : "LOW");

  Serial.println("\n[RTD Configurations]");
  for (int i = 0; i < 7; i++) {
    RTDConfig& config = rtd_configs[i];
    Serial.printf("  RTD #%d: %-8s | Dev %d | AIN%d->[+%d/-%d] | Cal[ofs=%+.2f, gain=%.3f]\n",
      i + 1,
      config.enabled ? "ENABLED" : "DISABLED",
      config.device_num,
      config.excitation_pin, config.positive_pin, config.negative_pin,
      rtd_cal[i].offset, rtd_cal[i].gain);
  }

  Serial.printf("\n[Photodiode Config]: Dev %d, AIN%d, TIA = %.0f kΩ\n",
    PHOTODIODE_DEVICE, PHOTODIODE_AIN, PHOTODIODE_TIA_RESISTOR / 1000.0);
  Serial.println("====================================================================");
}

void runFullDiagnostics() {
  Serial.println("\n====================== FULL DIAGNOSTICS ======================");

  Serial.println("Step 1: Enabling power rails...");
  if (!v5_enabled) set5V(true);
  if (!v10_enabled) set10V(true);
  delay(500);

  Serial.println("\nStep 2: Testing peripherals...");
  testBatteryMonitor();
  testRTD();
  testMicrowave();
  testExtI2C();
  testExtUART();

  Serial.println("\nStep 3: Sampling sensors...");
  readAllRTDTemperatures();
  readPhotodiode();

  Serial.println("\nStep 4: System summary:");
  showStatus();

  Serial.println("\n==================== DIAGNOSTICS COMPLETE ====================");
}

void processDeveloperCommand(String cmdLine) {
  cmdLine.trim();
  if (cmdLine.length() == 0) return;

  // Check legacy 'u:<msg>' shortcut
  if (cmdLine.startsWith("u:") || cmdLine.startsWith("U:")) {
    String msg = cmdLine.substring(2);
    initExtUART();
    ExtUART.println(msg);
    Serial.printf("✓ Sent to PyCubed UART: \"%s\"\n", msg.c_str());
    return;
  }

  // Tokenize command line into tokens
  int firstSpace = cmdLine.indexOf(' ');
  String cmd = (firstSpace == -1) ? cmdLine : cmdLine.substring(0, firstSpace);
  String remainder = (firstSpace == -1) ? "" : cmdLine.substring(firstSpace + 1);
  remainder.trim();

  int secondSpace = remainder.indexOf(' ');
  String arg1 = (secondSpace == -1) ? remainder : remainder.substring(0, secondSpace);
  String arg2 = (secondSpace == -1) ? "" : remainder.substring(secondSpace + 1);
  arg2.trim();

  String cmdLower = cmd;
  cmdLower.toLowerCase();
  String arg1Lower = arg1;
  arg1Lower.toLowerCase();
  String arg2Lower = arg2;
  arg2Lower.toLowerCase();

  // ---------------- SINGLE-CHAR SHORTCUTS ----------------
  if (cmdLine.length() == 1) {
    char c = cmdLine[0];
    switch (c) {
      case '1': toggle5V(); return;
      case '2': toggle10V(); return;
      case '3': testBatteryMonitor(); return;
      case '4': testRTD(); return;
      case '5': testMicrowave(); return;
      case '6': testExtI2C(); return;
      case '7': testExtUART(); return;
      case '8': toggleHeater(1); return;
      case '9': toggleHeater(2); return;
      case 'a': case 'A': toggleHeater(3); return;
      case 'b': case 'B': toggleHeater(4); return;
      case 'r': case 'R': readAllRTDTemperatures(); return;
      case 'c': case 'C': calibrateRTDs(); return;
      case 't': case 'T': continuousRTDMonitoring(); return;
      case 'p': case 'P': readPhotodiode(); return;
      case 'w': case 'W': runMicrowaveContrastSweep(); return;
      case 's': case 'S': showStatus(); return;
      case 'd': case 'D': runFullDiagnostics(); return;
      case 'm': case 'M': case '?': printMenu(); return;
      case 'y': case 'Y': sendPhotodiodeData(); return;
      case 'z': case 'Z': sendRTDData(); return;
    }
  }

  // ---------------- SHORTCUT 'r1'..'r7' ----------------
  if (cmdLower.length() == 2 && cmdLower[0] == 'r' && cmdLower[1] >= '1' && cmdLower[1] <= '7') {
    int rtd_num = cmdLower[1] - '0';
    readSingleRTD(rtd_num);
    return;
  }

  // ---------------- GENERAL COMMANDS ----------------
  if (cmdLower == "help" || cmdLower == "menu" || cmdLower == "?") {
    printMenu();
  }
  else if (cmdLower == "status" || cmdLower == "s") {
    showStatus();
  }
  else if (cmdLower == "diag" || cmdLower == "d") {
    runFullDiagnostics();
  }
  else if (cmdLower == "reset" || cmdLower == "reboot") {
    Serial.println("Rebooting ESP32...");
    delay(200);
    ESP.restart();
  }
  // ---------------- POWER ----------------
  else if (cmdLower == "pwr" || cmdLower == "power") {
    if (arg1Lower == "5") {
      if (arg2Lower == "on") set5V(true);
      else if (arg2Lower == "off") set5V(false);
      else toggle5V();
    }
    else if (arg1Lower == "10") {
      if (arg2Lower == "on") set10V(true);
      else if (arg2Lower == "off") set10V(false);
      else toggle10V();
    }
    else if (arg1Lower == "status") {
      Serial.printf("5V Rail: %s | 10V Rail: %s\n",
        v5_enabled ? "ON" : "OFF", v10_enabled ? "ON" : "OFF");
    }
    else {
      Serial.println("Usage: pwr <5|10> [on|off] OR pwr status");
    }
  }
  // ---------------- HEATERS ----------------
  else if (cmdLower == "heat" || cmdLower == "heater") {
    if (arg1Lower == "all") {
      bool state = (arg2Lower == "on");
      for (int i = 1; i <= 4; i++) setHeater(i, state);
    }
    else {
      int h = arg1.toInt();
      if (h >= 1 && h <= 4) {
        if (arg2Lower == "on") setHeater(h, true);
        else if (arg2Lower == "off") setHeater(h, false);
        else toggleHeater(h);
      }
      else {
        Serial.println("Usage: heat <1..4|all> [on|off]");
      }
    }
  }
  // ---------------- RTD SENSORS ----------------
  else if (cmdLower == "rtd") {
    if (arg1Lower == "" || arg1Lower == "all") {
      readAllRTDTemperatures();
    }
    else if (arg1Lower == "cal") {
      calibrateRTDs();
    }
    else if (arg1Lower == "mon") {
      continuousRTDMonitoring();
    }
    else {
      int rtd_num = arg1.toInt();
      if (rtd_num >= 1 && rtd_num <= 7) {
        readSingleRTD(rtd_num);
      } else {
        Serial.println("Usage: rtd [all | 1..7 | cal | mon]");
      }
    }
  }
  // ---------------- PHOTODIODE & BATTERY ----------------
  else if (cmdLower == "pd" || cmdLower == "photo") {
    readPhotodiode();
  }
  else if (cmdLower == "bat" || cmdLower == "battery") {
    testBatteryMonitor();
  }
  // ---------------- MICROWAVE / ODMR ----------------
  else if (cmdLower == "mw" || cmdLower == "microwave") {
    if (arg1Lower == "test") {
      testMicrowave();
    }
    else if (arg1Lower == "freq") {
      int freq = arg2.toInt();
      if (freq >= 25 && freq <= 3000) {
        if (!v10_enabled) {
          Serial.println("Enabling 10V rail for microwave synthesizer...");
          set10V(true);
          delay(200);
        }
        digitalWrite(MIC_REGEN, HIGH);
        hmc832_Initialize_Microwave_Generator();
        hmc832_Set_VCO_Frequency(freq);
        Serial.printf("✓ Synthesizer frequency set to %d MHz\n", freq);
      } else {
        Serial.println("Frequency out of range. Valid: 25 - 3000 MHz.");
      }
    }
    else if (arg1Lower == "point") {
      int freq = arg2.toInt();
      if (freq >= 2800 && freq <= 2950) {
        Serial.printf("Measuring optical contrast at %d MHz...\n", freq);
        float contrast = 0.0f;
        if (measureSingleFrequencyContrast((uint16_t)freq, contrast)) {
          Serial.printf("✓ Contrast at %d MHz: %.4f\n", freq, contrast);
        } else {
          Serial.println("✗ Contrast measurement failed");
        }
      } else {
        Serial.println("Frequency out of range. Valid: 2800 - 2950 MHz.");
      }
    }
    else if (arg1Lower == "sweep") {
      runMicrowaveContrastSweep();
    }
    else {
      Serial.println("Usage: mw <test | freq <MHz> | point <MHz> | sweep>");
    }
  }
  // ---------------- I2C / UART COMMUNICATION ----------------
  else if (cmdLower == "i2c") {
    testExtI2C();
  }
  else if (cmdLower == "uart") {
    if (arg1Lower == "test") {
      testExtUART();
    }
    else if (arg1Lower == "send") {
      int sendPos = remainder.indexOf(' ');
      String msg = (sendPos == -1) ? "" : remainder.substring(sendPos + 1);
      msg.trim();
      initExtUART();
      ExtUART.println(msg);
      Serial.printf("✓ Sent to PyCubed UART: \"%s\"\n", msg.c_str());
    }
    else if (arg1Lower == "sim") {
      if (arg2Lower == "pd") {
        Serial.println("Simulating PyCubed PD response packet...");
        sendPhotodiodeData();
      }
      else if (arg2Lower == "rtd") {
        Serial.println("Simulating PyCubed RTD response packet...");
        sendRTDData();
      }
      else {
        Serial.println("Usage: uart sim <pd|rtd>");
      }
    }
    else {
      Serial.println("Usage: uart <test | send <text> | sim <pd|rtd>>");
    }
  }
  else {
    Serial.printf("Unknown command: \"%s\". Type 'help' or 'm' for menu.\n", cmd.c_str());
  }
}

void handleDeveloperCLI() {
  static String inputBuffer = "";

  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\r' || c == '\n') {
      if (inputBuffer.length() > 0) {
        Serial.println();
        processDeveloperCommand(inputBuffer);
        inputBuffer = "";
        Serial.print("\npayload> ");
      } else {
        Serial.print("\npayload> ");
      }
    }
    else if (c == '\b' || c == 0x7F) {
      if (inputBuffer.length() > 0) {
        inputBuffer.remove(inputBuffer.length() - 1);
        Serial.print("\b \b");
      }
    }
    else if (c >= 32 && c <= 126) {
      if (inputBuffer.length() < 120) {
        inputBuffer += c;
        Serial.print(c); // Echo character
      }
    }
  }
}
