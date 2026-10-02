#include "config.h"

// Hardware bus instances
TwoWire BatMonI2C = TwoWire(0);
TwoWire ExtI2C = TwoWire(1);
HardwareSerial ExtUART(1);
SPIClass RTD_SPI(FSPI);

// System state flags
bool v5_enabled = false;
bool v10_enabled = false;
bool mic_enabled = false;
bool rtd_enabled = false;
bool batmon_enabled = false;
bool exti2c_enabled = false;
bool extuart_enabled = false;
bool microwave_inited = false;
bool photodiode_configured = false;

// NOTE: AD4130 IOUT0 can only be routed to certain AIN pins (typically 0–7).
// The configs with excitation_pin >7 may not be valid for IOUT0 and should
// be revisited once the exact board routing is confirmed.
RTDConfig rtd_configs[7] = {
  // RTD1-5 on Device 1 (increment by 3 pins each)
  { 0, 1, 2, 1, RTD_CS1, true },   // RTD1: AIN0(IOUT), AIN1(+), AIN2(-)
  { 3, 4, 5, 1, RTD_CS1, true },   // RTD2: AIN3(IOUT), AIN4(+), AIN5(-)
  { 6, 7, 8, 1, RTD_CS1, true },   // RTD3: AIN6(IOUT), AIN7(+), AIN8(-)
  { 9, 10, 11, 1, RTD_CS1, false },// RTD4: needs board/datasheet check
  { 12, 13, 14, 1, RTD_CS1, false },// RTD5: needs board/datasheet check
  // RTD6-7 on Device 2
  { 0, 1, 2, 2, RTD_CS2, false },  // RTD6: disabled by default
  { 3, 4, 5, 2, RTD_CS2, false }   // RTD7: disabled by default
};

// RTD calibration data
RTDCalibration rtd_cal[7] = {
  { 0.0, 1.0, false }, { 0.0, 1.0, false }, { 0.0, 1.0, false },
  { 0.0, 1.0, false }, { 0.0, 1.0, false }, { 0.0, 1.0, false },
  { 0.0, 1.0, false }
};
