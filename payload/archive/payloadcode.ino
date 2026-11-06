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

// External UART
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

// ======================= AD4130 DEFINITIONS =======================

// Register map
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

// We only check silicon ID bits (3:2) == 0b01 for AD4130 family
#define AD4130_SILICON_ID_EXPECTED  0x01

// ======================= RTD / PHOTODIODE CONFIG =======================

// RTD Configuration Constants
#define RTD_REFERENCE_RESISTOR      16200.0  // 16.2kΩ in ohms
#define PT1000_R0                   1000.0   // PT1000 resistance at 0°C
#define PT1000_ALPHA                0.003851 // Temperature coefficient

// RTD Pin Configuration Structure
struct RTDConfig {
  uint8_t excitation_pin;  // AIN pin for excitation current (IOUT)
  uint8_t positive_pin;    // AIN pin for RTD+ (connected to excitation)
  uint8_t negative_pin;    // AIN pin for RTD- (sense pin)
  uint8_t device_num;      // AD4130 device number (1 or 2)
  int cs_pin;              // Chip select pin for this device
  bool enabled;            // Whether this RTD is enabled
};

// NOTE: AD4130 IOUT0 can only be routed to certain AIN pins (typically 0–7).
// The configs with excitation_pin >7 may not be valid for IOUT0 and should
// be revisited once the exact board routing is confirmed.
RTDConfig rtd_configs[7] = {
  // RTD1-5 on Device 1 (increment by 3 pins each)
  {0, 1, 2, 1, RTD_CS1, true},   // RTD1: AIN0(IOUT), AIN1(+), AIN2(-)
  {3, 4, 5, 1, RTD_CS1, true},   // RTD2: AIN3(IOUT), AIN4(+), AIN5(-)
  {6, 7, 8, 1, RTD_CS1, true},   // RTD3: AIN6(IOUT), AIN7(+), AIN8(-)
  {9, 10, 11, 1, RTD_CS1, false},// RTD4: needs board/datasheet check
  {12, 13, 14, 1, RTD_CS1, false},// RTD5: needs board/datasheet check
  // RTD6-7 on Device 2
  {0, 1, 2, 2, RTD_CS2, false},  // RTD6: disabled by default
  {3, 4, 5, 2, RTD_CS2, false}   // RTD7: disabled by default
};

// Photodiode Configuration
#define PHOTODIODE_DEVICE       2        // Device 2 handles photodiode
#define PHOTODIODE_AIN          15       // AIN15 for photodiode
#define PHOTODIODE_TIA_RESISTOR 100000.0 // 100kΩ transimpedance resistor

// ======================= GLOBAL OBJECTS =======================

TwoWire BatMonI2C = TwoWire(0);
TwoWire ExtI2C   = TwoWire(1);
HardwareSerial ExtUART(1);
SPIClass RTD_SPI(FSPI);

// State flags
bool v5_enabled        = false;
bool v10_enabled       = false;
bool mic_enabled       = false;
bool rtd_enabled       = false;
bool batmon_enabled    = false;
bool exti2c_enabled    = false;
bool extuart_enabled   = false;
bool microwave_inited  = false;
bool photodiode_configured = false;

// RTD calibration data
struct RTDCalibration {
  float offset;
  float gain;
  bool valid;
};

RTDCalibration rtd_cal[7] = {
  {0.0, 1.0, false}, {0.0, 1.0, false}, {0.0, 1.0, false},
  {0.0, 1.0, false}, {0.0, 1.0, false}, {0.0, 1.0, false},
  {0.0, 1.0, false}
};

// ======================= FORWARD DECLARATIONS =======================

void initializePins();
void printMenu();

// Power / peripherals
void toggle5V();
void toggle10V();
void testBatteryMonitor();
void testRTD();
void testAD4130(int cs_pin, int int_pin, int device_num);
void testMicrowave();
void testExtI2C();
void testExtUART();
void toggleHeater(int heater_num);
void showStatus();
void runFullDiagnostics();

// RTD / AD4130
uint8_t  ad4130_read_register(int cs_pin, uint8_t reg);
void     ad4130_write_register(int cs_pin, uint8_t reg, uint8_t data);
uint16_t ad4130_read_register_16(int cs_pin, uint8_t reg);
void     ad4130_write_register_16(int cs_pin, uint8_t reg, uint16_t data);
uint32_t ad4130_read_register_24(int cs_pin, uint8_t reg);
void     ad4130_write_register_24(int cs_pin, uint8_t reg, uint32_t data);
uint32_t ad4130_read_data(int cs_pin);

bool ad4130_configure_for_rtd_generic(int cs_pin, int device_num, int channel_num, RTDConfig& config);
bool ad4130_configure_for_rtd(int cs_pin, int device_num);
bool readRTDSensorGeneric(int cs_pin, int device_num, int channel_num, float &temperature, float &resistance);
bool readRTDSensor(int cs_pin, int device_num, float &temperature, float &resistance);
void readSingleRTD(int rtd_number);
void readAllRTDTemperatures();
void readRTDTemperatures();
void calibrateRTDs();
void continuousRTDMonitoring();
void debugAD4130Registers(int cs_pin, int device_num);

// Photodiode
bool ad4130_configure_for_photodiode(int cs_pin, int device_num, int channel_num);
float calculatePhotocurrent(uint32_t adc_data);
bool readPhotodiodeSensor(int cs_pin, int device_num, int channel_num, float &photocurrent);
void readPhotodiode();

