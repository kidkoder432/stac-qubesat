#include "microwave.h"
#include "power.h"
#include "sensors.h"
#include "command_interface.h"

void hmc832_sendBytes(uint32_t data, uint8_t addressByte) {
  uint8_t b0 = (data >> 16) & 0xFF;
  uint8_t b1 = (data >> 8) & 0xFF;

  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(MIC_SEN, LOW);

  SPI.transfer(b0);
  SPI.transfer(b1);
  SPI.transfer(data & 0xFF);
  SPI.transfer(addressByte);  // pre-shifted: reg address << 3 | chip ID (000b)

  digitalWrite(MIC_SEN, HIGH);
  SPI.endTransaction();
}

// Two-cycle read (datasheet "Serial Port Read Operation"): cycle 1 writes the
// target address to Reg 0x00[4:0], cycle 2 shifts that register out on LD/SDO.
// Verified against a bit-banged read: the first bit sampled in cycle 2 is D23.
// Returns false if SDO reads all 0s or all 1s (no response from the chip).
bool hmc832_readRegister(uint8_t regAddr, uint32_t& readData) {
  uint8_t b2 = regAddr & 0x1F;  // D[4:0] = address to read, D[23:5] = 0

  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));

  digitalWrite(MIC_SEN, LOW);
  SPI.transfer(0);
  SPI.transfer(0);
  SPI.transfer(b2);
  SPI.transfer(0x00);  // reg 0x00, chip address 000b
  digitalWrite(MIC_SEN, HIGH);  // latches the read address
  delayMicroseconds(2);

  digitalWrite(MIC_SEN, LOW);
  uint32_t raw = 0;
  raw |= (uint32_t)SPI.transfer(0) << 24;
  raw |= (uint32_t)SPI.transfer(0) << 16;
  raw |= (uint32_t)SPI.transfer(b2) << 8;
  raw |= SPI.transfer(0x00);
  digitalWrite(MIC_SEN, HIGH);

  SPI.endTransaction();

  readData = raw >> 8;  // 24-bit register payload; low byte is the address echo
  return raw != 0x00000000 && raw != 0xFFFFFFFF;
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
    set10V(true);
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
    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
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

  // Init powers the 10V rail and regulators and sets 3.3V SDO (Reg 0x0B[22])
  hmc832_Initialize_Microwave_Generator();

  // SPI readback: Reg 0x00 is the read-only chip ID
  const uint32_t expected_id = 0x0F3275;
  uint32_t chip_id = 0;
  bool responded = hmc832_readRegister(0x00, chip_id);
  Serial.printf("Chip ID: 0x%06X (expected 0x%06X)\n", chip_id, expected_id);

  if (!responded) {
    Serial.println("✗ No SPI response. Check jumpers JP1-JP5, MIC_REGEN, 5.5V supply and SPI wiring");
  } else if (chip_id != expected_id) {
    Serial.println("⚠ Unexpected chip ID - check SPI mode and wiring");
  } else {
    Serial.println("✓ SPI readback OK");
  }

  // // Set 2800 MHz and check lock detect on LD/SDO
  // hmc832_sendBytes(0x4DB8, 0b00101000); // max gain
  // hmc832_sendBytes(0x90, 0b00101000);   // divider = 1
  // hmc832_sendBytes(0x1, 0b00010000);    // ref divider = 1
  // hmc832_Set_VCO_Frequency(2800);
  // delay(50);

  // if (digitalRead(MIC_SDO)) {
  //   Serial.println("✓ PLL locked at 2800 MHz");
  // } else {
  //   Serial.println("⚠ PLL not locked (check 50 MHz reference and RF connections)");
  // }
}

// True if any byte arrived on the USB serial console since the last check (the bytes are
// consumed). Lets a long sweep be stopped from the keyboard without cutting power.
static bool sweepCancelRequested() {
  if (Serial.available() > 0) {
    while (Serial.available() > 0) Serial.read();
    return true;
  }
  return false;
}

// Leave the generator in the same safe state a finished sweep does.
static void abortSweep(const char* reason) {
  hmc832_Set_VCO_Frequency(1500);
  Serial.printf("\n%s; VCO set back to 1500 MHz\n", reason);
}

// Restores normal per-reading prints on every way out of a sweep (return, cancel, error).
struct SensorQuietScope {
  SensorQuietScope() { setSensorQuiet(true); }
  ~SensorQuietScope() { setSensorQuiet(false); }
};

static void clearProgressLine() { Serial.print("\r                        \r"); }

