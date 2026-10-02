#pragma once

#include "config.h"

// HMC832 SPI and frequency control
void hmc832_sendBytes(uint32_t data, uint8_t addressByte);
void hmc832_Set_VCO_Out_Divider(int divisor);
void hmc832_Set_VCO_Frequency(int freqMHz);
void hmc832_Initialize_Microwave_Generator();

// Microwave testing and payload contrast sweep
void testMicrowave();
void runMicrowaveContrastSweep();
bool measureSingleFrequencyContrast(uint16_t freq_mhz, float& contrast_out);
