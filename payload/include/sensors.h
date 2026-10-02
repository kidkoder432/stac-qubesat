#pragma once

#include "config.h"
#include "ad4130.h"

// AD4130 sensor configuration
bool ad4130_configure_for_rtd_generic(int cs_pin, int device_num, int channel_num, RTDConfig& config);
bool ad4130_configure_for_rtd(int cs_pin, int device_num);
bool ad4130_configure_for_photodiode(int cs_pin, int device_num, int channel_num);

// Conversion math
float calculateRTDResistance(uint32_t adc_data);
float calculateTemperature(float resistance);
float calculatePhotocurrent(uint32_t adc_data);

// Sensor reading
bool readRTDSensorGeneric(int cs_pin, int device_num, int channel_num, float& temperature, float& resistance);
bool readRTDSensor(int cs_pin, int device_num, float& temperature, float& resistance);
bool readPhotodiodeSensor(int cs_pin, int device_num, int channel_num, float& photocurrent);
bool ensurePhotodiodeADCConfigured();
bool measurePhotodiodeOnce(float& photocurrent);

// High level & CLI routines
void readSingleRTD(int rtd_number);
void readAllRTDTemperatures();
void readPhotodiode();
void readRTDTemperatures();
void calibrateRTDs();
void continuousRTDMonitoring();
void testRTD();
