#pragma once

#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>

// ======================= PIN DEFINITIONS =======================

// RTD chip select
#define RTD_CS1         8
#define RTD_CS2         17

// RTD / ADC SPI pins (AD4130)
#define RTD_SCLK        9
#define RTD_DIN         10  // MOSI to AD4130
#define RTD_DOUT        5   // MISO from AD4130

// Power rails
#define V5_ENABLE       11
#define V10_ENABLE      12

// Microwave (HMC832 / EVAL-HMC832A) SPI & control
#define MIC_SCK         13
#define MIC_SDI         14   // MOSI to microwave module
#define MIC_SDO         6    // MISO from microwave module
#define MIC_SEN         18   // CS / SEN
#define MIC_REGEN       21   // regulator / enable

// Heater control pins
#define IN1             33
#define IN2             34
#define IN3             35
#define IN4             36

// External UART (PyCubed comms)
#define EXTUART_RX      37
#define EXTUART_TX      38

// External I2C
#define EXTI2C_SDA      1
#define EXTI2C_SCL      2

// Battery monitor I2C
#define BATMON_SDA      3
#define BATMON_SCL      4

// RTD interrupt pins
#define RTD_INT1        7
#define RTD_INT2        40

// I2C Addresses
#define INA228_ADDR     0x41

// ======================= RTD / PHOTODIODE CONFIG =======================

#define RTD_REFERENCE_RESISTOR      16200.0  // 16.2kΩ in ohms
#define PT1000_R0                   1000.0   // PT1000 resistance at 0°C
#define PT1000_ALPHA                0.003851 // Temperature coefficient

struct RTDConfig {
  uint8_t excitation_pin;  // AIN pin for excitation current (IOUT)
  uint8_t positive_pin;    // AIN pin for RTD+ (connected to excitation)
  uint8_t negative_pin;    // AIN pin for RTD- (sense pin)
  uint8_t device_num;      // AD4130 device number (1 or 2)
  int cs_pin;              // Chip select pin for this device
  bool enabled;            // Whether this RTD is enabled
};

struct RTDCalibration {
  float offset;
  float gain;
  bool valid;
};

// Photodiode Configuration
#define PHOTODIODE_DEVICE       2        // Device 2 handles photodiode
#define PHOTODIODE_AIN          15       // AIN15 for photodiode
#define PHOTODIODE_TIA_RESISTOR 100000.0 // 100kΩ transimpedance resistor

// ======================= GLOBAL HARDWARE BUSES & STATE =======================

extern TwoWire BatMonI2C;
extern TwoWire ExtI2C;
extern HardwareSerial ExtUART;
extern SPIClass RTD_SPI;

// State flags
extern bool v5_enabled;
extern bool v10_enabled;
extern bool mic_enabled;
extern bool rtd_enabled;
extern bool batmon_enabled;
extern bool exti2c_enabled;
extern bool extuart_enabled;
extern bool microwave_inited;
extern bool photodiode_configured;

// RTD configs and calibration tables
extern RTDConfig rtd_configs[7];
extern RTDCalibration rtd_cal[7];
