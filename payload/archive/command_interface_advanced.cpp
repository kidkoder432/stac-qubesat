#include "command_interface.h"
#include "power.h"
#include "sensors.h"
#include "microwave.h"
#include "ad4130.h"

// ======================= CRC & PACKET ENCODING =======================

uint16_t crc16_ccitt(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= ((uint16_t)data[i]) << 8;
    for (uint8_t b = 0; b < 8; b++) {
      if (crc & 0x8000) crc = (crc << 1) ^ 0x1021;
      else              crc = crc << 1;
    }
  }
  return crc;
}

void sendPacket(uint8_t type, uint8_t seq, const uint8_t* payload, uint8_t len) {
  uint8_t frame[260];

  frame[0] = PKT_START1;
  frame[1] = PKT_START2;
  frame[2] = type;
  frame[3] = seq;
  frame[4] = len;

  if (payload != nullptr && len > 0) {
    memcpy(&frame[5], payload, len);
  }

  // Calculate CRC over bytes 0 through (4 + len)
  uint16_t crc = crc16_ccitt(frame, 5 + len);
  frame[5 + len] = (crc >> 8) & 0xFF;  // MSB
  frame[6 + len] = crc & 0xFF;         // LSB

  if (!extuart_enabled) {
    ExtUART.begin(115200, SERIAL_8N1, EXTUART_RX, EXTUART_TX);
    extuart_enabled = true;
  }

  ExtUART.write(frame, 7 + len);
}

void sendACK(uint8_t seq) {
  sendPacket(PKT_TYPE_ACK, seq, nullptr, 0);
}

void sendNACK(uint8_t seq, uint8_t err_code) {
  sendPacket(PKT_TYPE_NACK, seq, &err_code, 1);
}

void sendError(uint8_t seq, uint8_t err_code) {
  sendPacket(PKT_TYPE_ERROR, seq, &err_code, 1);
}

// ======================= COMMAND HANDLERS =======================

void handlePingCommand(uint8_t seq) {
  Serial.printf("UART: Received PING (seq=%u), responding ACK\n", seq);
  sendACK(seq);
}

void handleReadPDCommand(uint8_t seq) {
  Serial.printf("UART: Received CMD_READ_PD (seq=%u)\n", seq);

  if (!v5_enabled) {
    toggle5V();
    delay(200);
  }

  float photocurrent = 0.0f;
  if (measurePhotodiodeOnce(photocurrent)) {
    Serial.printf("  ✓ Photodiode read success: %.3f nA\n", photocurrent * 1e9);
    sendPacket(PKT_TYPE_DATA, seq, (const uint8_t*)&photocurrent, sizeof(photocurrent));
  } else {
    Serial.println("  ✗ Photodiode read failed");
    sendError(seq, ERR_AD4130_TIMEOUT);
  }
}

void handleReadRTDCommand(uint8_t seq) {
  Serial.printf("UART: Received CMD_READ_RTD (seq=%u)\n", seq);

  if (!v5_enabled) {
    toggle5V();
    delay(200);
  }

  initRTDSPI();

  float rtd_results[14] = {}; // 7 pairs of [temp, res]
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
    Serial.println("  ✓ Sending RTD data packet (14 floats)");
    sendPacket(PKT_TYPE_DATA, seq, (const uint8_t*)rtd_results, sizeof(rtd_results));
  } else {
    Serial.println("  ✗ All RTD readings failed");
    sendError(seq, ERR_AD4130_TIMEOUT);
  }
}

void handleSweepCommand(uint8_t seq) {
  Serial.printf("UART: Received CMD_SWEEP (seq=%u)\n", seq);
  sendACK(seq);
  runMicrowaveContrastSweep();
}

void handleSetRailCommand(uint8_t seq, const uint8_t* payload, uint8_t len) {
  if (len < 2) {
    sendNACK(seq, ERR_INVALID_PARAM);
    return;
  }

  uint8_t rail = payload[0];
  bool state = (payload[1] != 0);

  Serial.printf("UART: Set Rail %dV to %s\n", rail, state ? "ON" : "OFF");
  if (rail == 5) {
    set5V(state);
    sendACK(seq);
  } else if (rail == 10) {
    set10V(state);
    sendACK(seq);
  } else {
    sendNACK(seq, ERR_INVALID_PARAM);
  }
}