// Payload helpers
bool ensurePhotodiodeADCConfigured();
bool measurePhotodiodeOnce(float &photocurrent);
void runMicrowaveContrastSweep();

// HMC832 / microwave
void hmc832_sendBytes(uint32_t data, uint8_t addressByte);
void hmc832_Set_VCO_Out_Divider(int divisor);
void hmc832_Set_VCO_Frequency(int freqMHz);
void hmc832_Initialize_Microwave_Generator();

// ======================= SETUP / LOOP =======================

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  Serial.println("\n=== Payload Board ESP32S3 Peripheral + Payload Test ===");
  Serial.println("Initializing all pins...");

  initializePins();
  printMenu();
}

void loop() {
  if (Serial.available()) {
    // Read ONE character and echo it for debugging
    char c = Serial.read();

    Serial.print("Received char: 0x");
    Serial.print((uint8_t)c, HEX);
    Serial.print(" ('");
    if (c >= 32 && c <= 126) Serial.print(c); else Serial.print('.');
    Serial.println("')");

    // Ignore line endings
    if (c == '\n' || c == '\r') {
      return;
    }

    switch (c) {
      case '1': toggle5V(); break;
      case '2': toggle10V(); break;
      case '3': testBatteryMonitor(); break;
      case '4': testRTD(); break;
      case '5': testMicrowave(); break;
      case '6': testExtI2C(); break;
      case '7': testExtUART(); break;
      case '8': toggleHeater(1); break;
      case '9': toggleHeater(2); break;
      case 'a': toggleHeater(3); break;
      case 'b': toggleHeater(4); break;
      case 'r': readAllRTDTemperatures(); break;
      case 'c': calibrateRTDs(); break;
      case 't': continuousRTDMonitoring(); break;
      case 'p': readPhotodiode(); break;
      case 's': showStatus(); break;
      case 'd': runFullDiagnostics(); break;
      case 'm': printMenu(); break;

      // NEW: payload sweep
      case 'w':
        Serial.println("Command 'w' recognized, starting microwave contrast sweep...");
        runMicrowaveContrastSweep();
        break;

      default:
        Serial.println("Unknown command. Press 'm' for menu.");
        break;
    }

    // Flush any extra characters in the buffer (like CR/LF combos)
    while (Serial.available()) Serial.read();
  }
}


// ======================= INITIALIZATION / MENU =======================

void initializePins() {
  // Power control
  pinMode(V5_ENABLE, OUTPUT);
  pinMode(V10_ENABLE, OUTPUT);
  digitalWrite(V5_ENABLE, LOW);
  digitalWrite(V10_ENABLE, LOW);

  // RTD pins
  pinMode(RTD_CS1, OUTPUT);
  pinMode(RTD_CS2, OUTPUT);
  pinMode(RTD_INT1, INPUT_PULLUP);
  pinMode(RTD_INT2, INPUT_PULLUP);
  digitalWrite(RTD_CS1, HIGH);
  digitalWrite(RTD_CS2, HIGH);

  // MIC pins
  pinMode(MIC_SEN, OUTPUT);
  pinMode(MIC_REGEN, OUTPUT);
  digitalWrite(MIC_SEN, HIGH);
  digitalWrite(MIC_REGEN, LOW);

  // Heaters
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);

  Serial.println("✓ All pins initialized");
}

void printMenu() {
  Serial.println("\n=== PERIPHERAL CONTROL MENU ===");
  Serial.println("Power Controls:");
  Serial.println("  1 - Toggle 5V Rail");
  Serial.println("  2 - Toggle 10V Rail");
  Serial.println("\nPeripherals:");
  Serial.println("  3 - Test Battery Monitor (INA228)");
  Serial.println("  4 - Test RTD (AD4130) - Basic");
  Serial.println("  5 - Test Microwave Module");
  Serial.println("  6 - Test External I2C");
  Serial.println("  7 - Test External UART");
  Serial.println("\nRTD Functions:");
  Serial.println("  r  - Read All RTD Temperatures");
  Serial.println("  r1-r7 - Read Individual RTD (e.g., 'r1' for RTD1)");
  Serial.println("  c  - Calibrate RTDs");
  Serial.println("  t  - Continuous RTD Monitoring");
  Serial.println("  p  - Read Photodiode (AIN15)");
  Serial.println("\nPayload:");
  Serial.println("  w  - Run Microwave Frequency Sweep (contrast scan)");
  Serial.println("\nHeater Controls:");
  Serial.println("  8 - Toggle Heater IN1");
  Serial.println("  9 - Toggle Heater IN2");
  Serial.println("  a - Toggle Heater IN3");
  Serial.println("  b - Toggle Heater IN4");
  Serial.println("\nDiagnostics:");
  Serial.println("  s - Show Status");
  Serial.println("  d - Run Full Diagnostics");
  Serial.println("  m - Show Menu");
  Serial.println("\nEnter command:");
}

// ======================= AD4130 LOW-LEVEL ACCESS =======================

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

// ======================= AD4130 CONFIG: RTD =======================

