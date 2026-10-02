#include "battery_monitor.h"

bool initBatteryMonitor() {
  if (!batmon_enabled) {
    BatMonI2C.begin(BATMON_SDA, BATMON_SCL, 100000);
    batmon_enabled = true;
    delay(100);
  }
  return true;
}

bool readBatteryVoltage(uint32_t& raw_voltage) {
  initBatteryMonitor();

  BatMonI2C.beginTransmission(INA228_ADDR);
  BatMonI2C.write(0x05); // Bus voltage register
  if (BatMonI2C.endTransmission() != 0) {
    return false;
  }

  if (BatMonI2C.requestFrom(INA228_ADDR, 3) != 3) {
    return false;
  }

  raw_voltage = ((uint32_t)BatMonI2C.read() << 16) |
                ((uint32_t)BatMonI2C.read() << 8) |
                BatMonI2C.read();
  return true;
}

void testBatteryMonitor() {
  Serial.println("\n--- Battery Monitor Test (INA228) ---");

  initBatteryMonitor();

  BatMonI2C.beginTransmission(INA228_ADDR);
  BatMonI2C.write(0x3F); // Device ID register
  if (BatMonI2C.endTransmission() == 0) {
    if (BatMonI2C.requestFrom(INA228_ADDR, 2) == 2) {
      uint16_t deviceID = (BatMonI2C.read() << 8) | BatMonI2C.read();
      Serial.printf("✓ INA228 Device ID: 0x%04X\n", deviceID);

      uint32_t voltage = 0;
      if (readBatteryVoltage(voltage)) {
        Serial.printf("✓ Bus Voltage: Raw=0x%06X\n", voltage);
      } else {
        Serial.println("✗ Failed to read bus voltage");
      }
    } else {
      Serial.println("✗ Failed to read device ID");
    }
  } else {
    Serial.println("✗ INA228 not responding - Check:");
    Serial.println("  - Power supply");
    Serial.println("  - I2C connections (SDA=3, SCL=4)");
    Serial.println("  - Pull-up resistors");
  }
}
