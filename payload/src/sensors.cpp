#include "sensors.h"
#include "power.h"
#include "driver/gpio.h"

// ======================= AD4130 CONFIG: RTD =======================

bool ad4130_configure_for_rtd_generic(int cs_pin, int device_num, int channel_num, RTDConfig& config) {
  Serial.printf("Configuring AD4130 #%d Channel %d for RTD measurement...\n", device_num, channel_num);
  Serial.printf("  Pin config: IOUT=AIN%d, RTD+=AIN%d, RTD-=AIN%d\n",
    config.excitation_pin, config.positive_pin, config.negative_pin);

  // Reset device only for first channel
  if (channel_num == 0) {
    ad4130_reset(cs_pin);

    // Verify device ID (by silicon_id bits)
    uint8_t id = ad4130_read_register(cs_pin, AD4130_REG_ID);
    uint8_t silicon_id = (id >> 2) & 0x03;
    uint8_t model_id = id & 0x03;

    if (silicon_id != AD4130_SILICON_ID_EXPECTED) {
      Serial.printf("  ✗ Unexpected AD4130 silicon ID: 0x%02X (raw ID=0x%02X)\n", silicon_id, id);
      return false;
    }
    Serial.printf("  ✓ AD4130 Device detected: silicon_id=0x%X, model_id=0x%X (raw 0x%02X)\n",
      silicon_id, model_id, id);

    // ADC control: IDLE mode, internal reference enabled
    uint16_t adc_control_val = AD4130_ADC_CONTROL_IDLE;
    ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_val);
    delay(10);
    uint16_t adc_readback = ad4130_read_register_16(cs_pin, AD4130_REG_ADC_CONTROL);
    Serial.printf("  ✓ ADC Control configured: wrote 0x%04X, read 0x%04X\n", adc_control_val, adc_readback);
  }

  // Configure Channel (24-bit)
  uint32_t channel_config = 0x800000 |                    // ENABLE=1
    (0x00 << 20) |                 // SETUP=0
    (config.positive_pin << 13) |  // AINP
    (config.negative_pin << 8) |   // AINM
    (config.excitation_pin << 0);  // I_OUT0 pin (must obey IOUT0 pin rules)
  ad4130_write_register_24(cs_pin, AD4130_REG_CHANNEL_0 + channel_num, channel_config);
  delay(10);
  uint32_t channel_readback = ad4130_read_register_24(cs_pin, AD4130_REG_CHANNEL_0 + channel_num);
  Serial.printf("  ✓ Channel %d configured: wrote 0x%06X, read 0x%06X\n", channel_num, channel_config, channel_readback);

  // Setup 0 configuration (only once per device)
  if (channel_num == 0) {
    uint16_t config0_val = (0x00 << 13) |   // I_OUT1 = Off
      (0x06 << 10) |    // I_OUT0 = 200µA
      (0x01 << 7) |     // REF_BUFP = 1
      (0x01 << 6) |     // REF_BUFM = 1
      (0x02 << 4) |     // REF_SEL = 10 (Internal)
      (0x00 << 1) |     // PGA = 000 (Gain=1)
      (0x00 << 0);      // PGA_BYP = 0
    ad4130_write_register_16(cs_pin, AD4130_REG_CONFIG_0, config0_val);
    delay(10);
    uint16_t config0_readback = ad4130_read_register_16(cs_pin, AD4130_REG_CONFIG_0);
    Serial.printf("  ✓ CONFIG_0 configured: wrote 0x%04X, read 0x%04X\n", config0_val, config0_readback);

    // Filter 0
    ad4130_write_register(cs_pin, AD4130_REG_FILTER_0, 0x04);
    delay(10);
    uint8_t filter0_readback = ad4130_read_register(cs_pin, AD4130_REG_FILTER_0);
    Serial.printf("  ✓ FILTER_0 configured: wrote 0x04, read 0x%02X\n", filter0_readback);
  }

  Serial.printf("  ✓ AD4130 #%d Channel %d RTD configuration complete\n", device_num, channel_num);
  return true;
}