bool ad4130_configure_for_rtd_generic(int cs_pin, int device_num, int channel_num, RTDConfig& config) {
  Serial.printf("Configuring AD4130 #%d Channel %d for RTD measurement...\n", device_num, channel_num);
  Serial.printf("  Pin config: IOUT=AIN%d, RTD+=AIN%d, RTD-=AIN%d\n",
                config.excitation_pin, config.positive_pin, config.negative_pin);

  // Reset device only for first channel
  if (channel_num == 0) {
    RTD_SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
    digitalWrite(cs_pin, LOW);
    RTD_SPI.transfer(AD4130_CMD_RESET);
    digitalWrite(cs_pin, HIGH);
    RTD_SPI.endTransaction();
    delay(100);

    // Verify device ID (by silicon_id bits)
    uint8_t id = ad4130_read_register(cs_pin, AD4130_REG_ID);
    uint8_t silicon_id = (id >> 2) & 0x03;
    uint8_t model_id   = id & 0x03;

    if (silicon_id != AD4130_SILICON_ID_EXPECTED) {
      Serial.printf("  ✗ Unexpected AD4130 silicon ID: 0x%02X (raw ID=0x%02X)\n", silicon_id, id);
      return false;
    }
    Serial.printf("  ✓ AD4130 Device detected: silicon_id=0x%X, model_id=0x%X (raw 0x%02X)\n",
                  silicon_id, model_id, id);

    // ADC control: IDLE mode, internal reference enabled
    uint16_t adc_control_val = 0x0110;  // INT_REF_EN=1, MODE=0100 (IDLE)
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
  RTD_SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(cs_pin, LOW);
  RTD_SPI.transfer(AD4130_CMD_RESET);
  digitalWrite(cs_pin, HIGH);
  RTD_SPI.endTransaction();
  delay(100);

  // Verify ID
  uint8_t id = ad4130_read_register(cs_pin, AD4130_REG_ID);
  uint8_t silicon_id = (id >> 2) & 0x03;
  uint8_t model_id   = id & 0x03;
  if (silicon_id != AD4130_SILICON_ID_EXPECTED) {
    Serial.printf("  ✗ Unexpected AD4130 silicon ID: 0x%X (raw 0x%02X)\n", silicon_id, id);
    return false;
  }
  Serial.printf("  ✓ AD4130 Device detected: silicon_id=0x%X, model_id=0x%X (raw 0x%02X)\n",
                silicon_id, model_id, id);

  // ADC control to IDLE, internal reference
  uint16_t adc_control_val = 0x0110;  // INT_REF_EN=1, MODE=0100 (IDLE)
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_val);
  delay(10);
  uint16_t adc_readback = ad4130_read_register_16(cs_pin, AD4130_REG_ADC_CONTROL);
  Serial.printf("  ✓ ADC Control configured: wrote 0x%04X, read 0x%04X\n", adc_control_val, adc_readback);

  // Channel 0: AIN1/AIN2, IOUT0 on AIN0
  uint32_t channel_config = 0x800000 |
                           (0x00 << 20) |
                           (0x01 << 13) |  // AINP=AIN1
                           (0x02 << 8)  |  // AINM=AIN2
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

  Serial.printf("    ADC code: %d, AIN voltage: %.6f V\n", adc_data, ain_voltage);

  float i_dac = 200e-6f; // 200 µA
  float rtd_resistance = ain_voltage / i_dac;

  Serial.printf("    Calculated RTD resistance: %.1f Ω (I=%.1fµA, V=%.6fV)\n",
                rtd_resistance, i_dac*1e6f, ain_voltage);

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

  // Channel config: single-ended, AINP=PHOTODIODE_AIN, AINM=AVSS (encoded as 17)
  uint32_t channel_config = 0x800000 |
                           (0x00 << 20) |
                           (PHOTODIODE_AIN << 13) |
                           (17 << 8);
  ad4130_write_register_24(cs_pin, AD4130_REG_CHANNEL_0 + channel_num, channel_config);
  delay(10);
  uint32_t channel_readback = ad4130_read_register_24(cs_pin, AD4130_REG_CHANNEL_0 + channel_num);
  Serial.printf("  ✓ Channel %d configured: wrote 0x%06X, read 0x%06X\n", channel_num, channel_config, channel_readback);

  Serial.printf("  ✓ AD4130 #%d Channel %d photodiode configuration complete\n", device_num, channel_num);
  return true;
}

float calculatePhotocurrent(uint32_t adc_data) {
  float vref = 2.5f;
  float voltage = ((float)adc_data * vref) / 16777216.0f;

  float photocurrent = voltage / PHOTODIODE_TIA_RESISTOR;

  Serial.printf("    ADC code: %d, Voltage: %.6f V\n", adc_data, voltage);
  Serial.printf("    Calculated photocurrent: %.3f nA\n", photocurrent * 1e9);

  return photocurrent;
}

// ======================= READ RTD / PHOTODIODE =======================

bool readRTDSensorGeneric(int cs_pin, int device_num, int channel_num, float &temperature, float &resistance) {
  Serial.printf("Reading RTD sensor device #%d channel %d...\n", device_num, channel_num);

  // Single sequence measurement
  uint16_t adc_control_single = 0x0104;  // MODE=0001 (Single Seq), INT_REF_EN=1
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_single);
  Serial.printf("  ✓ Started single sequence mode (0x%04X)\n", adc_control_single);

  // Wait for conversion complete (RDY bit clear)
  int timeout = 1000;
  uint8_t status;
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
  Serial.printf("  ✓ Raw ADC data: 0x%06X (%d)\n", adc_data, adc_data);

  resistance = calculateRTDResistance(adc_data);
  temperature = calculateTemperature(resistance);

  Serial.printf("  ✓ Calculated resistance: %.1f Ω\n", resistance);
  Serial.printf("  ✓ Calculated temperature: %.2f °C\n", temperature);

  // Return to IDLE
  uint16_t adc_control_idle = 0x0110;
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_idle);

  return true;
}