// ODMR contrast sweep over 2800..2950 MHz.
//   num_cycles      how many times the whole band is swept
//   samples_per_freq photodiode readings averaged at the reference (1500 MHz) and again at each
//                    frequency. One reading takes about 65 ms, so the time is roughly
//                    num_cycles * points * 2 * samples_per_freq * 65 ms.
//   step_mhz        spacing between frequencies (1 = 151 points, 5 = 31 points)
//
// Every finished frequency is printed at once as a line  DATA,<cycle>,<freq_mhz>,<contrast>
// so a cancelled sweep still leaves usable data; plot_odmr_sweep.py reads those lines straight
// from a copy of the console. Contrast = mean photocurrent at the frequency / mean at the
// reference, so it is about 0.85 to 1.0 whatever samples_per_freq is (ICD: contrast point).
// Send any key on the USB serial console to cancel.
void runMicrowaveSweep(int num_cycles, int samples_per_freq, int step_mhz) {
  if (num_cycles < 1 || num_cycles > 100 || samples_per_freq < 1 || samples_per_freq > 1000 ||
      step_mhz < 1 || step_mhz > 150) {
    Serial.println("Sweep parameters out of range: cycles 1..100, samples 1..1000, step 1..150 MHz");
    return;
  }
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

  // The command that started this sweep may have left a newline in the serial buffer; drop it
  // so it is not mistaken for a cancel.
  while (Serial.available() > 0) Serial.read();

  const int start_frequency = 2800;   // MHz
  const int end_frequency = 2950;     // MHz
  const int ref_frequency = 1500;     // MHz
  const int n_freq = (end_frequency - start_frequency) / step_mhz + 1;
  const bool full_format = (step_mhz == 1);  // the 151-point array the PyCubed link expects
  const uint32_t progress_interval_ms = 250;  // progress line refresh rate
  const int total_reads = n_freq * 2 * samples_per_freq;  // per cycle

  static float contrast_arr[151];

  Serial.printf("SWEEP,cycles=%d,samples=%d,step=%d,points=%d\n", num_cycles, samples_per_freq, step_mhz, n_freq);
  Serial.println("DATA_COLUMNS,cycle,freq_mhz,contrast");
  Serial.println("Send any key to cancel the sweep.");

  SensorQuietScope quiet;  // no per-reading prints while sweeping; progress is shown instead
  uint32_t last_progress_ms = 0;
  const uint32_t sweep_start_ms = millis();
  bool estimate_printed = false;

  for (int cycle = 0; cycle < num_cycles; ++cycle) {
    const uint32_t cycle_start_ms = millis();

    for (int j = 0; j < n_freq; ++j) {
      const int set_freq = start_frequency + j * step_mhz;
      const uint32_t freq_start_ms = millis();

      double low_sum = 0.0;
      double high_sum = 0.0;

      // Reference measurement at 1500 MHz
      hmc832_Set_VCO_Frequency(ref_frequency);
      delay(10);

      for (int s = 0; s < samples_per_freq; ++s) {
        if (sweepCancelRequested()) {
          abortSweep("Sweep CANCELLED by user");
          return;
        }
        float i_photo;
        if (!measurePhotodiodeOnce(i_photo)) {
          clearProgressLine();
          Serial.println("Error during low/reference photodiode read");
          abortSweep("Sweep aborted");
          return;
        }
        low_sum += i_photo;
        if (millis() - last_progress_ms >= progress_interval_ms) {
          last_progress_ms = millis();
          Serial.printf("\r%d/%d %dMHz %3d%%  ", cycle + 1, num_cycles, set_freq,
                        100 * (j * 2 * samples_per_freq + s + 1) / total_reads);
        }
      }

      // Measurement at current sweep frequency
      hmc832_Set_VCO_Frequency(set_freq);
      delay(10);

      for (int s = 0; s < samples_per_freq; ++s) {
        if (sweepCancelRequested()) {
          abortSweep("Sweep CANCELLED by user");
          return;
        }
        float i_photo;
        if (!measurePhotodiodeOnce(i_photo)) {
          clearProgressLine();
          Serial.println("Error during high photodiode read");
          abortSweep("Sweep aborted");
          return;
        }
        high_sum += i_photo;
        if (millis() - last_progress_ms >= progress_interval_ms) {
          last_progress_ms = millis();
          Serial.printf("\r%d/%d %dMHz %3d%%  ", cycle + 1, num_cycles, set_freq,
                        100 * (j * 2 * samples_per_freq + samples_per_freq + s + 1) / total_reads);
        }
      }

      // Return to reference frequency
      hmc832_Set_VCO_Frequency(ref_frequency);

      // Ratio of the two means (both sums have samples_per_freq terms, so it is high_sum / low_sum).
      // The old code divided by samples_per_freq as well, which scaled contrast by 1/samples.
      double ratio = (low_sum > 0.0) ? (high_sum / low_sum) : 0.0;
      contrast_arr[j] = (float)ratio;

      clearProgressLine();
      Serial.printf("DATA,%d,%d,%.6f\n", cycle + 1, set_freq, ratio);

      if (!estimate_printed) {
        estimate_printed = true;
        const float est_s = (millis() - freq_start_ms) / 1000.0f * n_freq * num_cycles;
        Serial.printf("(first frequency took %.1f s; estimated total about %.0f s = %.1f min)\n",
                      (millis() - freq_start_ms) / 1000.0f, est_s, est_s / 60.0f);
      }
    }

    Serial.printf("[cycle %d/%d done in %.1f s]\n", cycle + 1, num_cycles,
                  (millis() - cycle_start_ms) / 1000.0);
    if (full_format) {
      // 151 floats (604 bytes) as one packet, the format the PyCubed side expects
      sendContrastData(contrast_arr, n_freq);
    }
  }

  hmc832_Set_VCO_Frequency(1500);
  Serial.printf("Sweep complete in %.1f s, VCO set back to 1500 MHz\n", (millis() - sweep_start_ms) / 1000.0);
}

// The full-quality sweep (10 cycles, 100 samples, every 1 MHz). About 5 hours; use the quick one first.
void runMicrowaveContrastSweep() {
  runMicrowaveSweep(10, 100, 1);
}

// A rough result in about a minute: 2 cycles, 5 samples, every 5 MHz (31 points).
void runMicrowaveQuickSweep() {
  runMicrowaveSweep(2, 5, 5);
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
