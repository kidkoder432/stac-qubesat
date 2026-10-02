#pragma once

#include "config.h"

// ======================= PACKET FRAMING CONSTANTS =======================

#define PKT_START1           0x57
#define PKT_START2           0xAC

// Packet Types (Header Byte [2])
#define PKT_TYPE_DATA        0x01
#define PKT_TYPE_ACK         0x06
#define PKT_TYPE_NACK        0x15
#define PKT_TYPE_ERROR       0x20  // Payload reporting internal fault

// Command Types / IDs (Header Byte [2] from master, or first byte of command payload)
#define PKT_CMD_PING         0x08
#define PKT_CMD_READ_PD      0x10
#define PKT_CMD_READ_RTD     0x11
#define PKT_CMD_SWEEP        0x12
#define PKT_CMD_SET_RAIL     0x13
#define PKT_CMD_SET_HEATER   0x14
#define PKT_CMD_GET_STATUS   0x15

// Error Codes (Sent inside PKT_TYPE_ERROR or NACK payload)
enum PayloadErrorCode : uint8_t {
  ERR_NONE               = 0x00,
  ERR_BAD_CRC            = 0x01,  // UART CRC didn't match
  ERR_UNKNOWN_CMD        = 0x02,  // Unrecognized command byte
  ERR_RAIL_NOT_ENABLED   = 0x03,  // 5V or 10V rail was off / failed to power up
  ERR_AD4130_TIMEOUT     = 0x04,  // ADC conversion timed out
  ERR_AD4130_CONFIG_FAIL = 0x05,  // Silicon ID mismatch or register write failed
  ERR_MICROWAVE_FAIL     = 0x06,  // HMC832 lock/SPI failed
  ERR_INVALID_PARAM      = 0x07,  // Payload parameter out of range
  ERR_BUSY               = 0x08   // Busy running long task (e.g. sweep)
};

// ======================= PACKET TRANSMISSION =======================

uint16_t crc16_ccitt(const uint8_t* data, size_t len);
void sendPacket(uint8_t type, uint8_t seq, const uint8_t* payload, uint8_t len);
void sendACK(uint8_t seq);
void sendNACK(uint8_t seq, uint8_t err_code);
void sendError(uint8_t seq, uint8_t err_code);

// ======================= COMMAND DISPATCH & PROCESSING =======================

// Non-blocking parser called in loop() to read and process incoming PyCubed UART frames
void checkUART();

// Handlers called by packet dispatcher
void handleReadPDCommand(uint8_t seq);
void handleReadRTDCommand(uint8_t seq);
void handleSweepCommand(uint8_t seq);
void handlePingCommand(uint8_t seq);
void handleSetRailCommand(uint8_t seq, const uint8_t* payload, uint8_t len);
void handleSetHeaterCommand(uint8_t seq, const uint8_t* payload, uint8_t len);
void handleGetStatusCommand(uint8_t seq);

// Legacy string-framed UART functions for debugging
void sendPDOverUART(int cs_pin, int device_num, int channel_num);
void sendRTDOverUART();