bool readPhotodiodeSensor(int cs_pin, int device_num, int channel_num, float &photocurrent) {
  Serial.printf("Reading photodiode sensor device #%d channel %d...\n", device_num, channel_num);

  uint16_t adc_control_single = 0x0104;
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_single);
  Serial.printf("  ✓ Started single sequence mode (0x%04X)\n", adc_control_single);

  int timeout = 1000;
  uint8_t status;
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
  Serial.printf("  ✓ Raw ADC data: 0x%06X (%d)\n", adc_data, adc_data);

  photocurrent = calculatePhotocurrent(adc_data);

  uint16_t adc_control_idle = 0x0110;
  ad4130_write_register_16(cs_pin, AD4130_REG_ADC_CONTROL, adc_control_idle);

  return true;
}

// Legacy wrapper
bool readRTDSensor(int cs_pin, int device_num, float &temperature, float &resistance) {
  return readRTDSensorGeneric(cs_pin, device_num, 0, temperature, resistance);
}

// ======================= DEBUG / RTD HIGH-LEVEL =======================

void debugAD4130Registers(int cs_pin, int device_num) {
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
  uint8_t model_id   = id & 0x03;

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
  uint8_t ref_sel   = (config0 >> 4) & 0x03;
  uint8_t pga_gain  = (config0 >> 1) & 0x07;

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

  if (!rtd_enabled) {
    RTD_SPI.begin(RTD_SCLK, RTD_DOUT, RTD_DIN, RTD_CS1);
    rtd_enabled = true;
  }

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
    } else {
      Serial.printf("RTD #%d: Read failed\n", rtd_number);
    }
  } else {
    Serial.printf("RTD #%d: Configuration failed\n", rtd_number);
  }
}

void readAllRTDTemperatures() {
  Serial.println("\n--- Reading All RTD Temperatures ---");

  if (!rtd_enabled) {
    RTD_SPI.begin(RTD_SCLK, RTD_DOUT, RTD_DIN, RTD_CS1);
    rtd_enabled = true;
  }

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
        } else {
          Serial.printf("RTD #%d: Read failed\n", rtd_num);
        }
      } else {
        Serial.printf("RTD #%d: Config failed\n", rtd_num);
      }
      delay(100);
    }
  }
  Serial.println("======================");
}

void readPhotodiode() {
  Serial.println("\n--- Reading Photodiode ---");

  if (!rtd_enabled) {
    RTD_SPI.begin(RTD_SCLK, RTD_DOUT, RTD_DIN, RTD_CS1);
    rtd_enabled = true;
  }

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
    } else {
      Serial.println("Photodiode: Read failed");
    }
  } else {
    Serial.println("Photodiode: Configuration failed");
  }
}

// Original single-RTD debug helper
void readRTDTemperatures() {
  Serial.println("\n--- RTD Temperature Reading ---");

  if (!rtd_enabled) {
    RTD_SPI.begin(RTD_SCLK, RTD_DOUT, RTD_DIN, RTD_CS1);
    rtd_enabled = true;
  }

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
    } else {
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
    rtd_cal[i].gain   = 1.0;
    rtd_cal[i].valid  = true;
  }

  Serial.println("✓ Default calibration applied to all 7 RTDs");
}

void continuousRTDMonitoring() {
  Serial.println("\n--- Continuous RTD Monitoring ---");
  Serial.println("Press any key to stop...");

  if (!rtd_enabled) {
    RTD_SPI.begin(RTD_SCLK, RTD_DOUT, RTD_DIN, RTD_CS1);
    rtd_enabled = true;
  }

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
      } else {
        Serial.print("RTD1=ERR ");
      }
    }

    if (rtd2_ok) {
      float temp2, res2;
      if (readRTDSensor(RTD_CS2, 2, temp2, res2)) {
        Serial.printf("RTD2=%.2f°C ", temp2);
      } else {
        Serial.print("RTD2=ERR ");
      }
    }

    Serial.println();
    delay(1000);
  }

  while (Serial.available()) Serial.read();
  Serial.println("Monitoring stopped.");
}

// ======================= POWER / PERIPHERAL TESTS =======================

void toggle5V() {
  v5_enabled = !v5_enabled;
  digitalWrite(V5_ENABLE, v5_enabled);
  Serial.print("5V Rail: ");
  Serial.println(v5_enabled ? "ENABLED" : "DISABLED");
  delay(100);
}

void toggle10V() {
  v10_enabled = !v10_enabled;
  digitalWrite(V10_ENABLE, v10_enabled);
  Serial.print("10V Rail: ");
  Serial.println(v10_enabled ? "ENABLED" : "DISABLED");
  delay(100);
}

