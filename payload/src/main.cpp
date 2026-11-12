#include "config.h"
#include "power.h"
#include "battery_monitor.h"
#include "ad4130.h"
#include "sensors.h"
#include "microwave.h"
#include "external_bus.h"
#include "command_interface.h"
#include "diagnostics.h"

// !! make sure to change this to 0 during handoff 
#define TESTING 1

// ======================= SETUP / LOOP =======================

void setup() {
  #if TESTING
  Serial.begin(115200);
  while (!Serial) {}
  #endif

  Serial.println("\n=== Payload Board ESP32S3 Peripheral + Payload Test ===");
  Serial.println("Initializing all pins...");

  initializePins();
  printMenu();

  // External UART setup (PyCubed comms)
  Serial.println("\n--- Setting up UART ---");
  initExtUART();
  Serial.println("✓ UART initialized");

  Serial.print("\npayload> ");
}

void loop() {
  // Service non-blocking incoming UART command packets from PyCubed
  checkUART();

  #if TESTING
  // Service interactive developer Serial console CLI
  handleDeveloperCLI();
#endif

  
}
