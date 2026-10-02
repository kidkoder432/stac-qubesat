#include "command_interface.h"
#include "power.h"
#include "sensors.h"
#include "microwave.h"

// ======================= CHECKSUM =======================

uint8_t calculateChecksum(const uint8_t* data, size_t len) {
  uint8_t sum = 0;
  for (size_t i = 0; i < len; i++) {
    sum += data[i];
  }
  return sum;
}

// ======================= TRANSMIT FUNCTIONS =======================

void sendACK() {
  uint8_t pkt[4] = { PKT_START1, PKT_START2, PKT_RESP_ACK, 0 };
  pkt[3] = calculateChecksum(pkt, 3);
  ExtUART.write(pkt, 4);
}

void sendNACK() {
  uint8_t pkt[4] = { PKT_START1, PKT_START2, PKT_RESP_NACK, 0 };
  pkt[3] = calculateChecksum(pkt, 3);
  ExtUART.write(pkt, 4);
}

void sendError(uint16_t error_code) {
  uint8_t pkt[6] = {
    PKT_START1, PKT_START2, PKT_RESP_ERROR,
    (uint8_t)((error_code >> 8) & 0xFF),
    (uint8_t)(error_code & 0xFF),
    0
  };
  pkt[5] = calculateChecksum(pkt, 5);
  ExtUART.write(pkt, 6);
}

void sendPhotodiodeData() {
  if (!v5_enabled) {
    toggle5V();
    delay(200);
  }

  float photocurrent = 0.0f;
  if (measurePhotodiodeOnce(photocurrent)) {
    uint8_t pkt[8];
    pkt[0] = PKT_START1;
    pkt[1] = PKT_START2;
    pkt[2] = PKT_RESP_PD;
    memcpy(&pkt[3], &photocurrent, sizeof(photocurrent));
    pkt[7] = calculateChecksum(pkt, 7);
    ExtUART.write(pkt, 8);
  } else {
    sendError(ERR_CODE_ADC_TIMEOUT);
  }
}

void sendRTDData() {
  if (!v5_enabled) {
    toggle5V();
    delay(200);
  }

  initRTDSPI();

  float rtd_results[14] = {};
  bool any_success = false;

  for (int i = 0; i < 7; i++) {
    if (rtd_configs[i].enabled) {
      RTDConfig& config = rtd_configs[i];
      if (ad4130_configure_for_rtd_generic(config.cs_pin, config.device_num, 0, config)) {
        float temp = 0.0f, res = 0.0f;
        if (readRTDSensorGeneric(config.cs_pin, config.device_num, 0, temp, res)) {
          if (rtd_cal[i].valid) {
            temp = temp * rtd_cal[i].gain + rtd_cal[i].offset;
          }
          rtd_results[2 * i] = temp;
          rtd_results[2 * i + 1] = res;
          any_success = true;
        }
      }
      delay(20);
    }
  }

  if (any_success) {
    uint8_t pkt[60];
    pkt[0] = PKT_START1;
    pkt[1] = PKT_START2;
    pkt[2] = PKT_RESP_RTD;
    memcpy(&pkt[3], rtd_results, sizeof(rtd_results));
    pkt[59] = calculateChecksum(pkt, 59);
    ExtUART.write(pkt, 60);
  } else {
    sendError(ERR_CODE_ADC_TIMEOUT);
  }
}

void sendStatusData() {
  uint8_t pkt[10];
  pkt[0] = PKT_START1;
  pkt[1] = PKT_START2;
  pkt[2] = PKT_RESP_STATUS;
  pkt[3] = v5_enabled ? 1 : 0;
  pkt[4] = v10_enabled ? 1 : 0;
  pkt[5] = digitalRead(IN1) ? 1 : 0;
  pkt[6] = digitalRead(IN2) ? 1 : 0;
  pkt[7] = digitalRead(IN3) ? 1 : 0;
  pkt[8] = digitalRead(IN4) ? 1 : 0;
  pkt[9] = calculateChecksum(pkt, 9);
  ExtUART.write(pkt, 10);
}

void sendContrastData(const float* contrast_arr, size_t count) {
  // Transmit [0x57, 0xAC, 'W', ... 604 raw float bytes ..., Checksum]
  uint8_t cs = 0;

  ExtUART.write(PKT_START1);
  cs += PKT_START1;

  ExtUART.write(PKT_START2);
  cs += PKT_START2;

  ExtUART.write(PKT_RESP_CONTRAST);
  cs += PKT_RESP_CONTRAST;

  size_t payload_bytes = count * sizeof(float);
  const uint8_t* raw = (const uint8_t*)contrast_arr;

  for (size_t i = 0; i < payload_bytes; i++) {
    ExtUART.write(raw[i]);
    cs += raw[i];
  }

  ExtUART.write(cs);
}

void sendContrastPoint(float contrast) {
  // Transmit 8 bytes: [0x57, 0xAC, 'W', (4 bytes float), Checksum]
  uint8_t pkt[8];
  pkt[0] = PKT_START1;
  pkt[1] = PKT_START2;
  pkt[2] = PKT_RESP_CONTRAST;

  uint8_t* raw = (uint8_t*)&contrast;
  pkt[3] = raw[0];
  pkt[4] = raw[1];
  pkt[5] = raw[2];
  pkt[6] = raw[3];

  pkt[7] = calculateChecksum(pkt, 7);
  ExtUART.write(pkt, 8);
}

