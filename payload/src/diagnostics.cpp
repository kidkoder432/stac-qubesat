#include "diagnostics.h"
#include "power.h"
#include "battery_monitor.h"
#include "sensors.h"
#include "microwave.h"
#include "external_bus.h"

void printMenu() {
  Serial.println("\n=== PERIPHERAL CONTROL MENU ===");
  Serial.println("Power Controls:");
  Serial.println("  1 - Toggle 5V Rail");
  Serial.println("  2 - Toggle 10V Rail");
  Serial.println("\nPeripherals:");
  Serial.println("  3 - Test Battery Monitor (INA228)");
  Serial.println("  4 - Test RTD (AD4130) - Basic");
  Serial.println("  5 - Test Microwave Module");
  Serial.println("  6 - Test External I2C");
  Serial.println("  7 - Test External UART");
  Serial.println("\nRTD Functions:");
  Serial.println("  r  - Read All RTD Temperatures");
  Serial.println("  r1-r7 - Read Individual RTD (e.g., 'r1' for RTD1)");
  Serial.println("  c  - Calibrate RTDs");
  Serial.println("  t  - Continuous RTD Monitoring");
  Serial.println("  p  - Read Photodiode (AIN15)");
  Serial.println("\nPayload:");
  Serial.println("  w  - Run Microwave Frequency Sweep (contrast scan)");
  Serial.println("\nHeater Controls:");
  Serial.println("  8 - Toggle Heater IN1");
  Serial.println("  9 - Toggle Heater IN2");
  Serial.println("  a - Toggle Heater IN3");
  Serial.println("  b - Toggle Heater IN4");
  Serial.println("\nDiagnostics:");
  Serial.println("  s - Show Status");
  Serial.println("  d - Run Full Diagnostics");
  Serial.println("  m - Show Menu");
  Serial.println("\nUART:");
  Serial.println("  y - Send Photodiode Data (Legacy)");
  Serial.println("  z - Send All RTD Temperatures (Legacy)");
  Serial.println("\nEnter command:");
}

void showStatus() {
  Serial.println("\n=== CURRENT STATUS ===");

  Serial.println("Power Rails:");
  Serial.printf("  5V Rail:  %s\n", v5_enabled ? "ENABLED" : "DISABLED");
  Serial.printf("  10V Rail: %s\n", v10_enabled ? "ENABLED" : "DISABLED");

  Serial.println("Heaters:");
  Serial.printf("  IN1: %s\n", digitalRead(IN1) ? "ON" : "OFF");
  Serial.printf("  IN2: %s\n", digitalRead(IN2) ? "ON" : "OFF");
  Serial.printf("  IN3: %s\n", digitalRead(IN3) ? "ON" : "OFF");
  Serial.printf("  IN4: %s\n", digitalRead(IN4) ? "ON" : "OFF");

  Serial.println("Peripherals:");
  Serial.printf("  Battery Monitor: %s\n", batmon_enabled ? "INIT" : "NOT INIT");
  Serial.printf("  RTD ADCs:        %s\n", rtd_enabled ? "INIT" : "NOT INIT");
  Serial.printf("  Microwave:       %s\n", mic_enabled ? "INIT" : "NOT INIT");
  Serial.printf("  External I2C:    %s\n", exti2c_enabled ? "INIT" : "NOT INIT");
  Serial.printf("  External UART:   %s\n", extuart_enabled ? "INIT" : "NOT INIT");

  Serial.println("RTD Configuration & Calibration:");
  for (int i = 0; i < 7; i++) {
    RTDConfig& config = rtd_configs[i];
    Serial.printf("  RTD #%d: %s, Device %d, Pins[%d/%d/%d], Cal[offset=%.2f, gain=%.3f]\n",
      i + 1,
      config.enabled ? "ENABLED" : "DISABLED",
      config.device_num,
      config.excitation_pin, config.positive_pin, config.negative_pin,
      rtd_cal[i].offset, rtd_cal[i].gain);
  }

  Serial.printf("Photodiode: Device %d, AIN%d, TIA=%.0fkΩ\n",
    PHOTODIODE_DEVICE, PHOTODIODE_AIN, PHOTODIODE_TIA_RESISTOR / 1000.0);

  Serial.println("Critical Pin States:");
  Serial.printf("  RTD_INT1: %s\n", digitalRead(RTD_INT1) ? "HIGH" : "LOW");
  Serial.printf("  RTD_INT2: %s\n", digitalRead(RTD_INT2) ? "HIGH" : "LOW");
  Serial.printf("  MIC_REGEN: %s\n", digitalRead(MIC_REGEN) ? "HIGH" : "LOW");
}

void runFullDiagnostics() {
  Serial.println("\n=== FULL DIAGNOSTICS ===");

  Serial.println("1. Enabling power rails...");
  if (!v5_enabled) toggle5V();
  if (!v10_enabled) toggle10V();
  delay(500);

  Serial.println("2. Testing all peripherals...");
  testBatteryMonitor();
  testRTD();
  testMicrowave();
  testExtI2C();
  testExtUART();

  Serial.println("3. Reading RTD temperatures and photodiode...");
  readAllRTDTemperatures();
  readPhotodiode();

  Serial.println("4. Final status:");
  showStatus();

  Serial.println("\n=== DIAGNOSTICS COMPLETE ===");
}
