#pragma once

#include "config.h"

// Initialize Battery Monitor I2C bus if not already initialized
bool initBatteryMonitor();

// Run diagnostic test on INA228
void testBatteryMonitor();

// Read bus voltage from INA228 (returns true on success)
bool readBatteryVoltage(uint32_t& raw_voltage);