// ======================= NON-BLOCKING RING BUFFER =======================

#define RING_BUF_SIZE 256
static uint8_t ring_buf[RING_BUF_SIZE];
static size_t ring_head = 0;
static size_t ring_tail = 0;

static inline size_t ring_count() {
  return (ring_head >= ring_tail) ? (ring_head - ring_tail) : (RING_BUF_SIZE - ring_tail + ring_head);
}

static inline void ring_push(uint8_t b) {
  size_t next_head = (ring_head + 1) % RING_BUF_SIZE;
  if (next_head != ring_tail) {
    ring_buf[ring_head] = b;
    ring_head = next_head;
  }
}

static inline uint8_t ring_peek(size_t offset) {
  return ring_buf[(ring_tail + offset) % RING_BUF_SIZE];
}

static inline void ring_pop_n(size_t n) {
  ring_tail = (ring_tail + n) % RING_BUF_SIZE;
}

void initCommandInterface() {
  if (!extuart_enabled) {
    ExtUART.begin(115200, SERIAL_8N1, EXTUART_RX, EXTUART_TX);
    extuart_enabled = true;
    delay(50);
  }
}

void checkUART() {
  initCommandInterface();

  // 1. Ingest all available bytes from serial into ring buffer
  while (ExtUART.available() > 0) {
    ring_push(ExtUART.read());
  }

  // 2. Parse fixed 6-byte command packets from ring buffer
  while (ring_count() >= 6) {
    // Check for 2-byte header [0x57, 0xAC]
    if (ring_peek(0) != PKT_START1) {
      ring_pop_n(1);
      continue;
    }
    if (ring_peek(1) != PKT_START2) {
      ring_pop_n(1);
      continue;
    }

    // Copy 6 candidate bytes
    uint8_t cmd_pkt[6];
    for (size_t i = 0; i < 6; i++) {
      cmd_pkt[i] = ring_peek(i);
    }

    // Verify 1-byte modulo-256 checksum across first 5 bytes
    uint8_t computed_cs = calculateChecksum(cmd_pkt, 5);
    uint8_t received_cs = cmd_pkt[5];

    if (computed_cs != received_cs) {
      Serial.printf("ExtUART: Checksum mismatch! Expected: 0x%02X, Received: 0x%02X\n",
        computed_cs, received_cs);
      sendNACK();
      ring_pop_n(2); // Advance past header and try again
      continue;
    }

    // Checksum verified! Consume packet from ring buffer
    ring_pop_n(6);

    uint8_t cmd_type = cmd_pkt[2];
    uint8_t d0       = cmd_pkt[3];
    uint8_t d1       = cmd_pkt[4];

    Serial.printf("ExtUART command recognized: '%c' (0x%02X), d0=0x%02X, d1=0x%02X\n",
      cmd_type, cmd_type, d0, d1);

    switch (cmd_type) {
      case PKT_CMD_PING: // '1'
        sendACK();
        break;

      case PKT_CMD_SET_RAIL: { // '2'
        bool state = (d1 == 0xFF);
        if (d0 == 0x00) {
          set5V(state);
          sendACK();
        } else if (d0 == 0xFF) {
          set10V(state);
          sendACK();
        } else {
          sendError(ERR_CODE_INVALID_PARAM);
        }
        break;
      }

      case PKT_CMD_SET_HEATER: { // '3'
        uint8_t heater_num = d0;
        bool state = (d1 == 0xFF);
        if (heater_num >= 1 && heater_num <= 4) {
          setHeater(heater_num, state);
          sendACK();
        } else {
          sendError(ERR_CODE_INVALID_PARAM);
        }
        break;
      }

      case PKT_CMD_SWEEP: { // '4'
        uint16_t freq_mhz = ((uint16_t)d0 << 8) | (uint16_t)d1;
        if (freq_mhz >= 2800 && freq_mhz <= 2950) {
          float contrast = 0.0f;
          if (measureSingleFrequencyContrast(freq_mhz, contrast)) {
            sendContrastPoint(contrast);
          } else {
            sendError(ERR_CODE_MICROWAVE_FAIL);
          }
        } else if (d0 == 'M' && d1 == 'W') {
          // Legacy full sweep compatibility
          sendACK();
          runMicrowaveContrastSweep();
        } else {
          Serial.printf("ExtUART: Invalid sweep frequency: %u MHz\n", freq_mhz);
          sendError(ERR_CODE_INVALID_PARAM);
        }
        break;
      }

      case PKT_CMD_GET_STATUS: // '5'
        sendStatusData();
        break;

      case PKT_CMD_READ_PD: // 'P'
        sendPhotodiodeData();
        break;

      case PKT_CMD_READ_RTD: // 'R'
        sendRTDData();
        break;

      default:
        Serial.printf("ExtUART: Unknown command: 0x%02X\n", cmd_type);
        sendError(ERR_CODE_UNKNOWN_CMD);
        break;
    }
  }
}