void handleSetHeaterCommand(uint8_t seq, const uint8_t* payload, uint8_t len) {
  if (len < 2) {
    sendNACK(seq, ERR_INVALID_PARAM);
    return;
  }

  uint8_t heater_num = payload[0];
  bool state = (payload[1] != 0);

  if (heater_num < 1 || heater_num > 4) {
    sendNACK(seq, ERR_INVALID_PARAM);
    return;
  }

  Serial.printf("UART: Set Heater %u to %s\n", heater_num, state ? "ON" : "OFF");
  setHeater(heater_num, state);
  sendACK(seq);
}

void handleGetStatusCommand(uint8_t seq) {
  uint8_t status_bytes[6];
  status_bytes[0] = v5_enabled ? 1 : 0;
  status_bytes[1] = v10_enabled ? 1 : 0;
  status_bytes[2] = digitalRead(IN1) ? 1 : 0;
  status_bytes[3] = digitalRead(IN2) ? 1 : 0;
  status_bytes[4] = digitalRead(IN3) ? 1 : 0;
  status_bytes[5] = digitalRead(IN4) ? 1 : 0;

  sendPacket(PKT_TYPE_DATA, seq, status_bytes, sizeof(status_bytes));
}

// ======================= NON-BLOCKING UART PARSER =======================

enum ParserState {
  STATE_WAIT_START1,
  STATE_WAIT_START2,
  STATE_READ_HEADER,
  STATE_READ_PAYLOAD,
  STATE_READ_CRC
};

static ParserState parser_state = STATE_WAIT_START1;
static uint8_t rx_type = 0;
static uint8_t rx_seq = 0;
static uint8_t rx_len = 0;
static uint8_t rx_payload[256];
static uint8_t rx_header[3];
static uint8_t rx_crc_bytes[2];
static size_t rx_idx = 0;
static unsigned long last_rx_time = 0;

void checkUART() {
  if (!extuart_enabled) {
    ExtUART.begin(115200, SERIAL_8N1, EXTUART_RX, EXTUART_TX);
    extuart_enabled = true;
  }

  // Inter-byte timeout reset (100ms)
  if (parser_state != STATE_WAIT_START1 && millis() - last_rx_time > 100) {
    parser_state = STATE_WAIT_START1;
    rx_idx = 0;
  }

  while (ExtUART.available()) {
    uint8_t b = ExtUART.read();
    last_rx_time = millis();

    switch (parser_state) {
      case STATE_WAIT_START1:
        if (b == PKT_START1) {
          parser_state = STATE_WAIT_START2;
        }
        break;

      case STATE_WAIT_START2:
        if (b == PKT_START2) {
          parser_state = STATE_READ_HEADER;
          rx_idx = 0;
        } else if (b != PKT_START1) {
          parser_state = STATE_WAIT_START1;
        }
        break;

      case STATE_READ_HEADER:
        rx_header[rx_idx++] = b;
        if (rx_idx >= 3) {
          rx_type = rx_header[0];
          rx_seq  = rx_header[1];
          rx_len  = rx_header[2];

          rx_idx = 0;
          if (rx_len > 0) {
            parser_state = STATE_READ_PAYLOAD;
          } else {
            parser_state = STATE_READ_CRC;
          }
        }
        break;

      case STATE_READ_PAYLOAD:
        rx_payload[rx_idx++] = b;
        if (rx_idx >= rx_len) {
          parser_state = STATE_READ_CRC;
          rx_idx = 0;
        }
        break;

      case STATE_READ_CRC:
        rx_crc_bytes[rx_idx++] = b;
        if (rx_idx >= 2) {
          uint16_t expected_crc = ((uint16_t)rx_crc_bytes[0] << 8) | rx_crc_bytes[1];

          // Compute CRC across [START1, START2, TYPE, SEQ, LEN, PAYLOAD...]
          uint8_t full_frame[260];
          full_frame[0] = PKT_START1;
          full_frame[1] = PKT_START2;
          full_frame[2] = rx_type;
          full_frame[3] = rx_seq;
          full_frame[4] = rx_len;
          if (rx_len > 0) {
            memcpy(&full_frame[5], rx_payload, rx_len);
          }

          uint16_t computed_crc = crc16_ccitt(full_frame, 5 + rx_len);

          if (computed_crc != expected_crc) {
            Serial.printf("UART: CRC mismatch! Expected: 0x%04X, Computed: 0x%04X\n",
              expected_crc, computed_crc);
            sendNACK(rx_seq, ERR_BAD_CRC);
          } else {
            // CRC valid, dispatch command
            switch (rx_type) {
              case PKT_CMD_PING:
                handlePingCommand(rx_seq);
                break;
              case PKT_CMD_READ_PD:
                handleReadPDCommand(rx_seq);
                break;
              case PKT_CMD_READ_RTD:
                handleReadRTDCommand(rx_seq);
                break;
              case PKT_CMD_SWEEP:
                handleSweepCommand(rx_seq);
                break;
              case PKT_CMD_SET_RAIL:
                handleSetRailCommand(rx_seq, rx_payload, rx_len);
                break;
              case PKT_CMD_SET_HEATER:
                handleSetHeaterCommand(rx_seq, rx_payload, rx_len);
                break;
              case PKT_CMD_GET_STATUS:
                handleGetStatusCommand(rx_seq);
                break;
              default:
                Serial.printf("UART: Unknown command type: 0x%02X\n", rx_type);
                sendNACK(rx_seq, ERR_UNKNOWN_CMD);
                break;
            }
          }

          // Reset parser state
          parser_state = STATE_WAIT_START1;
          rx_idx = 0;
        }
        break;
    }
  }
}