void testBatteryMonitor() {
  Serial.println("\n--- Battery Monitor Test (INA228) ---");

  if (!batmon_enabled) {
    BatMonI2C.begin(BATMON_SDA, BATMON_SCL, 100000);
    batmon_enabled = true;
    delay(100);
  }

  BatMonI2C.beginTransmission(INA228_ADDR);
  BatMonI2C.write(0x3F); // Device ID register
  if (BatMonI2C.endTransmission() == 0) {
    if (BatMonI2C.requestFrom(INA228_ADDR, 2) == 2) {
      uint16_t deviceID = (BatMonI2C.read() << 8) | BatMonI2C.read();
      Serial.printf("✓ INA228 Device ID: 0x%04X\n", deviceID);

      BatMonI2C.beginTransmission(INA228_ADDR);
      BatMonI2C.write(0x05);
      if (BatMonI2C.endTransmission() == 0) {
        if (BatMonI2C.requestFrom(INA228_ADDR, 3) == 3) {
          uint32_t voltage = ((uint32_t)BatMonI2C.read() << 16) |
                             ((uint32_t)BatMonI2C.read() << 8) |
                             BatMonI2C.read();
          Serial.printf("✓ Bus Voltage: Raw=0x%06X\n", voltage);
        }
      }
    } else {
      Serial.println("✗ Failed to read device ID");
    }
  } else {
    Serial.println("✗ INA228 not responding - Check:");
    Serial.println("  - Power supply");
    Serial.println("  - I2C connections (SDA=3, SCL=4)");
    Serial.println("  - Pull-up resistors");
  }
}

void testRTD() {
  Serial.println("\n--- RTD Test (AD4130) - Basic Check ---");

  if (!rtd_enabled) {
    RTD_SPI.begin(RTD_SCLK, RTD_DOUT, RTD_DIN, RTD_CS1);
    rtd_enabled = true;
    delay(100);
  }

  Serial.println("Testing AD4130 #1 (CS=8):");
  testAD4130(RTD_CS1, RTD_INT1, 1);

  Serial.println("Testing AD4130 #2 (CS=17):");
  testAD4130(RTD_CS2, RTD_INT2, 2);

  Serial.println("For full RTD temperature reading, use 'r' command");
}

void testAD4130(int cs_pin, int int_pin, int device_num) {
  uint8_t id = ad4130_read_register(cs_pin, AD4130_REG_ID);
  uint8_t silicon_id = (id >> 2) & 0x03;
  uint8_t model_id   = id & 0x03;

  if (silicon_id == AD4130_SILICON_ID_EXPECTED) {
    Serial.printf("  ✓ AD4130 #%d detected: raw ID=0x%02X (silicon_id=0x%X, model_id=0x%X)\n",
                  device_num, id, silicon_id, model_id);
    Serial.printf("  ✓ INT%d pin: %s\n", device_num,
                  digitalRead(int_pin) ? "HIGH" : "LOW");

    uint8_t adc_ctrl = ad4130_read_register(cs_pin, AD4130_REG_ADC_CONTROL);
    Serial.printf("    ADC_CONTROL: 0x%02X\n", adc_ctrl);

    uint8_t status = ad4130_read_register(cs_pin, AD4130_REG_STATUS);
    Serial.printf("    STATUS: 0x%02X\n", status);
  } else if (id != 0x00 && id != 0xFF) {
    Serial.printf("  ⚠ AD4130 #%d unexpected ID: 0x%02X (silicon_id=0x%X)\n",
                  device_num, id, silicon_id);
  } else {
    Serial.printf("  ✗ AD4130 #%d not responding (ID: 0x%02X)\n", device_num, id);
    Serial.println("    Check:");
    Serial.println("    - Power supply (5V rail)");
    Serial.println("    - SPI connections");
    Serial.println("    - CS pin connection");
  }
}

void testMicrowave() {
  Serial.println("\n--- Microwave Module Test (EVAL-HMC832A) ---");

  if (!mic_enabled) {
    SPI.begin(MIC_SCK, MIC_SDO, MIC_SDI, MIC_SEN);
    mic_enabled = true;
  }

  if (!v10_enabled) {
    Serial.println("Enabling 10V rail for microwave module...");
    toggle10V();
    delay(200);
  }

  digitalWrite(MIC_REGEN, HIGH);
  delay(100);
  Serial.println("✓ Microwave module powered on");

  Serial.printf("MIC_REGEN: %s\n", digitalRead(MIC_REGEN) ? "HIGH" : "LOW");
  Serial.printf("MIC_SEN: %s\n", digitalRead(MIC_SEN) ? "HIGH" : "LOW");

  // Simple SPI read test (not full init)
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE2));
  digitalWrite(MIC_SEN, LOW);
  uint8_t response = SPI.transfer(0x00);
  digitalWrite(MIC_SEN, HIGH);
  SPI.endTransaction();

  Serial.printf("SPI Response: 0x%02X\n", response);

  if (response == 0x00 || response == 0xFF) {
    Serial.println("⚠ Module may not be responding properly");
    Serial.println("  Check:");
    Serial.println("  - Power supply (10V rail)");
    Serial.println("  - SPI connections");
    Serial.println("  - Module initialization sequence");
  } else {
    Serial.println("✓ Module appears to be responding");
  }
}