bool ad4130_configure_for_rtd(int cs_pin, int device_num) {
  Serial.printf("Configuring AD4130 #%d for RTD measurement...\n", device_num);

  // Reset
  ad4130_reset(cs_pin);

  // Verify ID
  uint8_t id = ad4130_read_register(cs_pin, AD4130_REG_ID);
  uint8_t silicon_id = (id >> 2) & 0x03;
  uint8_t model_id = id & 0x03;
  if (silicon_id != AD4130_SILICON_ID_EXPECTED) {
    Serial.printf("  ✗ Unexpected AD4130 silicon ID: 0x%X (raw 0x%02X)\n", silicon_id, id);
    return false;
  }
  Serial.printf("  ✓ AD4130 Device detected: silicon_id=0x%X, model_id=0x%X (raw 0x%02X)\n",
    silicon_id, model_id, id);

  // ADC control to IDLE, internal reference
  uint16_t adc_control_val = AD4130_ADC_CONTROL_IDLE;
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_val);
  delay(10);
  uint16_t adc_readback = ad4130_read_register_16(cs_pin, AD4130_REG_ADC_CONTROL);
  Serial.printf("  ✓ ADC Control configured: wrote 0x%04X, read 0x%04X\n", adc_control_val, adc_readback);

  // Channel 0: AIN1/AIN2, IOUT0 on AIN0
  uint32_t channel_config = 0x800000 |
    (0x00 << 20) |
    (0x01 << 13) |  // AINP=AIN1
    (0x02 << 8) |   // AINM=AIN2
    (0x00 << 0);    // IOUT0 on AIN0
  ad4130_write_register_24(cs_pin, AD4130_REG_CHANNEL_0, channel_config);
  delay(10);
  uint32_t channel_readback = ad4130_read_register_24(cs_pin, AD4130_REG_CHANNEL_0);
  Serial.printf("  ✓ Channel 0 configured: wrote 0x%06X, read 0x%06X\n", channel_config, channel_readback);

  // Setup 0
  uint16_t config0_val = (0x00 << 13) |   // I_OUT1 = Off
    (0x06 << 10) |    // I_OUT0 = 200µA
    (0x01 << 7) |     // REF_BUFP = 1
    (0x01 << 6) |     // REF_BUFM = 1
    (0x02 << 4) |     // REF_SEL = 10 (Internal)
    (0x00 << 1) |     // PGA = 000
    (0x00 << 0);      // PGA_BYP = 0
  ad4130_write_register_16(cs_pin, AD4130_REG_CONFIG_0, config0_val);
  delay(10);
  uint16_t config0_readback = ad4130_read_register_16(cs_pin, AD4130_REG_CONFIG_0);
  Serial.printf("  ✓ CONFIG_0 configured: wrote 0x%04X, read 0x%04X\n", config0_val, config0_readback);

  // Filter 0
  ad4130_write_register(cs_pin, AD4130_REG_FILTER_0, 0x04);
  delay(10);
  uint8_t filter0_readback = ad4130_read_register(cs_pin, AD4130_REG_FILTER_0);
  Serial.printf("  ✓ FILTER_0 configured: wrote 0x04, read 0x%02X\n", filter0_readback);

  delay(100);
  Serial.printf("  ✓ AD4130 #%d RTD configuration complete\n", device_num);
  return true;
}

// ======================= RTD MATH =======================

float calculateRTDResistance(uint32_t adc_data) {
  float vref = 2.5f; // Internal reference
  float ain_voltage = ((float)adc_data * vref) / 16777216.0f;  // 2^24

  Serial.printf("    ADC code: %u, AIN voltage: %.6f V\n", (unsigned int)adc_data, ain_voltage);

  float i_dac = 200e-6f; // 200 µA
  float rtd_resistance = ain_voltage / i_dac;

  Serial.printf("    Calculated RTD resistance: %.1f Ω (I=%.1fµA, V=%.6fV)\n",
    rtd_resistance, i_dac * 1e6f, ain_voltage);

  return rtd_resistance;
}

