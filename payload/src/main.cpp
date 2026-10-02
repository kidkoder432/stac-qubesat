#include "config.h"
#include "power.h"
#include "battery_monitor.h"
#include "ad4130.h"
#include "sensors.h"
#include "microwave.h"
#include "external_bus.h"
#include "command_interface.h"
#include "diagnostics.h"

// ======================= SETUP / LOOP =======================

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  Serial.println("\n=== Payload Board ESP32S3 Peripheral + Payload Test ===");
  Serial.println("Initializing all pins...");

  initializePins();
  printMenu();

  // External UART setup (PyCubed comms)
  Serial.println("\n--- Setting up UART ---");
  initExtUART();
  Serial.println("✓ UART initialized");
}

void loop() {
  // Service non-blocking incoming UART command packets from PyCubed
  checkUART();

  // Service interactive developer Serial console
  if (Serial.available()) {
    // Read ONE character and echo it for debugging
    char c = Serial.read();

    Serial.print("Received char: 0x");
    Serial.print((uint8_t)c, HEX);
    Serial.print(" ('");
    if (c >= 32 && c <= 126) Serial.print(c); else Serial.print('.');
    Serial.println("')");

    // Ignore line endings
    if (c == '\n' || c == '\r') {
      return;
    }

    switch (c) {
      case '1': toggle5V(); break;
      case '2': toggle10V(); break;
      case '3': testBatteryMonitor(); break;
      case '4': testRTD(); break;
      case '5': testMicrowave(); break;
      case '6': testExtI2C(); break;
      case '7': testExtUART(); break;
      case '8': toggleHeater(1); break;
      case '9': toggleHeater(2); break;
      case 'a': toggleHeater(3); break;
      case 'b': toggleHeater(4); break;
      case 'r': readAllRTDTemperatures(); break;
      case 'c': calibrateRTDs(); break;
      case 't': continuousRTDMonitoring(); break;
      case 'p': readPhotodiode(); break;
      case 's': showStatus(); break;
      case 'd': runFullDiagnostics(); break;
      case 'm': printMenu(); break;

      // Payload sweep
      case 'w':
        Serial.println("Command 'w' recognized, starting microwave contrast sweep...");
        runMicrowaveContrastSweep();
        break;

      // UART tests
      case 'y':
        Serial.println("Command 'y' recognized, sending photodiode data...");
        sendPhotodiodeData();
        break;
        
      case 'z':
        Serial.println("Command 'z' recognized, sending all RTD data...");
        sendRTDData();
        break;

      default:
        Serial.println("Unknown command. Press 'm' for menu.");
        break;
    }

    // Flush any extra characters in the buffer (like CR/LF combos)
    while (Serial.available()) Serial.read();
  }
}