void testExtI2C() {
  Serial.println("\n--- External I2C Test ---");

  if (!exti2c_enabled) {
    ExtI2C.begin(EXTI2C_SDA, EXTI2C_SCL, 100000);
    exti2c_enabled = true;
    delay(100);
  }

  Serial.println("Scanning I2C bus...");
  int devices = 0;

  for (int addr = 1; addr < 127; addr++) {
    ExtI2C.beginTransmission(addr);
    if (ExtI2C.endTransmission() == 0) {
      Serial.printf("  ✓ Device found at 0x%02X\n", addr);
      devices++;
    }
  }

  if (devices == 0) {
    Serial.println("  No devices found");
    Serial.println("  Check:");
    Serial.println("  - Pull-up resistors");
    Serial.println("  - Device connections");
    Serial.println("  - Device power");
  } else {
    Serial.printf("  Found %d device(s)\n", devices);
  }

  Serial.println("Test write/read (if devices present):");
  for (int addr = 1; addr < 127; addr++) {
    ExtI2C.beginTransmission(addr);
    ExtI2C.write(0x00);
    if (ExtI2C.endTransmission() == 0) {
      if (ExtI2C.requestFrom(addr, 1) == 1) {
        uint8_t data = ExtI2C.read();
        Serial.printf("  0x%02X: wrote 0x00, read 0x%02X\n", addr, data);
      }
    }
  }
}

void testExtUART() {
  Serial.println("\n--- External UART Test ---");

  if (!extuart_enabled) {
    ExtUART.begin(115200, SERIAL_8N1, EXTUART_RX, EXTUART_TX);
    extuart_enabled = true;
    delay(100);
  }

  Serial.println("Sending test message...");
  ExtUART.println("ESP32 Test Message");

  Serial.println("Listening for 2 seconds...");
  unsigned long start = millis();
  bool received = false;

  while (millis() - start < 2000) {
    if (ExtUART.available()) {
      Serial.print("Received: ");
      while (ExtUART.available()) {
        Serial.write(ExtUART.read());
        received = true;
      }
      Serial.println();
    }
  }

  if (!received) {
    Serial.println("No response received");
    Serial.println("Check:");
    Serial.println("  - UART connections (RX=37, TX=38)");
    Serial.println("  - External device");
    Serial.println("  - Baud rate match");
  }

  Serial.println("You can send data to external UART by typing 'u:<message>'");
}

// ======================= HEATERS / STATUS / DIAGNOSTICS =======================

void toggleHeater(int heater_num) {
  int pin = 0;
  switch (heater_num) {
    case 1: pin = IN1; break;
    case 2: pin = IN2; break;
    case 3: pin = IN3; break;
    case 4: pin = IN4; break;
  }

  bool current_state = digitalRead(pin);
  digitalWrite(pin, !current_state);

  Serial.printf("Heater IN%d: %s\n", heater_num,
                !current_state ? "ON" : "OFF");
}

void showStatus() {
  Serial.println("\n=== CURRENT STATUS ===");

  Serial.println("Power Rails:");
  Serial.printf("  5V Rail:  %s\n", v5_enabled ? "ENABLED" : "DISABLED");
  Serial.printf("  10V Rail: %s\n", v10_enabled ? "ENABLED" : "DISABLED");

  Serial.println("Heaters:");
  Serial.printf("  IN1: %s\n", digitalRead(IN1) ? "ON" : "OFF");
  Serial.printf("  IN2: %s\n", digitalRead(IN2) ? "ON" : "OFF");
  Serial.printf("  IN3: %s\n", digitalRead(IN3) ? "ON" : "OFF");
  Serial.printf("  IN4: %s\n", digitalRead(IN4) ? "ON" : "OFF");

  Serial.println("Peripherals:");
  Serial.printf("  Battery Monitor: %s\n", batmon_enabled ? "INIT" : "NOT INIT");
  Serial.printf("  RTD ADCs:        %s\n", rtd_enabled ? "INIT" : "NOT INIT");
  Serial.printf("  Microwave:       %s\n", mic_enabled ? "INIT" : "NOT INIT");
  Serial.printf("  External I2C:    %s\n", exti2c_enabled ? "INIT" : "NOT INIT");
  Serial.printf("  External UART:   %s\n", extuart_enabled ? "INIT" : "NOT INIT");

  Serial.println("RTD Configuration & Calibration:");
  for (int i = 0; i < 7; i++) {
    RTDConfig& config = rtd_configs[i];
    Serial.printf("  RTD #%d: %s, Device %d, Pins[%d/%d/%d], Cal[offset=%.2f, gain=%.3f]\n",
                  i+1,
                  config.enabled ? "ENABLED" : "DISABLED",
                  config.device_num,
                  config.excitation_pin, config.positive_pin, config.negative_pin,
                  rtd_cal[i].offset, rtd_cal[i].gain);
  }

  Serial.printf("Photodiode: Device %d, AIN%d, TIA=%.0fkΩ\n",
                PHOTODIODE_DEVICE, PHOTODIODE_AIN, PHOTODIODE_TIA_RESISTOR/1000.0);

  Serial.println("Critical Pin States:");
  Serial.printf("  RTD_INT1: %s\n", digitalRead(RTD_INT1) ? "HIGH" : "LOW");
  Serial.printf("  RTD_INT2: %s\n", digitalRead(RTD_INT2) ? "HIGH" : "LOW");
  Serial.printf("  MIC_REGEN: %s\n", digitalRead(MIC_REGEN) ? "HIGH" : "LOW");
}