float calculateTemperature(float resistance) {
  // Simple PT1000 approximation: T = (R - R0) / (R0 * alpha)
  return (resistance - PT1000_R0) / (PT1000_R0 * PT1000_ALPHA);
}

// ======================= PHOTODIODE CONFIG / MATH =======================

bool ad4130_configure_for_photodiode(int cs_pin, int device_num, int channel_num) {
  Serial.printf("Configuring AD4130 #%d Channel %d for photodiode measurement...\n", device_num, channel_num);
  Serial.printf("  Pin config: AIN%d (photodiode input)\n", PHOTODIODE_AIN);

  // Reset device and verify it is actually responding before configuring
  ad4130_reset(cs_pin);

  uint8_t id = ad4130_read_register(cs_pin, AD4130_REG_ID);
  uint8_t silicon_id = (id >> 2) & 0x03;
  if (silicon_id != AD4130_SILICON_ID_EXPECTED) {
    Serial.printf("  ✗ AD4130 #%d not responding (raw ID=0x%02X). Check 5V/AVDD, CS pin %d, and MISO.\n",
      device_num, id, cs_pin);
    return false;
  }
  Serial.printf("  ✓ AD4130 Device detected (raw ID=0x%02X)\n", id);

  // ADC control: IDLE mode, internal reference enabled
  uint16_t adc_control_val = AD4130_ADC_CONTROL_IDLE;
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_val);
  delay(10);
  uint16_t adc_readback = ad4130_read_register_16(cs_pin, AD4130_REG_ADC_CONTROL);
  Serial.printf("  ADC Control: wrote 0x%04X, read 0x%04X\n", adc_control_val, adc_readback);
  if (adc_readback != adc_control_val) {
    Serial.println("  ✗ ADC_CONTROL readback mismatch");
    return false;
  }

  // Setup 0: no excitation currents, internal reference (REF_SEL=10) with buffers, PGA gain 1
  uint16_t config0_val = (0x01 << 7) |   // REF_BUFP = 1
    (0x01 << 6) |                        // REF_BUFM = 1
    (0x02 << 4);                         // REF_SEL = 10 (internal, REFOUT/AVSS)
  ad4130_write_register_16(cs_pin, AD4130_REG_CONFIG_0, config0_val);
  delay(10);
  uint16_t config0_readback = ad4130_read_register_16(cs_pin, AD4130_REG_CONFIG_0);
  Serial.printf("  CONFIG_0: wrote 0x%04X, read 0x%04X\n", config0_val, config0_readback);
  if (config0_readback != config0_val) {
    Serial.println("  ✗ CONFIG_0 readback mismatch");
    return false;
  }

  // Channel config: single-ended, AINP=PHOTODIODE_AIN, AINM=AVSS (encoded as 17)
  uint32_t channel_config = 0x800000 |
    (0x00 << 20) |
    (PHOTODIODE_AIN << 13) |
    (17 << 8);
  ad4130_write_register_24(cs_pin, AD4130_REG_CHANNEL_0 + channel_num, channel_config);
  delay(10);
  uint32_t channel_readback = ad4130_read_register_24(cs_pin, AD4130_REG_CHANNEL_0 + channel_num);
  Serial.printf("  Channel %d: wrote 0x%06X, read 0x%06X\n", channel_num, channel_config, channel_readback);
  if (channel_readback != channel_config) {
    Serial.printf("  ✗ Channel %d readback mismatch\n", channel_num);
    return false;
  }

  Serial.printf("  ✓ AD4130 #%d Channel %d photodiode configuration complete\n", device_num, channel_num);
  return true;
}

