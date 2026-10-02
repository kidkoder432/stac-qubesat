#include "microwave.h"
#include "power.h"
#include "sensors.h"
#include "command_interface.h"

void hmc832_sendBytes(uint32_t data, uint8_t addressByte) {
  uint8_t b0 = (data >> 16) & 0xFF;
  uint8_t b1 = (data >> 8) & 0xFF;
  uint8_t b2 = data & 0xFF;

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
  hmc832_sendBytes(0x0, 0b00101000);
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
  hmc832_sendBytes(0, reg_5);
  hmc832_sendBytes(frac_data, reg_4);
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

  uint8_t VarZero = 0b00000000;
  uint8_t VarOne = 0b00100000;
  uint8_t VarTwo = 0b00000010;
  uint8_t VarThree = 0b00001000;
  uint8_t VarFour = 0b00000001;
  uint8_t VarFive = 0b00010000;
  uint8_t VarSix = 0b10010000;
  uint8_t VarSeven = 0b00101000;
  uint8_t VarEight = 0b00001111;
  uint8_t VarNine = 0b10011000;
  uint8_t VarOneZero = 0b01001011;
  uint8_t VarOneOne = 0b00111000;
  uint8_t VarOneTwo = 0b01001010;
  uint8_t VarOneThree = 0b00110000;
  uint8_t VarOneFour = 0b01001101;
  uint8_t VarOneFive = 0b11000001;
  uint8_t VarOneSix = 0b10111110;
  uint8_t VarOneSeven = 0b11111111;
  uint8_t VarOneEight = 0b01000000;
  uint8_t VarOneNine = 0b00111111;
  uint8_t VarTwoZero = 0b11111110;
  uint8_t VarTwoOne = 0b11111101;
  uint8_t VarTwoTwo = 0b01001000;
  uint8_t VarTwoThree = 0b01000110;
  uint8_t VarTwoFour = 0b01010000;
  uint8_t VarTwoFive = 0b01001111;
  uint8_t VarTwoSix = 0b10000000;
  uint8_t VarTwoSeven = 0b01100001;
  uint8_t VarTwoEight = 0b01011000;
  uint8_t VarTwoNine = 0b01100000;
  uint8_t VarThreeZero = 0b10000001;
  uint8_t VarThreeOne = 0b01111000;
  uint8_t VarThreeTwo = 0b00101010;
  uint8_t VarThreeThree = 0b00011000;
  uint8_t VarThreeFour = 0b01100110;

  auto burstWrite = [&](uint8_t d0, uint8_t d1, uint8_t d2, uint8_t addr) {
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

  // Direct port of original Initialize_Microwave_Generator sequence
  burstWrite(VarZero, VarZero, VarOne, VarZero);      // REG 0 20 (RESET)
  burstWrite(VarZero, VarZero, VarTwo, VarThree);     // REG 1 2
  burstWrite(VarZero, VarZero, VarFour, VarFive);      // REG 2 1
  burstWrite(VarZero, VarZero, VarSix, VarSeven);     // REG 5 90
  burstWrite(VarZero, VarEight, VarNine, VarSeven);     // REG 5 F98
  burstWrite(VarZero, VarOneZero, VarOneOne, VarSeven);   // REG 5 4B38
  burstWrite(VarZero, VarZero, VarZero, VarSeven);     // REG 5 0
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
  }
  else {
    Serial.println("✓ Module appears to be responding");
  }
}

void runMicrowaveContrastSweep() {
  Serial.println("\n--- Microwave Contrast Sweep ---");

  if (!microwave_inited) {
    hmc832_Initialize_Microwave_Generator();

    // Maximum gain, divider=1, ref divider=1 (port of old STM32 behavior)
    hmc832_sendBytes(0x4DB8, 0b00101000); // max gain
    hmc832_sendBytes(0x90, 0b00101000);   // divider = 1
    hmc832_sendBytes(0x1, 0b00010000);    // ref divider = 1
  }

  if (!ensurePhotodiodeADCConfigured()) {
    Serial.println("Cannot run sweep: photodiode ADC not configured");
    return;
  }

  const int num_cycles = 10;
  const int samples_per_freq = 100;
  const int freq_steps = 151;
  const int start_frequency = 2800;   // MHz
  const int end_frequency = 2950;     // MHz
  const int step_size = (end_frequency - start_frequency + 1) / freq_steps;
  const int ref_frequency = 1500;     // MHz

  static float contrast_arr[freq_steps];

  for (int cycle = 0; cycle < num_cycles; ++cycle) {
    Serial.printf("Cycle %d/%d\n", cycle + 1, num_cycles);

    for (int j = 0; j < freq_steps; ++j) {
      int set_freq = start_frequency + j * step_size;

      double low_sum = 0.0;
      double high_sum = 0.0;

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
      contrast_arr[j] = (float)ratio;
    }

    // Print the contrast array (one integer per line, like old UART behavior)
    Serial.println("\n=== Contrast Data ===");
    for (int i = 0; i < freq_steps; ++i) {
      Serial.println(contrast_arr[i]);
    }
    Serial.println("=== End Contrast Data ===\n");
    // Send 608-byte packet over UART to PyCubed
    sendContrastData(contrast_arr, freq_steps);
  }

  hmc832_Set_VCO_Frequency(1500);
  Serial.println("Sweep complete, VCO set back to 1500 MHz");
}

bool measureSingleFrequencyContrast(uint16_t freq_mhz, float& contrast_out) {
  if (!microwave_inited) {
    hmc832_Initialize_Microwave_Generator();
    hmc832_sendBytes(0x4DB8, 0b00101000); // max gain
    hmc832_sendBytes(0x90, 0b00101000);   // divider = 1
    hmc832_sendBytes(0x1, 0b00010000);    // ref divider = 1
  }

  if (!ensurePhotodiodeADCConfigured()) {
    Serial.println("Cannot measure contrast: photodiode ADC not configured");
    return false;
  }

  const int samples = 10;
  const int ref_frequency = 1500; // MHz

  // 1. Reference baseline at 1500 MHz
  hmc832_Set_VCO_Frequency(ref_frequency);
  delay(10);

  double low_sum = 0.0;
  for (int s = 0; s < samples; ++s) {
    float i_photo;
    if (!measurePhotodiodeOnce(i_photo)) {
      Serial.println("Error reading reference photodiode");
      return false;
    }
    low_sum += i_photo;
  }

  // 2. Measure at target frequency
  hmc832_Set_VCO_Frequency((int)freq_mhz);
  delay(10);

  double high_sum = 0.0;
  for (int s = 0; s < samples; ++s) {
    float i_photo;
    if (!measurePhotodiodeOnce(i_photo)) {
      Serial.println("Error reading target frequency photodiode");
      hmc832_Set_VCO_Frequency(ref_frequency);
      return false;
    }
    high_sum += i_photo;
  }

  // 3. Return to reference frequency
  hmc832_Set_VCO_Frequency(ref_frequency);

  double denom = low_sum;
  double ratio = (denom > 0.0) ? (high_sum / denom) : 0.0;
  contrast_out = (float)ratio;

  Serial.printf("ODMR Point %u MHz: contrast = %.4f\n", freq_mhz, contrast_out);
  return true;
}