// ======================= LEGACY SERIAL / UART TRANSMISSIONS =======================

void sendPDOverUART(int cs_pin, int device_num, int channel_num) {
  Serial.printf("UART: Reading photodiode sensor device #%d channel %d...\n", device_num, channel_num);

  uint16_t adc_control_single = 0x0104;
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_single);
  Serial.printf("  ✓ Started single sequence mode (0x%04X)\n", adc_control_single);

  int timeout = 1000;
  uint8_t status = 0;
  while (timeout-- > 0) {
    status = ad4130_read_register(cs_pin, AD4130_REG_STATUS);
    if (!(status & 0x80)) {
      break;
    }
    delay(1);
  }

  if (timeout <= 0) {
    Serial.printf("  ✗ AD4130 #%d conversion timeout (status: 0x%02X)\n", device_num, status);
  }

  Serial.printf("  ✓ Conversion complete after %d ms (status: 0x%02X)\n", 1000 - timeout, status);

  uint32_t adc_data = ad4130_read_data(cs_pin);
  Serial.printf("  ✓ Raw ADC data: 0x%06X (%u)\n", adc_data, (unsigned int)adc_data);

  float photocurrent = calculatePhotocurrent(adc_data);

  uint16_t adc_control_idle = 0x0110;
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_idle);

  ExtUART.write("UART_PD_START");
  ExtUART.write((uint8_t*)(&photocurrent), sizeof(photocurrent));
  ExtUART.write("UART_PD_END");
}

void sendRTDOverUART() {
  Serial.println("\n--- UART: Sending All RTD Temperatures ---");

  initRTDSPI();

  if (!v5_enabled) {
    Serial.println("Enabling 5V rail for RTD sensors...");
    toggle5V();
    delay(500);
  }

  float rtd_results[14] = {};

  Serial.println("\n=== ALL RTD RESULTS ===");
  for (int i = 0; i < 7; i++) {
    if (rtd_configs[i].enabled) {
      int rtd_num = i + 1;
      RTDConfig& config = rtd_configs[i];
      if (ad4130_configure_for_rtd_generic(config.cs_pin, config.device_num, 0, config)) {
        float temp = 0.0f, res = 0.0f;
        if (readRTDSensorGeneric(config.cs_pin, config.device_num, 0, temp, res)) {
          if (rtd_cal[i].valid) {
            temp = temp * rtd_cal[i].gain + rtd_cal[i].offset;
          }
          Serial.printf("RTD #%d: %.2f°C (%.1fΩ) [AIN%d/AIN%d/AIN%d]\n",
            rtd_num, temp, res, config.excitation_pin, config.positive_pin, config.negative_pin);
          rtd_results[2 * i] = temp;
          rtd_results[2 * i + 1] = res;
        }
        else {
          Serial.printf("RTD #%d: Read failed\n", rtd_num);
        }
      }
      else {
        Serial.printf("RTD #%d: Config failed\n", rtd_num);
      }
      delay(100);
    }
  }

  ExtUART.write("UART_RTD_START");
  ExtUART.write((uint8_t*)(&rtd_results), sizeof(rtd_results));
  ExtUART.write("UART_RTD_END");

  Serial.println("======================");
}
