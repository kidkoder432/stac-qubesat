# Interface Control Document (ICD): Payload Subsystem to PyCubed OBC

**Document ID**: ICD-QUBESAT-PAYLOAD-001  
**Target Subsystems**: ESP32-S3 Payload Board $\longleftrightarrow$ PyCubed Flight Computer (OBC)  
**Status**: DRAFT / BASELINE  
**Author**: Flight Software Subsystem  

---

## 1. Scope & System Overview

This Interface Control Document (ICD) defines the electrical, logical, and data interfaces between the **PyCubed On-Board Computer (OBC)** and the **ESP32-S3 Payload Subsystem**.

### 1.1 Mission Payload Description
The payload is an **Optical Magnetometry / NV-Center Diamond Experiment** consisting of:
1. **Microwave Synthesizer (HMC832)**: Generates 2.80 GHz to 2.95 GHz RF signals to manipulate quantum spin states.
2. **Photodiode & Transimpedance Amplifier (TIA)**: Reads laser-induced fluorescence photocurrent to detect optical contrast dips.
3. **Dual AD4130 24-bit ADCs**:
   - **ADC #1** (CS=8): Reads RTD temperature sensors 1 through 5.
   - **ADC #2** (CS=17): Reads RTD temperature sensors 6 and 7, and Photodiode on AIN15.
4. **Thermal Management (IN1..IN4)**: 4 independent heater channels for temperature stabilization.
5. **Power Rails**: Switched 5V rail (sensors/ADCs) and switched 10V rail (microwave synthesizer).
6. **Battery Monitor (INA228)**: Dedicated I2C power monitor.

---

## 2. Physical & Electrical Interface

### 2.1 Hardware Connections
The communication interface between the OBC and Payload is an asynchronous serial bus (UART):

| Signal Name | ESP32-S3 Pin | PyCubed Pin | Direction | Description |
|---|---|---|---|---|
| **UART_TX** | GPIO 38 | `board.RX` | ESP32 $\rightarrow$ PyCubed | Serial data from Payload to OBC |
| **UART_RX** | GPIO 37 | `board.TX` | PyCubed $\rightarrow$ ESP32 | Commands from OBC to Payload |
| **GND** | GND | GND | Common | Ground reference |

### 2.2 Serial Line Parameters
- **Baud Rate**: `115200` baud
- **Data Bits**: 8
- **Parity**: None
- **Stop Bits**: 1
- **Flow Control**: None (8N1)
- **Voltage Levels**: 3.3V CMOS Logic

---

## 3. Data Formats & Engineering Units

All multi-byte numeric values sent over the serial bus use standard **IEEE-754 32-bit floating point (Little-Endian)** unless specified otherwise.

### 3.1 Photodiode Measurement
- **Sensor**: Silicon Photodiode on AD4130 #2, Channel AIN15.
- **Circuit**: Transimpedance amplifier with $R_{\text{TIA}} = 100\,\text{k}\Omega$.
- **Formula**:
  $$\text{Voltage } V = \frac{\text{ADC\_Data} \times 2.5\,\text{V}}{2^{24}}$$
  $$\text{Photocurrent } I = \frac{V}{100,000\,\Omega}\quad (\text{Amperes})$$
- **Payload Format**: 4 bytes (1 float, little-endian `<f`).
- **Expected Range**: $1.0\times 10^{-10}\,\text{A}$ (dark) to $5.0\times 10^{-7}\,\text{A}$ (saturated).

### 3.2 RTD Temperature & Resistance Measurements
- **Sensors**: PT1000 RTDs ($R_0 = 1000\,\Omega$ at $0^\circ\text{C}$, $\alpha = 0.003851$).
- **Excitation**: $200\,\mu\text{A}$ internal current source from AD4130.
- **Formula**:
  $$R = \frac{V_{\text{AIN}}}{200\,\mu\text{A}}$$
  $$T = \frac{R - 1000.0}{1000.0 \times 0.003851}\quad (^\circ\text{C})$$
- **Channels**: 7 physical RTD channels.
- **Payload Format**: 14 floats (56 bytes, little-endian `<14f`):
  $$[T_1, R_1, T_2, R_2, T_3, R_3, T_4, R_4, T_5, R_5, T_6, R_6, T_7, R_7]$$
