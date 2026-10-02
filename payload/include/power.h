#pragma once

#include "config.h"

// Pin setup for GPIOs, CS lines, heaters, and rail enables
void initializePins();

// Power rail controls
void toggle5V();
void toggle10V();
void set5V(bool enable);
void set10V(bool enable);

// Heater controls (heater_num 1..4 corresponding to IN1..IN4)
void toggleHeater(int heater_num);
void setHeater(int heater_num, bool enable);
