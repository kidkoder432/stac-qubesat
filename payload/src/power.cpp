#include "power.h"

void initializePins() {
  // Power control
  pinMode(V5_ENABLE, OUTPUT);
  pinMode(V10_ENABLE, OUTPUT);
  digitalWrite(V5_ENABLE, LOW);
  digitalWrite(V10_ENABLE, LOW);

  // RTD pins
  pinMode(RTD_CS1, OUTPUT);
  pinMode(RTD_CS2, OUTPUT);
  pinMode(RTD_INT1, INPUT_PULLUP);
  pinMode(RTD_INT2, INPUT_PULLUP);
  digitalWrite(RTD_CS1, HIGH);
  digitalWrite(RTD_CS2, HIGH);

  // MIC pins
  pinMode(MIC_SEN, OUTPUT);
  pinMode(MIC_REGEN, OUTPUT);
  digitalWrite(MIC_SEN, HIGH);
  digitalWrite(MIC_REGEN, LOW);

  // Heaters
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);

  Serial.println("✓ All pins initialized");
}

void set5V(bool enable) {
  v5_enabled = enable;
  digitalWrite(V5_ENABLE, v5_enabled ? HIGH : LOW);
  Serial.print("5V Rail: ");
  Serial.println(v5_enabled ? "ENABLED" : "DISABLED");
  delay(100);
}

void toggle5V() {
  set5V(!v5_enabled);
}

void set10V(bool enable) {
  v10_enabled = enable;
  digitalWrite(V10_ENABLE, v10_enabled ? HIGH : LOW);
  Serial.print("10V Rail: ");
  Serial.println(v10_enabled ? "ENABLED" : "DISABLED");
  delay(100);
}

void toggle10V() {
  set10V(!v10_enabled);
}

void setHeater(int heater_num, bool enable) {
  int pin = 0;
  switch (heater_num) {
    case 1: pin = IN1; break;
    case 2: pin = IN2; break;
    case 3: pin = IN3; break;
    case 4: pin = IN4; break;
    default:
      Serial.printf("Invalid heater number: %d (use 1-4)\n", heater_num);
      return;
  }

  digitalWrite(pin, enable ? HIGH : LOW);
  Serial.printf("Heater IN%d: %s\n", heater_num, enable ? "ON" : "OFF");
}

void toggleHeater(int heater_num) {
  int pin = 0;
  switch (heater_num) {
    case 1: pin = IN1; break;
    case 2: pin = IN2; break;
    case 3: pin = IN3; break;
    case 4: pin = IN4; break;
    default:
      Serial.printf("Invalid heater number: %d (use 1-4)\n", heater_num);
      return;
  }

  bool current_state = digitalRead(pin);
  setHeater(heater_num, !current_state);
}