- **Expected Range**: $-40^\circ\text{C}$ to $+85^\circ\text{C}$ ($842\,\Omega$ to $1328\,\Omega$).

### 3.3 Power Rail & Heater States
- **Rails**: 5V (`V5_ENABLE`, pin 11), 10V (`V10_ENABLE`, pin 12).
- **Heaters**: IN1 (pin 33), IN2 (pin 34), IN3 (pin 35), IN4 (pin 36).
- **Format**: `uint8_t` (`1 = ON / ENABLED`, `0 = OFF / DISABLED`).

---

## 4. Command Dictionary (What PyCubed Needs to Tell Payload)

The Payload Subsystem must support the following core operational functions requested by PyCubed:

| Command Name | Description | Parameters From PyCubed | Data Returned by Payload |
|---|---|---|---|
| **PING** | Heartbeat / link check | None | Confirmation (ACK) |
| **READ_PD** | Sample photodiode | None | Photocurrent (float, 4 bytes) |
| **READ_RTD** | Sample all 7 temperature channels | None | 7 temperatures & resistances (14 floats, 56 bytes) |
| **SET_RAIL** | Turn 5V or 10V rail on/off | Rail (5 or 10), State (1 or 0) | Confirmation (ACK/NACK) |
| **SET_HEATER** | Turn heater 1..4 on/off | Heater (1..4), State (1 or 0) | Confirmation (ACK/NACK) |
| **START_SWEEP** | Trigger RF microwave sweep | Optional frequency parameters | Confirmation (ACK), followed by contrast data |
| **GET_STATUS** | Query rail and heater states | None | Status bitfield / 6 state bytes |

---

## 5. Baseline Protocol Specification: Fixed-Length Packets with Modulo-256 Checksum

All packets use a 2-byte header `[0x57, 0xAC]` (ASCII `'W'`, `0xAC` / STAC signature) and fixed, predictable lengths so that no variable length field is required. Every packet concludes with a 1-byte modulo-256 checksum.

### 5.1 Checksum Calculation
The checksum is the lower 8 bits of the sum of all preceding bytes in the packet:
$$\text{Checksum} = \left(\sum_{i=0}^{M-1} \text{byte}[i]\right) \pmod{256}$$

### 5.2 Command Packets (PyCubed $\longrightarrow$ ESP32, Exactly 6 Bytes)
All command packets from the flight computer are uniformly **6 bytes**:

| Command | Byte 0 | Byte 1 | Byte 2 (Type) | Byte 3 (Data 0) | Byte 4 (Data 1) | Byte 5 (CS) |
|---|---|---|---|---|---|---|
| **Ping / Heartbeat** | `0x57` | `0xAC` | `'1'` (`0x31`) | `'H'` (`0x48`) | `'B'` (`0x42`) | Mod-256 CS |
| **Set Rail** | `0x57` | `0xAC` | `'2'` (`0x32`) | `0x00` (5V) / `0xFF` (10V) | `0x00` (OFF) / `0xFF` (ON) | Mod-256 CS |
| **Set Heater** | `0x57` | `0xAC` | `'3'` (`0x33`) | `0x01`..`0x04` (IN1..4) | `0x00` (OFF) / `0xFF` (ON) | Mod-256 CS |
| **Measure Contrast Point** | `0x57` | `0xAC` | `'4'` (`0x34`) | `Freq_MSB` | `Freq_LSB` | Mod-256 CS |
| **Get Status** | `0x57` | `0xAC` | `'5'` (`0x35`) | `'G'` (`0x47`) | `'S'` (`0x53`) | Mod-256 CS |
| **Read Photodiode** | `0x57` | `0xAC` | `'P'` (`0x50`) | `'P'` (`0x50`) | `'D'` (`0x44`) | Mod-256 CS |
| **Read RTDs** | `0x57` | `0xAC` | `'R'` (`0x52`) | `'R'` (`0x52`) | `'T'` (`0x54`) | Mod-256 CS |

### 5.3 Response & Telemetry Packets (ESP32 $\longrightarrow$ PyCubed)