float calculatePhotocurrent(uint32_t adc_data) {
  float vref = 2.5f;
  float voltage = ((float)adc_data * vref) / 16777216.0f;

  float photocurrent = voltage / PHOTODIODE_TIA_RESISTOR;

  Serial.printf("    ADC code: %u, Voltage: %.6f V\n", (unsigned int)adc_data, voltage);
  Serial.printf("    Calculated photocurrent: %.3f nA\n", photocurrent * 1e9);

  return photocurrent;
}

// ======================= READ RTD / PHOTODIODE =======================

bool readRTDSensorGeneric(int cs_pin, int device_num, int channel_num, float& temperature, float& resistance) {
  Serial.printf("Reading RTD sensor device #%d channel %d...\n", device_num, channel_num);

  // Single sequence measurement
  uint16_t adc_control_single = AD4130_ADC_CONTROL_SINGLE;
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_single);
  Serial.printf("  ✓ Started single sequence mode (0x%04X)\n", adc_control_single);

  // Wait for conversion complete (RDY bit clear)
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
    return false;
  }

  Serial.printf("  ✓ Conversion complete after %d ms (status: 0x%02X)\n", 1000 - timeout, status);

  uint32_t adc_data = ad4130_read_data(cs_pin);
  Serial.printf("  ✓ Raw ADC data: 0x%06X (%u)\n", adc_data, (unsigned int)adc_data);

  resistance = calculateRTDResistance(adc_data);
  temperature = calculateTemperature(resistance);

  Serial.printf("  ✓ Calculated resistance: %.1f Ω\n", resistance);
  Serial.printf("  ✓ Calculated temperature: %.2f °C\n", temperature);

  // Return to IDLE
  uint16_t adc_control_idle = AD4130_ADC_CONTROL_IDLE;
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_idle);

  return true;
}

bool readPhotodiodeSensor(int cs_pin, int device_num, int channel_num, float& photocurrent) {
  Serial.printf("Reading photodiode sensor device #%d channel %d...\n", device_num, channel_num);

  uint16_t adc_control_single = AD4130_ADC_CONTROL_SINGLE;
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_single);
  // Serial.printf("  ✓ Started single sequence mode (0x%04X)\n", adc_control_single);

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
    return false;
  }

  // Serial.printf("  ✓ Conversion complete after %d ms (status: 0x%02X)\n", 1000 - timeout, status);

  uint32_t adc_data = ad4130_read_data(cs_pin);
  // Serial.printf("  ✓ Raw ADC data: 0x%06X (%u)\n", adc_data, (unsigned int)adc_data);

  photocurrent = calculatePhotocurrent(adc_data);

  uint16_t adc_control_idle = AD4130_ADC_CONTROL_IDLE;
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_idle);

  Serial.printf("  ✓ Photocurrent: %.3f nA\n", photocurrent * 1e9);

  return true;
}

// Legacy wrapper
bool readRTDSensor(int cs_pin, int device_num, float& temperature, float& resistance) {
  return readRTDSensorGeneric(cs_pin, device_num, 0, temperature, resistance);
}

// ======================= CLI / TEST HELPERS =======================

void readSingleRTD(int rtd_number) {
  Serial.printf("\n--- Reading RTD #%d ---\n", rtd_number);

  if (rtd_number < 1 || rtd_number > 7) {
    Serial.println("Invalid RTD number. Use 1-7.");
    return;
  }

  RTDConfig& config = rtd_configs[rtd_number - 1];

  if (!config.enabled) {
    Serial.printf("RTD #%d is disabled in configuration.\n", rtd_number);
    return;
  }

  initRTDSPI();

  if (!v5_enabled) {
    Serial.println("Enabling 5V rail for RTD sensors...");
    toggle5V();
    delay(500);
  }

  int channel_num = 0;
  if (ad4130_configure_for_rtd_generic(config.cs_pin, config.device_num, channel_num, config)) {
    float temp, res;
    if (readRTDSensorGeneric(config.cs_pin, config.device_num, channel_num, temp, res)) {
      if (rtd_cal[rtd_number - 1].valid) {
        float orig_temp = temp;
        temp = temp * rtd_cal[rtd_number - 1].gain + rtd_cal[rtd_number - 1].offset;
        Serial.printf("  ✓ Applied calibration: %.2f °C -> %.2f °C\n", orig_temp, temp);
      }

      Serial.printf("\n=== RTD #%d RESULT ===\n", rtd_number);
      Serial.printf("Temperature: %.2f°C\n", temp);
      Serial.printf("Resistance: %.1fΩ\n", res);
      Serial.printf("Pin Config: IOUT=AIN%d, RTD+=AIN%d, RTD-=AIN%d\n",
        config.excitation_pin, config.positive_pin, config.negative_pin);
      Serial.printf("====================\n");
    }
    else {
      Serial.printf("RTD #%d: Read failed\n", rtd_number);
    }
  }
  else {
    Serial.printf("RTD #%d: Configuration failed\n", rtd_number);
  }
}

