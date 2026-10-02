#include "ad4130.h"

void initRTDSPI() {
  if (!rtd_enabled) {
    RTD_SPI.begin(RTD_SCLK, RTD_DOUT, RTD_DIN, RTD_CS1);
    rtd_enabled = true;
    delay(100);
  }
}

uint16_t ad4130_read_register_16(int cs_pin, uint8_t reg) {
  RTD_SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(cs_pin, LOW);
  delayMicroseconds(1);

  RTD_SPI.transfer(AD4130_CMD_READ | reg);
  uint16_t data = (RTD_SPI.transfer(0x00) << 8) | RTD_SPI.transfer(0x00);

  delayMicroseconds(1);
  digitalWrite(cs_pin, HIGH);
  RTD_SPI.endTransaction();

  return data;
}

void ad4130_write_register_16(int cs_pin, uint8_t reg, uint16_t data) {
  RTD_SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(cs_pin, LOW);
  delayMicroseconds(1);

  RTD_SPI.transfer(AD4130_CMD_WRITE | reg);
  RTD_SPI.transfer((data >> 8) & 0xFF);
  RTD_SPI.transfer(data & 0xFF);

  delayMicroseconds(1);
  digitalWrite(cs_pin, HIGH);
  RTD_SPI.endTransaction();
}

uint32_t ad4130_read_register_24(int cs_pin, uint8_t reg) {
  RTD_SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(cs_pin, LOW);
  delayMicroseconds(1);

  RTD_SPI.transfer(AD4130_CMD_READ | reg);
  uint32_t data = 0;
  data |= ((uint32_t)RTD_SPI.transfer(0x00) << 16);
  data |= ((uint32_t)RTD_SPI.transfer(0x00) << 8);
  data |= RTD_SPI.transfer(0x00);

  delayMicroseconds(1);
  digitalWrite(cs_pin, HIGH);
  RTD_SPI.endTransaction();

  return data;
}

void ad4130_write_register_24(int cs_pin, uint8_t reg, uint32_t data) {
  RTD_SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(cs_pin, LOW);
  delayMicroseconds(1);

  RTD_SPI.transfer(AD4130_CMD_WRITE | reg);
  RTD_SPI.transfer((data >> 16) & 0xFF);
  RTD_SPI.transfer((data >> 8) & 0xFF);
  RTD_SPI.transfer(data & 0xFF);

  delayMicroseconds(1);
  digitalWrite(cs_pin, HIGH);
  RTD_SPI.endTransaction();
}

uint8_t ad4130_read_register(int cs_pin, uint8_t reg) {
  RTD_SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(cs_pin, LOW);
  delayMicroseconds(1);

  RTD_SPI.transfer(AD4130_CMD_READ | reg);
  uint8_t data = RTD_SPI.transfer(0x00);

  delayMicroseconds(1);
  digitalWrite(cs_pin, HIGH);
  RTD_SPI.endTransaction();

  return data;
}

void ad4130_write_register(int cs_pin, uint8_t reg, uint8_t data) {
  RTD_SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(cs_pin, LOW);
  delayMicroseconds(1);

  RTD_SPI.transfer(AD4130_CMD_WRITE | reg);
  RTD_SPI.transfer(data);

  delayMicroseconds(1);
  digitalWrite(cs_pin, HIGH);
  RTD_SPI.endTransaction();
}

uint32_t ad4130_read_data(int cs_pin) {
  RTD_SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(cs_pin, LOW);
  delayMicroseconds(1);

  RTD_SPI.transfer(AD4130_CMD_READ | AD4130_REG_DATA);
  uint32_t data = 0;
  data |= ((uint32_t)RTD_SPI.transfer(0x00) << 16);
  data |= ((uint32_t)RTD_SPI.transfer(0x00) << 8);
  data |= RTD_SPI.transfer(0x00);

  delayMicroseconds(1);
  digitalWrite(cs_pin, HIGH);
  RTD_SPI.endTransaction();

  return data;
}

void testAD4130(int cs_pin, int int_pin, int device_num) {
  initRTDSPI();

  uint8_t id = ad4130_read_register(cs_pin, AD4130_REG_ID);
  uint8_t silicon_id = (id >> 2) & 0x03;
  uint8_t model_id = id & 0x03;

  if (silicon_id == AD4130_SILICON_ID_EXPECTED) {
    Serial.printf("  ✓ AD4130 #%d detected: raw ID=0x%02X (silicon_id=0x%X, model_id=0x%X)\n",
      device_num, id, silicon_id, model_id);
    Serial.printf("  ✓ INT%d pin: %s\n", device_num,
      digitalRead(int_pin) ? "HIGH" : "LOW");

    uint8_t adc_ctrl = ad4130_read_register(cs_pin, AD4130_REG_ADC_CONTROL);
    Serial.printf("    ADC_CONTROL: 0x%02X\n", adc_ctrl);

    uint8_t status = ad4130_read_register(cs_pin, AD4130_REG_STATUS);
    Serial.printf("    STATUS: 0x%02X\n", status);
  }
  else if (id != 0x00 && id != 0xFF) {
    Serial.printf("  ⚠ AD4130 #%d unexpected ID: 0x%02X (silicon_id=0x%X)\n",
      device_num, id, silicon_id);
  }
  else {
    Serial.printf("  ✗ AD4130 #%d not responding (ID: 0x%02X)\n", device_num, id);
    Serial.println("    Check:");
    Serial.println("    - Power supply (5V rail)");
    Serial.println("    - SPI connections");
    Serial.println("    - CS pin connection");
  }
}

