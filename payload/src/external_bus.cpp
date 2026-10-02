#include "external_bus.h"

void initExtI2C() {
  if (!exti2c_enabled) {
    ExtI2C.begin(EXTI2C_SDA, EXTI2C_SCL, 100000);
    exti2c_enabled = true;
    delay(100);
  }
}

void initExtUART() {
  if (!extuart_enabled) {
    ExtUART.begin(115200, SERIAL_8N1, EXTUART_RX, EXTUART_TX);
    extuart_enabled = true;
    delay(100);
  }
}

void testExtI2C() {
  Serial.println("\n--- External I2C Test ---");

  initExtI2C();

  Serial.println("Scanning I2C bus...");
  int devices = 0;

  for (int addr = 1; addr < 127; addr++) {
    ExtI2C.beginTransmission(addr);
    if (ExtI2C.endTransmission() == 0) {
      Serial.printf("  ✓ Device found at 0x%02X\n", addr);
      devices++;
    }
  }

  if (devices == 0) {
    Serial.println("  No devices found");
    Serial.println("  Check:");
    Serial.println("  - Pull-up resistors");
    Serial.println("  - Device connections");
    Serial.println("  - Device power");
  }
  else {
    Serial.printf("  Found %d device(s)\n", devices);
  }

  Serial.println("Test write/read (if devices present):");
  for (int addr = 1; addr < 127; addr++) {
    ExtI2C.beginTransmission(addr);
    ExtI2C.write(0x00);
    if (ExtI2C.endTransmission() == 0) {
      if (ExtI2C.requestFrom(addr, 1) == 1) {
        uint8_t data = ExtI2C.read();
        Serial.printf("  0x%02X: wrote 0x00, read 0x%02X\n", addr, data);
      }
    }
  }
}

void testExtUART() {
  Serial.println("\n--- External UART Test ---");

  initExtUART();

  Serial.println("Sending test message...");
  ExtUART.println("ESP32 Test Message");

  Serial.println("Listening for 2 seconds...");
  unsigned long start = millis();
  bool received = false;

  while (millis() - start < 2000) {
    if (ExtUART.available()) {
      Serial.print("Received: ");
      while (ExtUART.available()) {
        Serial.write(ExtUART.read());
        received = true;
      }
      Serial.println();
    }
  }

  if (!received) {
    Serial.println("No response received");
    Serial.println("Check:");
    Serial.println("  - UART connections (RX=37, TX=38)");
    Serial.println("  - External device");
    Serial.println("  - Baud rate match");
  }

  Serial.println("You can send data to external UART by typing 'u:<message>'");
}