void readAllRTDTemperatures() {
  Serial.println("\n--- Reading All RTD Temperatures ---");

  initRTDSPI();

  if (!v5_enabled) {
    Serial.println("Enabling 5V rail for RTD sensors...");
    toggle5V();
    delay(500);
  }

  Serial.println("\n=== ALL RTD RESULTS ===");
  for (int i = 0; i < 7; i++) {
    if (rtd_configs[i].enabled) {
      int rtd_num = i + 1;
      RTDConfig& config = rtd_configs[i];
      if (ad4130_configure_for_rtd_generic(config.cs_pin, config.device_num, 0, config)) {
        float temp, res;
        if (readRTDSensorGeneric(config.cs_pin, config.device_num, 0, temp, res)) {
          if (rtd_cal[i].valid) {
            temp = temp * rtd_cal[i].gain + rtd_cal[i].offset;
          }
          Serial.printf("RTD #%d: %.2f°C (%.1fΩ) [AIN%d/AIN%d/AIN%d]\n",
            rtd_num, temp, res, config.excitation_pin, config.positive_pin, config.negative_pin);
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
  Serial.println("======================");
}

void readPhotodiode() {
  Serial.println("\n--- Reading Photodiode ---");

  initRTDSPI();

  if (!v5_enabled) {
    Serial.println("Enabling 5V rail for sensors...");
    toggle5V();
    delay(500);
  }

  int cs_pin = RTD_CS2;
  int channel_num = 0;

  if (ad4130_configure_for_photodiode(cs_pin, PHOTODIODE_DEVICE, channel_num)) {
    float photocurrent;
    if (readPhotodiodeSensor(cs_pin, PHOTODIODE_DEVICE, channel_num, photocurrent)) {
      Serial.printf("\n=== PHOTODIODE RESULT ===\n");
      Serial.printf("Photocurrent: %.3f nA\n", photocurrent * 1e9);
      Serial.printf("Input: AIN%d\n", PHOTODIODE_AIN);
      Serial.printf("TIA Resistor: %.0f kΩ\n", PHOTODIODE_TIA_RESISTOR / 1000.0);
      Serial.printf("========================\n");
    }
    else {
      Serial.println("Photodiode: Read failed");
    }
  }
  else {
    Serial.println("Photodiode: Configuration failed");
  }
}

// Original single-RTD debug helper
void readRTDTemperatures() {
  Serial.println("\n--- RTD Temperature Reading ---");

  initRTDSPI();

  if (!v5_enabled) {
    Serial.println("Enabling 5V rail for RTD sensors...");
    toggle5V();
    delay(500);
  }

  Serial.println("Configuring RTD #1 only...");

  debugAD4130Registers(RTD_CS1, 1);

  if (ad4130_configure_for_rtd(RTD_CS1, 1)) {
    debugAD4130Registers(RTD_CS1, 1);

    float temp1, res1;
    if (readRTDSensor(RTD_CS1, 1, temp1, res1)) {
      Serial.printf("\n=== FINAL RESULT ===\n");
      Serial.printf("RTD #1: %.2f°C (%.1fΩ)\n", temp1, res1);
      Serial.printf("===================\n");
    }
    else {
      Serial.println("RTD #1: Read failed");
    }
  }

  Serial.println("\nNote: Only RTD #1 configured (AIN0=IOUT, AIN1=RTD+, AIN2=RTD-)");
}

void calibrateRTDs() {
  Serial.println("\n--- RTD Calibration ---");
  Serial.println("Using default calibration values (offset=0, gain=1)");

  for (int i = 0; i < 7; i++) {
    rtd_cal[i].offset = 0.0;
    rtd_cal[i].gain = 1.0;
    rtd_cal[i].valid = true;
  }

  Serial.println("✓ Default calibration applied to all 7 RTDs");
}

void continuousRTDMonitoring() {
  Serial.println("\n--- Continuous RTD Monitoring ---");
  Serial.println("Press any key to stop...");

  initRTDSPI();

  if (!v5_enabled) {
    Serial.println("Enabling 5V rail for RTD sensors...");
    toggle5V();
    delay(500);
  }

  bool rtd1_ok = ad4130_configure_for_rtd(RTD_CS1, 1);
  bool rtd2_ok = ad4130_configure_for_rtd(RTD_CS2, 2);

  if (!rtd1_ok && !rtd2_ok) {
    Serial.println("✗ No RTDs configured successfully");
    return;
  }

  while (!Serial.available()) {
    Serial.print("RTD Temps: ");

    if (rtd1_ok) {
      float temp1, res1;
      if (readRTDSensor(RTD_CS1, 1, temp1, res1)) {
        Serial.printf("RTD1=%.2f°C ", temp1);
      }
      else {
        Serial.print("RTD1=ERR ");
      }
    }

    if (rtd2_ok) {
      float temp2, res2;
      if (readRTDSensor(RTD_CS2, 2, temp2, res2)) {
        Serial.printf("RTD2=%.2f°C ", temp2);
      }
      else {
        Serial.print("RTD2=ERR ");
      }
    }

    Serial.println();
    delay(1000);
  }

  while (Serial.available()) Serial.read();
  Serial.println("Monitoring stopped.");
}

void testRTD() {
  Serial.println("\n--- RTD Test (AD4130) - Basic Check ---");

  initRTDSPI();

  Serial.println("Testing AD4130 #1 (CS=8):");
  testAD4130(RTD_CS1, RTD_INT1, 1);

  Serial.println("Testing AD4130 #2 (CS=17):");
  testAD4130(RTD_CS2, RTD_INT2, 2);

  Serial.println("For full RTD temperature reading, use 'r' command");
}

// Try every (CS1, CS2) level combination and print the ID each one returns, to
// find which pin pattern actually selects each AD4130.
void scanADCChipSelects() {
  Serial.println("\n--- AD4130 Chip Select Scan ---");

  initRTDSPI();

  if (!v5_enabled) {
    Serial.println("Enabling 5V rail...");
    toggle5V();
    delay(500);
  }

  auto scan = [](const char* label) {
    Serial.printf("%s\n", label);
    for (int cs1 = 0; cs1 <= 1; cs1++) {
      for (int cs2 = 0; cs2 <= 1; cs2++) {
        digitalWrite(RTD_CS1, cs1);
        digitalWrite(RTD_CS2, cs2);

        RTD_SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
        delayMicroseconds(1);
        RTD_SPI.transfer(AD4130_CMD_READ | AD4130_REG_ID);
        uint8_t id = RTD_SPI.transfer(0x00);
        delayMicroseconds(1);
        RTD_SPI.endTransaction();

        Serial.printf("  CS1=%s CS2=%s -> ID=0x%02X%s\n",
          cs1 ? "HIGH" : "LOW ", cs2 ? "HIGH" : "LOW ", id,
          ((id >> 2) & 0x03) == AD4130_SILICON_ID_EXPECTED ? "  <- AD4130" : "");
      }
    }
    digitalWrite(RTD_CS1, HIGH);
    digitalWrite(RTD_CS2, HIGH);
  };

  scan("Before reset (chips may be out of sync):");

  // 64-ones reset + CSB_EN on both chips, then scan again
  ad4130_reset(RTD_CS1);
  ad4130_reset(RTD_CS2);
  scan("After 64-bit reset + CSB_EN:");

  // Is anything driving MISO with only CS2 selected? Compare the ID under different
  // MISO pulls and SPI settings: a floating line follows the pull, a driven one doesn't.
  Serial.println("MISO drive test (CS1=HIGH, CS2=LOW):");
  struct { const char* name; gpio_pull_mode_t pull; } pulls[] = {
    { "pull-up  ", GPIO_PULLUP_ONLY },
    { "pull-down", GPIO_PULLDOWN_ONLY },
  };
  uint32_t clocks[] = { 1000000, 100000 };
  uint8_t modes[] = { SPI_MODE3, SPI_MODE0 };
  for (auto& pull : pulls) {
    gpio_set_pull_mode((gpio_num_t)RTD_DOUT, pull.pull);
    for (int m = 0; m < 2; m++) {
      for (int c = 0; c < 2; c++) {
        digitalWrite(RTD_CS1, HIGH);
        digitalWrite(RTD_CS2, LOW);
        RTD_SPI.beginTransaction(SPISettings(clocks[c], MSBFIRST, modes[m]));
        RTD_SPI.transfer(AD4130_CMD_READ | AD4130_REG_ID);
        uint8_t id = RTD_SPI.transfer(0x00);
        RTD_SPI.endTransaction();
        digitalWrite(RTD_CS2, HIGH);
        Serial.printf("  %s mode%d %7lu Hz -> 0x%02X\n", pull.name,
          modes[m] == SPI_MODE3 ? 3 : 0, (unsigned long)clocks[c], id);
      }
    }
  }

  // Same pull-up read with each CS combination: a line that only goes low when CS2 is
  // asserted is being driven by IC3; one that is always low is held by something else.
  Serial.println("MISO with pull-up, per CS combination:");
  gpio_set_pull_mode((gpio_num_t)RTD_DOUT, GPIO_PULLUP_ONLY);
  for (int cs1 = 0; cs1 <= 1; cs1++) {
    for (int cs2 = 0; cs2 <= 1; cs2++) {
      digitalWrite(RTD_CS1, cs1);
      digitalWrite(RTD_CS2, cs2);
      RTD_SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
      RTD_SPI.transfer(AD4130_CMD_READ | AD4130_REG_ID);
      uint8_t id = RTD_SPI.transfer(0x00);
      RTD_SPI.endTransaction();
      Serial.printf("  CS1=%s CS2=%s -> 0x%02X\n", cs1 ? "HIGH" : "LOW ", cs2 ? "HIGH" : "LOW ", id);
    }
  }
  digitalWrite(RTD_CS1, HIGH);
  digitalWrite(RTD_CS2, HIGH);
  gpio_set_pull_mode((gpio_num_t)RTD_DOUT, GPIO_FLOATING);
}

// Payload helpers
bool ensurePhotodiodeADCConfigured() {
  initRTDSPI();

  if (!v5_enabled) {
    Serial.println("Enabling 5V rail for sensors...");
    toggle5V();
    delay(500);
  }

  if (!photodiode_configured) {
    if (!ad4130_configure_for_photodiode(RTD_CS2, PHOTODIODE_DEVICE, 0)) {
      Serial.println("✗ Failed to configure AD4130 photodiode channel");
      return false;
    }
    photodiode_configured = true;
  }

  return true;
}

bool measurePhotodiodeOnce(float& photocurrent) {
  if (!ensurePhotodiodeADCConfigured()) {
    return false;
  }

  if (!readPhotodiodeSensor(RTD_CS2, PHOTODIODE_DEVICE, 0, photocurrent)) {
    Serial.println("✗ Photodiode read failed");
    return false;
  }

  return true;
}