void debugAD4130Registers(int cs_pin, int device_num) {
  initRTDSPI();

  Serial.printf("\n=== AD4130 #%d Register Debug ===\n", device_num);

  uint8_t id = ad4130_read_register(cs_pin, AD4130_REG_ID);
  uint8_t status = ad4130_read_register(cs_pin, AD4130_REG_STATUS);
  uint16_t adc_ctrl = ad4130_read_register_16(cs_pin, AD4130_REG_ADC_CONTROL);
  uint16_t io_ctrl = ad4130_read_register_16(cs_pin, AD4130_REG_IO_CONTROL_1);
  uint8_t error = ad4130_read_register(cs_pin, AD4130_REG_ERROR);
  uint32_t channel0 = ad4130_read_register_24(cs_pin, AD4130_REG_CHANNEL_0);
  uint16_t config0 = ad4130_read_register_16(cs_pin, AD4130_REG_CONFIG_0);
  uint8_t filter0 = ad4130_read_register(cs_pin, AD4130_REG_FILTER_0);

  uint8_t silicon_id = (id >> 2) & 0x03;
  uint8_t model_id = id & 0x03;

  Serial.printf("ID (0x05):           0x%02X (silicon_id=0x%X, model_id=0x%X)\n", id, silicon_id, model_id);
  Serial.printf("STATUS (0x00):       0x%02X\n", status);
  Serial.printf("ADC_CONTROL (0x01):  0x%04X (16-bit)\n", adc_ctrl);
  Serial.printf("IO_CONTROL (0x03):   0x%04X (16-bit)\n", io_ctrl);
  Serial.printf("ERROR (0x06):        0x%02X\n", error);
  Serial.printf("CHANNEL_0 (0x09):    0x%06X (24-bit)\n", channel0);
  Serial.printf("CONFIG_0 (0x19):     0x%04X (16-bit)\n", config0);
  Serial.printf("FILTER_0 (0x21):     0x%02X\n", filter0);

  Serial.println("\nDecoded values:");
  Serial.printf("  Internal Ref Enabled: %s\n", (adc_ctrl & 0x0100) ? "YES" : "NO");
  Serial.printf("  ADC Mode: %d (0=CONT,1=SINGLE_SEQ,2=STANDBY,4=IDLE)\n", (adc_ctrl >> 2) & 0x0F);
  Serial.printf("  Bipolar Mode: %s\n", (adc_ctrl & 0x4000) ? "YES" : "NO");

  uint8_t iout0_val = (config0 >> 10) & 0x07;
  uint8_t iout1_val = (config0 >> 13) & 0x07;
  uint8_t ref_sel = (config0 >> 4) & 0x03;
  uint8_t pga_gain = (config0 >> 1) & 0x07;

  Serial.printf("  I_OUT0 Current: %d (0=OFF, 6=200µA)\n", iout0_val);
  Serial.printf("  I_OUT1 Current: %d (0=OFF)\n", iout1_val);
  Serial.printf("  Reference: %d (0=REFIN1, 2=Internal)\n", ref_sel);
  Serial.printf("  PGA Gain: %d (0=1x, 1=2x,...)\n", pga_gain);
  Serial.printf("  Ref Buffers: P=%s, M=%s\n",
    (config0 & 0x80) ? "ON" : "OFF",
    (config0 & 0x40) ? "ON" : "OFF");

  bool ch_enabled = (channel0 & 0x800000) != 0;
  uint8_t setup_num = (channel0 >> 20) & 0x07;
  uint8_t ainp = (channel0 >> 13) & 0x1F;
  uint8_t ainm = (channel0 >> 8) & 0x1F;
  uint8_t iout0_pin = channel0 & 0x0F;
  uint8_t iout1_pin = (channel0 >> 4) & 0x0F;

  Serial.printf("  Channel 0 Enabled: %s\n", ch_enabled ? "YES" : "NO");
  Serial.printf("  Setup Number: %d\n", setup_num);
  Serial.printf("  AINP: AIN%d\n", ainp);
  Serial.printf("  AINM: AIN%d\n", ainm);
  Serial.printf("  I_OUT0 Pin: AIN%d\n", iout0_pin);
  Serial.printf("  I_OUT1 Pin: AIN%d\n", iout1_pin);

  if (error != 0) {
    Serial.printf("⚠ ERROR register indicates problems: 0x%02X\n", error);
  }

  Serial.println("=== End Register Debug ===\n");
}
