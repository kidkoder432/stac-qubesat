#pragma once

#include "config.h"

// ======================= AD4130 REGISTER MAP =======================

#define AD4130_REG_STATUS           0x00
#define AD4130_REG_ADC_CONTROL      0x01
#define AD4130_REG_DATA             0x02
#define AD4130_REG_IO_CONTROL_1     0x03
#define AD4130_REG_IO_CONTROL_2     0x04
#define AD4130_REG_ID               0x05
#define AD4130_REG_ERROR            0x06
#define AD4130_REG_ERROR_EN         0x07
#define AD4130_REG_MCLK_COUNT       0x08
#define AD4130_REG_CHANNEL_0        0x09
#define AD4130_REG_CONFIG_0         0x19
#define AD4130_REG_FILTER_0         0x21
#define AD4130_REG_OFFSET_0         0x29
#define AD4130_REG_GAIN_0           0x31
#define AD4130_REG_MISC             0x39
#define AD4130_REG_FIFO_CONTROL     0x3A
#define AD4130_REG_FIFO_STATUS      0x3B
#define AD4130_REG_FIFO_THRESHOLD   0x3C
#define AD4130_REG_FIFO_DATA        0x3D

// AD4130 Commands
#define AD4130_CMD_READ             0x40
#define AD4130_CMD_WRITE            0x00
#define AD4130_CMD_RESET            0xFF

// AD4130 mode bits (ADC_CONTROL MODE field)
#define AD4130_MODE_CONTINUOUS      0x00
#define AD4130_MODE_SINGLE_SEQ      0x01
#define AD4130_MODE_STANDBY         0x02
#define AD4130_MODE_IDLE            0x04

// Silicon ID bits (3:2) == 0b01 for AD4130 family
#define AD4130_SILICON_ID_EXPECTED  0x01

// ======================= AD4130 LOW LEVEL SPI FUNCTIONS =======================

void initRTDSPI();

uint8_t  ad4130_read_register(int cs_pin, uint8_t reg);
void     ad4130_write_register(int cs_pin, uint8_t reg, uint8_t data);
uint16_t ad4130_read_register_16(int cs_pin, uint8_t reg);
void     ad4130_write_register_16(int cs_pin, uint8_t reg, uint16_t data);
uint32_t ad4130_read_register_24(int cs_pin, uint8_t reg);
void     ad4130_write_register_24(int cs_pin, uint8_t reg, uint32_t data);
uint32_t ad4130_read_data(int cs_pin);

// Debugging and self-test
void testAD4130(int cs_pin, int int_pin, int device_num);
void debugAD4130Registers(int cs_pin, int device_num);