| Response Type | Total Bytes | Structure | Description |
|---|---|---|---|
| **ACK** | 4 | `[0x57, 0xAC, 'A', CS]` | Command received & executed successfully. |
| **NACK** | 4 | `[0x57, 0xAC, 'N', CS]` | Packet rejected (checksum error or invalid command). |
| **ERROR** | 6 | `[0x57, 0xAC, 'E', ERR_MSB, ERR_LSB, CS]` | Command valid, but hardware faulted (ADC timeout, rail off). |
| **Photodiode Data** | 8 | `[0x57, 0xAC, 'P', 4-byte float, CS]` | Little-endian photocurrent in Amperes. |
| **RTD Data** | 60 | `[0x57, 0xAC, 'R', 56 float bytes, CS]` | 14 little-endian floats (7x $[T, R]$). |
| **Status Data** | 10 | `[0x57, 0xAC, 'S', v5, v10, in1..4, CS]` | Rail & heater GPIO state flags. |
| **Contrast Point Data** | 8 | `[0x57, 0xAC, 'W', 4-byte float, CS]` | Normalized optical contrast ratio at target frequency ($\approx 0.85$–$1.0$). |

### 5.4 Error Protection & Retry Behavior
- Both ACK, NACK, ERROR, and DATA packets carry the header and checksum. If radiation bit-flips affect an error code, the checksum mismatch causes the packet to be rejected.
- If a checksum error occurs on either side, a `NACK` is sent.
- PyCubed automatically retries commands upon receiving `NACK` or on timeout until a valid response is received.

---

## 6. Implementation Blueprint: What to Put in the Boilerplate

### In the ESP32 Firmware ([`src/command_interface.cpp`](file:///Users/findp/qubesat/payload/src/command_interface.cpp))
Your main loop calls `checkUART()` periodically. Inside `checkUART()`, you just need to:
1. Check if `ExtUART.available() > 0`.
2. Read the incoming command.
3. Call the appropriate subsystem helper:
   - For Photodiode: call `measurePhotodiodeOnce(photocurrent)` (from [`sensors.h`](file:///Users/findp/qubesat/payload/include/sensors.h)).
   - For RTDs: call `readRTDSensorGeneric(...)` or `readAllRTDTemperatures()` (from [`sensors.h`](file:///Users/findp/qubesat/payload/include/sensors.h)).
   - For Power: call `set5V(true/false)` or `set10V(true/false)` (from [`power.h`](file:///Users/findp/qubesat/payload/include/power.h)).
   - For Heaters: call `setHeater(num, state)` (from [`power.h`](file:///Users/findp/qubesat/payload/include/power.h)).
4. Write the result bytes back out to `ExtUART`.

### In PyCubed Flight Task ([`applications/flight/Tasks/payload_uart.py`](file:///Users/findp/qubesat/applications/flight/Tasks/payload_uart.py))
Inside `main_task(self)`:
1. Send the command byte/packet over `self.uart.write(...)`.
2. Wait briefly or check `self.uart.in_waiting`.
3. Read the response bytes.
4. Unpack the numbers using Python's `struct` module:
   ```python
   # Unpack 1 float (photodiode)
   photocurrent = struct.unpack("<f", data)[0]

   # Unpack 14 floats (RTD temperatures & resistances)
   rtd_values = struct.unpack("<14f", data)
   ```
5. Log the data using `self.debug(...)` and `self.log(...)`.

---

## 7. Verification & Acceptance Checklist

Before flight delivery, test these 5 operations on the bench:
- [ ] **Interface Electrical Test**: Verify RX/TX pin mapping and ground reference between PyCubed and ESP32.
- [ ] **Photodiode Telemetry**: Command a photodiode read; verify float value responds to light changes.
- [ ] **RTD Thermal Telemetry**: Command an RTD read; verify measured resistance is $\approx 1000\,\Omega$ at room temperature.
- [ ] **Power Rail Command**: Command 5V/10V rails ON and OFF remotely from PyCubed; verify voltage on multimeter.
- [ ] **Timeout Robustness**: Disconnect UART cable while PyCubed is polling; verify PyCubed task does not freeze or crash the satellite.
