#pragma once

#include "config.h"

// ======================= PROTOCOL SIGNATURE & PACKET TYPES =======================

#define PKT_START1          0x57  // 'W'
#define PKT_START2          0xAC

// Packet Types / Responses
#define PKT_RESP_ACK        'A'   // 0x41: 4 bytes total
#define PKT_RESP_NACK       'N'   // 0x4E: 4 bytes total
#define PKT_RESP_ERROR      'E'   // 0x45: 6 bytes total
#define PKT_RESP_PD         'P'   // 0x50: 8 bytes total (4 float bytes)
#define PKT_RESP_RTD        'R'   // 0x52: 60 bytes total (56 float bytes)
#define PKT_RESP_STATUS     'S'   // 0x53: 10 bytes total (6 state bytes)
#define PKT_RESP_CONTRAST   'W'   // 0x57: 608 bytes total (604 uint32 bytes for 151 steps)

// Command Types (PyCubed -> ESP32, all 6 bytes total)
#define PKT_CMD_PING        '1'   // '1', 'H', 'B'
#define PKT_CMD_SET_RAIL    '2'   // '2', rail (0x00=5V, 0xFF=10V), state (0x00=OFF, 0xFF=ON)
#define PKT_CMD_SET_HEATER  '3'   // '3', heater (1..4), state (0x00=OFF, 0xFF=ON)
#define PKT_CMD_SWEEP       '4'   // '4', 'M', 'W'
#define PKT_CMD_GET_STATUS  '5'   // '5', 'G', 'S'
#define PKT_CMD_READ_PD     'P'   // 'P', 'P', 'D'
#define PKT_CMD_READ_RTD    'R'   // 'R', 'R', 'T'

// Error Codes
#define ERR_CODE_NONE           0x0000
#define ERR_CODE_BAD_CHECKSUM   0x0001
#define ERR_CODE_UNKNOWN_CMD    0x0002
#define ERR_CODE_RAIL_DISABLED  0x0003
#define ERR_CODE_ADC_TIMEOUT    0x0004
#define ERR_CODE_ADC_CONFIG     0x0005
#define ERR_CODE_MICROWAVE_FAIL 0x0006
#define ERR_CODE_INVALID_PARAM  0x0007

// ======================= FUNCTION PROTOTYPES =======================

// Checksum calculation (modulo 256 sum of all preceding bytes)
uint8_t calculateChecksum(const uint8_t* data, size_t len);

// Interface initialization and non-blocking service routine
void initCommandInterface();
void checkUART();

// Transmit response packets
void sendACK();
void sendNACK();
void sendError(uint16_t error_code);
void sendPhotodiodeData();
void sendRTDData();
void sendStatusData();
void sendContrastData(const float* contrast_arr, size_t count);
void sendContrastPoint(float contrast);