void runFullDiagnostics() {
  Serial.println("\n=== FULL DIAGNOSTICS ===");

  Serial.println("1. Enabling power rails...");
  if (!v5_enabled) toggle5V();
  if (!v10_enabled) toggle10V();
  delay(500);

  Serial.println("2. Testing all peripherals...");
  testBatteryMonitor();
  testRTD();
  testMicrowave();
  testExtI2C();
  testExtUART();

  Serial.println("3. Reading RTD temperatures and photodiode...");
  readAllRTDTemperatures();
  readPhotodiode();

  Serial.println("4. Final status:");
  showStatus();

  Serial.println("\n=== DIAGNOSTICS COMPLETE ===");
}

// ======================= MICROWAVE / HMC832 DRIVER =======================

void hmc832_sendBytes(uint32_t data, uint8_t addressByte) {
  uint8_t b0 = (data >> 16) & 0xFF;
  uint8_t b1 = (data >> 8)  & 0xFF;
  uint8_t b2 =  data        & 0xFF;

  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE2));
  digitalWrite(MIC_SEN, LOW);
  delayMicroseconds(1);

  SPI.transfer(b0);
  SPI.transfer(b1);
  SPI.transfer(b2);
  SPI.transfer(addressByte);

  delayMicroseconds(1);
  digitalWrite(MIC_SEN, HIGH);
  SPI.endTransaction();
}

void hmc832_Set_VCO_Out_Divider(int divisor) {
  uint16_t reg_5_bottom_bits = 0b0010000;
  uint32_t word = ((uint32_t)divisor << 7) | reg_5_bottom_bits;

  hmc832_sendBytes(word, 0b00101000);
  hmc832_sendBytes(0x0,  0b00101000);
}

void hmc832_Set_VCO_Frequency(int freqMHz) {
  int xtal = 50;

  int integer_data = freqMHz / xtal;
  double frac_value = (1.0 * freqMHz / xtal) - integer_data;
  int frac_data = (int)(frac_value * pow(2, 24));

  uint8_t reg_5 = 0b00101000;
  uint8_t reg_3 = 0b00011000;
  uint8_t reg_4 = 0b00100000;

  hmc832_sendBytes(integer_data, reg_3);
  hmc832_sendBytes(0,             reg_5);
  hmc832_sendBytes(frac_data,     reg_4);
}

void hmc832_Initialize_Microwave_Generator() {
  Serial.println("Initializing HMC832 microwave generator...");

  if (!v10_enabled) {
    Serial.println("Enabling 10V rail for microwave module...");
    toggle10V();
    delay(200);
  }

  if (!mic_enabled) {
    SPI.begin(MIC_SCK, MIC_SDO, MIC_SDI, MIC_SEN);
    mic_enabled = true;
  }

  digitalWrite(MIC_REGEN, HIGH);
  delay(100);

  uint8_t VarZero    = 0b00000000;
  uint8_t VarOne     = 0b00100000;
  uint8_t VarTwo     = 0b00000010;
  uint8_t VarThree   = 0b00001000;
  uint8_t VarFour    = 0b00000001;
  uint8_t VarFive    = 0b00010000;
  uint8_t VarSix     = 0b10010000;
  uint8_t VarSeven   = 0b00101000;
  uint8_t VarEight   = 0b00001111;
  uint8_t VarNine    = 0b10011000;
  uint8_t VarOneZero = 0b01001011;
  uint8_t VarOneOne  = 0b00111000;
  uint8_t VarOneTwo  = 0b01001010;
  uint8_t VarOneThree= 0b00110000;
  uint8_t VarOneFour = 0b01001101;
  uint8_t VarOneFive = 0b11000001;
  uint8_t VarOneSix  = 0b10111110;
  uint8_t VarOneSeven= 0b11111111;
  uint8_t VarOneEight= 0b01000000;
  uint8_t VarOneNine = 0b00111111;
  uint8_t VarTwoZero = 0b11111110;
  uint8_t VarTwoOne  = 0b11111101;
  uint8_t VarTwoTwo  = 0b01001000;
  uint8_t VarTwoThree= 0b01000110;
  uint8_t VarTwoFour = 0b01010000;
  uint8_t VarTwoFive = 0b01001111;
  uint8_t VarTwoSix  = 0b10000000;
  uint8_t VarTwoSeven= 0b01100001;
  uint8_t VarTwoEight= 0b01011000;
  uint8_t VarTwoNine = 0b01100000;
  uint8_t VarThreeZero=0b10000001;
  uint8_t VarThreeOne= 0b01111000;
  uint8_t VarThreeTwo= 0b00101010;
  uint8_t VarThreeThree=0b00011000;
  uint8_t VarThreeFour=0b01100110;

  auto burstWrite = [&](uint8_t d0, uint8_t d1, uint8_t d2, uint8_t addr){
    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE2));
    digitalWrite(MIC_SEN, LOW);
    delayMicroseconds(1);

    SPI.transfer(d0);
    SPI.transfer(d1);
    SPI.transfer(d2);
    SPI.transfer(addr);

    delayMicroseconds(1);
    digitalWrite(MIC_SEN, HIGH);
    SPI.endTransaction();
    delay(50);
  };

  // This is a direct port of your original Initialize_Microwave_Generator sequence
  burstWrite(VarZero, VarZero, VarOne,     VarZero);      // REG 0 20 (RESET)
  burstWrite(VarZero, VarZero, VarTwo,     VarThree);     // REG 1 2
  burstWrite(VarZero, VarZero, VarFour,    VarFive);      // REG 2 1
  burstWrite(VarZero, VarZero, VarSix,     VarSeven);     // REG 5 90
  burstWrite(VarZero, VarEight, VarNine,   VarSeven);     // REG 5 F98
  burstWrite(VarZero, VarOneZero, VarOneOne, VarSeven);   // REG 5 4B38
  burstWrite(VarZero, VarZero, VarZero,    VarSeven);     // REG 5 0
  burstWrite(VarZero, VarEight, VarOneTwo, VarOneThree);  // REG 6 F4A
  burstWrite(VarZero, VarFour, VarOneFour, VarOneOne);    // REG 7 14D
  burstWrite(VarOneFive, VarOneSix, VarOneSeven, VarOneEight); // REG 8 C1BEFF
  burstWrite(VarOneNine, VarTwoZero, VarTwoOne, VarTwoTwo);    // REG 9 3FFEFD
  burstWrite(VarZero, VarOne, VarTwoThree, VarTwoFour);        // REG A 2046
  burstWrite(VarTwoFive, VarTwoSix, VarTwoSeven, VarTwoEight); // REG B 4F8061
  burstWrite(VarZero, VarZero, VarZero, VarTwoNine);           // REG C 0
  burstWrite(VarZero, VarZero, VarThreeZero, VarThreeOne);     // REG F 81
  burstWrite(VarZero, VarZero, VarThreeTwo, VarThreeThree);    // REG 3 2A
  burstWrite(VarThreeFour, VarThreeFour, VarThreeFour, VarOne);// REG 4 666666

  Serial.println("✓ HMC832 initialization complete");
  microwave_inited = true;
}

// ======================= PAYLOAD HELPERS (PHOTODIODE + SWEEP) =======================

bool ensurePhotodiodeADCConfigured() {
  if (!rtd_enabled) {
    RTD_SPI.begin(RTD_SCLK, RTD_DOUT, RTD_DIN, RTD_CS1);
    rtd_enabled = true;
    delay(100);
  }

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

bool measurePhotodiodeOnce(float &photocurrent) {
  if (!ensurePhotodiodeADCConfigured()) {
    return false;
  }

  if (!readPhotodiodeSensor(RTD_CS2, PHOTODIODE_DEVICE, 0, photocurrent)) {
    Serial.println("✗ Photodiode read failed");
    return false;
  }

  return true;
}

// ======================= PAYLOAD MAIN: FREQUENCY SWEEP =======================

void runMicrowaveContrastSweep() {
  Serial.println("\n--- Microwave Contrast Sweep ---");

  if (!microwave_inited) {
    hmc832_Initialize_Microwave_Generator();

    // Maximum gain, divider=1, ref divider=1 (port of old STM32 behavior)
    hmc832_sendBytes(0x4DB8, 0b00101000); // max gain
    hmc832_sendBytes(0x90,   0b00101000); // divider = 1
    hmc832_sendBytes(0x1,    0b00010000); // ref divider = 1
  }

  if (!ensurePhotodiodeADCConfigured()) {
    Serial.println("Cannot run sweep: photodiode ADC not configured");
    return;
  }

  const int num_cycles        = 10;
  const int samples_per_freq  = 100;
  const int freq_steps        = 151;
  const int start_frequency   = 2800;   // MHz
  const int end_frequency     = 2950;   // MHz
  const int step_size         = (end_frequency - start_frequency + 1) / freq_steps;
  const int ref_frequency     = 1500;   // MHz

  static uint32_t contrast_arr[freq_steps];

  for (int cycle = 0; cycle < num_cycles; ++cycle) {
    Serial.printf("Cycle %d/%d\n", cycle + 1, num_cycles);

    int set_freq = start_frequency;

    for (int j = 0; set_freq <= end_frequency && j < freq_steps; ++j) {
      set_freq += step_size;

      double low_sum  = 0.0;
      double high_sum = 0.0;
`
      // Reference measurement at 1500 MHz
      hmc832_Set_VCO_Frequency(ref_frequency);
      delay(10);

      for (int s = 0; s < samples_per_freq; ++s) {
        float i_photo;
        if (!measurePhotodiodeOnce(i_photo)) {
          Serial.println("Error during low/reference photodiode read");
          return;
        }
        low_sum += i_photo;
      }

      // Measurement at current sweep frequency
      hmc832_Set_VCO_Frequency(set_freq);
      delay(10);

      for (int s = 0; s < samples_per_freq; ++s) {
        float i_photo;
        if (!measurePhotodiodeOnce(i_photo)) {
          Serial.println("Error during high photodiode read");
          return;
        }
        high_sum += i_photo;
      }

      // Return to reference frequency
      hmc832_Set_VCO_Frequency(ref_frequency);

      double denom = samples_per_freq * low_sum;
      double ratio = (denom > 0.0) ? (high_sum / denom) : 0.0;
      contrast_arr[j] = (uint32_t)(ratio * 1e9);
    }

    // Print the contrast array (one integer per line, like old UART behavior)
    Serial.println("\n=== Contrast Data ===");
    for (int i = 0; i < freq_steps; ++i) {
      Serial.println(contrast_arr[i]);
    }
    Serial.println("=== End Contrast Data ===\n");
  }

  hmc832_Set_VCO_Frequency(1500);
  Serial.println("Sweep complete, VCO set back to 1500 MHz");
}
