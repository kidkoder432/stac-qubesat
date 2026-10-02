# Payload Command Interface, Error Handling & Component Testing Guide

This document outlines the modular architecture of the ESP32-S3 payload firmware, the binary UART communication protocol between **PyCubed (OBC)** and the **ESP32-S3 Payload Board**, error handling strategies, component test procedures, and an actionable implementation checklist.

---

## 1. Modular Codebase Architecture

The monolithic `payloadcode.cpp` has been broken down into clean header and source pairs to eliminate scrolling, isolate hardware concerns, and make testing and maintenance straightforward:

| Module                               | Header                                                                                            | Source                                                                                        | Primary Responsibility                                                                                                               |
| ------------------------------------ | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **System Config & Pins**       | [`include/config.h`](file:///Users/findp/qubesat/payload/include/config.h)                       | [`src/config.cpp`](file:///Users/findp/qubesat/payload/src/config.cpp)                       | GPIO pin definitions, bus objects (`RTD_SPI`, `ExtUART`, `BatMonI2C`, `ExtI2C`), sensor configurations & calibration tables. |
| **Power & Heaters**            | [`include/power.h`](file:///Users/findp/qubesat/payload/include/power.h)                         | [`src/power.cpp`](file:///Users/findp/qubesat/payload/src/power.cpp)                         | Power rails (5V, 10V) control, pin initialization, and heater drivers (IN1..IN4).                                                    |
| **Battery Monitor**            | [`include/battery_monitor.h`](file:///Users/findp/qubesat/payload/include/battery_monitor.h)     | [`src/battery_monitor.cpp`](file:///Users/findp/qubesat/payload/src/battery_monitor.cpp)     | INA228 I2C communication, voltage readings, and bus self-testing.                                                                    |
| **AD4130 ADC Driver**          | [`include/ad4130.h`](file:///Users/findp/qubesat/payload/include/ad4130.h)                       | [`src/ad4130.cpp`](file:///Users/findp/qubesat/payload/src/ad4130.cpp)                       | Low-level SPI register read/write (8-bit, 16-bit, 24-bit), reset, register debugging, and silicon ID verification.                   |
| **Sensors (RTD & Photodiode)** | [`include/sensors.h`](file:///Users/findp/qubesat/payload/include/sensors.h)                     | [`src/sensors.cpp`](file:///Users/findp/qubesat/payload/src/sensors.cpp)                     | AD4130 channel routing for 7x PT1000 RTDs and TIA photodiode, resistance/temperature math, calibration, and single/all reads.        |
| **Microwave Generator**        | [`include/microwave.h`](file:///Users/findp/qubesat/payload/include/microwave.h)                 | [`src/microwave.cpp`](file:///Users/findp/qubesat/payload/src/microwave.cpp)                 | HMC832 PLL synthesizer driver, VCO divider/frequency tuning, and optical contrast sweep experiment.                                  |
| **External Bus**               | [`include/external_bus.h`](file:///Users/findp/qubesat/payload/include/external_bus.h)           | [`src/external_bus.cpp`](file:///Users/findp/qubesat/payload/src/external_bus.cpp)           | External I2C bus scan and external UART loopback testing.                                                                            |
| **Command Interface**          | [`include/command_interface.h`](file:///Users/findp/qubesat/payload/include/command_interface.h) | [`src/command_interface.cpp`](file:///Users/findp/qubesat/payload/src/command_interface.cpp) | Binary packet framing, CRC16-CCITT validation, non-blocking stream parser, ACK/NACK/Error responses, and command dispatching.        |
| **Diagnostics & CLI**          | [`include/diagnostics.h`](file:///Users/findp/qubesat/payload/include/diagnostics.h)             | [`src/diagnostics.cpp`](file:///Users/findp/qubesat/payload/src/diagnostics.cpp)             | Full system health check, status summary, and developer CLI menu.                                                                    |
| **Main App**                   | —                                                                                                | [`src/main.cpp`](file:///Users/findp/qubesat/payload/src/main.cpp)                           | `setup()`, non-blocking `checkUART()` in `loop()`, and USB Serial CLI monitor.                                                 |

---

## 2. PyCubed UART Command Interface

### 2.1 Packet Frame Specification

All frames exchanged over `ExtUART` (ESP32 pins `RX=37`, `TX=38` at 115200 8N1) follow this binary structure:

```
+---------+---------+--------+-------+-------+-------------------------+---------------+
| START1  | START2  |  TYPE  |  SEQ  |  LEN  |         PAYLOAD         |     CRC-16    |
| (0x57)  | (0xAC)  | (1 B)  | (1 B) | (1 B) |      (0..250 Bytes)     |  (2 B, Big-E) |
+---------+---------+--------+-------+-------+-------------------------+---------------+
```

- **START1 / START2**: Synchronization bytes (`0x57`, `0xAC`).
- **TYPE**: Frame category or Command ID (1 byte).
- **SEQ**: Sequence counter (`0x00..0xFF`) to correlate requests with responses.
- **LEN**: Number of payload bytes ($N$, $0 \le N \le 250$).
- **PAYLOAD**: Raw data bytes (IEEE-754 little-endian floats, integer parameters, etc.).
- **CRC-16**: CRC-16-CCITT (Polynomial `0x1021`, Initial `0xFFFF`), computed over bytes `[0]` through `[4 + LEN]`.

### 2.2 Packet Types & Command Codes

#### Response Types (ESP32 $\rightarrow$ PyCubed)

| Code     | Name               | Payload                       | Description                                     |
| -------- | ------------------ | ----------------------------- | ----------------------------------------------- |
| `0x01` | `PKT_TYPE_DATA`  | Variable ($N$ bytes)        | Data response requested by command.             |
| `0x06` | `PKT_TYPE_ACK`   | Empty ($LEN=0$)             | Command accepted and completed successfully.    |
| `0x15` | `PKT_TYPE_NACK`  | 1 byte (`PayloadErrorCode`) | Frame rejected (e.g. CRC error, bad parameter). |
| `0x20` | `PKT_TYPE_ERROR` | 1 byte (`PayloadErrorCode`) | Command executed but hardware operation failed. |

#### Command Types (PyCubed $\rightarrow$ ESP32)

| Code     | Command Name           | Payload From PyCubed                                                                                                   | Expected Response                    | Description                                             |
| -------- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------ | ------------------------------------------------------- |
| `0x08` | `PKT_CMD_PING`       | None ($LEN=0$)                                                                                                       | `PKT_TYPE_ACK`                     | Keep-alive check.                                       |
| `0x10` | `PKT_CMD_READ_PD`    | None ($LEN=0$)                                                                                                       | `PKT_TYPE_DATA` (4 bytes, 1 float) | Measures photocurrent in amperes.                       |
| `0x11` | `PKT_CMD_READ_RTD`   | None ($LEN=0$) | `PKT_TYPE_DATA` (56 bytes, 14 floats) | Reads all enabled RTDs ($[T_1, R_1, \dots, T_7, R_7]$). |                                      |                                                         |
| `0x12` | `PKT_CMD_SWEEP`      | None or sweep params                                                                                                   | `PKT_TYPE_ACK` followed by data    | Triggers microwave contrast sweep.                      |
| `0x13` | `PKT_CMD_SET_RAIL`   | 2 bytes:`[rail, state]`                                                                                              | `PKT_TYPE_ACK` or `NACK`         | Rail:`5` or `10`; State: `1` (ON) or `0` (OFF). |
| `0x14` | `PKT_CMD_SET_HEATER` | 2 bytes:`[heater, state]`                                                                                            | `PKT_TYPE_ACK` or `NACK`         | Heater:`1..4`; State: `1` (ON) or `0` (OFF).      |
| `0x15` | `PKT_CMD_GET_STATUS` | None ($LEN=0$)                                                                                                       | `PKT_TYPE_DATA` (6 bytes)          | Status bitfield (rails, heaters).                       |

---

## 3. Error Handling Architecture

The firmware uses explicit error codes defined in [`include/command_interface.h`](file:///Users/findp/qubesat/payload/include/command_interface.h):

```cpp
enum PayloadErrorCode : uint8_t {
  ERR_NONE               = 0x00,
  ERR_BAD_CRC            = 0x01,  // UART CRC mismatch
  ERR_UNKNOWN_CMD        = 0x02,  // Unrecognized command byte
  ERR_RAIL_NOT_ENABLED   = 0x03,  // 5V or 10V rail off / failed to supply power
  ERR_AD4130_TIMEOUT     = 0x04,  // ADC conversion timed out (RDY bit stuck)
  ERR_AD4130_CONFIG_FAIL = 0x05,  // Silicon ID mismatch or register write failed
  ERR_MICROWAVE_FAIL     = 0x06,  // HMC832 SPI/PLL lock failed
  ERR_INVALID_PARAM      = 0x07,  // Parameter out of allowable bounds
  ERR_BUSY               = 0x08   // Long-running operation already in progress
};
```

### Error Mitigation & Recovery Rules

1. **CRC Failure**: When incoming frame CRC doesn't match computed CRC, ESP32 responds with `sendNACK(seq, ERR_BAD_CRC)`. The PyCubed task retries up to 3 times before logging a link fault.
2. **Missing Power Rail**: When reading sensors or running microwave sweeps, if the required rail (5V or 10V) is disabled, the firmware automatically attempts to enable it. If it cannot or times out, it aborts and sends `ERR_RAIL_NOT_ENABLED`.
3. **ADC Conversion Timeout**: The AD4130 conversion loop has a 1000 ms timeout. If the conversion fails to complete within 1000 ms, the ADC returns to idle and reports `ERR_AD4130_TIMEOUT` without freezing the microcontroller.
4. **Inter-Byte Framing Timeout**: If the packet parser receives a valid start byte but the full packet is not received within 100 ms, the parser automatically resets to `STATE_WAIT_START1`, preventing buffer poisoning from corrupted bursts.

---

## 4. Component Testing Plan

Each peripheral can be verified independently using both the USB Serial Menu (interactive CLI) and automated UART command packets:

### 1. Power & Rail Switching

- [ ] **5V Rail**: Toggle via menu key `'1'` or command `0x13 [5, 1]`. Verify 5V output on multimeter/oscilloscope and verify current draw.
- [ ] **10V Rail**: Toggle via menu key `'2'` or command `0x13 [10, 1]`. Verify boost converter activates.
- [ ] **Heaters (IN1..IN4)**: Toggle via menu keys `'8'`, `'9'`, `'a'`, `'b'` or command `0x14 [num, state]`. Verify GPIO output levels on pins 33, 34, 35, 36.

### 2. Battery Monitor (INA228)

- [ ] Test via menu key `'3'` ([`testBatteryMonitor()`](file:///Users/findp/qubesat/payload/src/battery_monitor.cpp)).
- [ ] Verify I2C0 ACK on address `0x41`.
- [ ] Read device ID register (`0x3F`) and confirm ID matches expected value.
- [ ] Verify bus voltage reading (`0x05`) corresponds to actual bus voltage.

### 3. RTD Temperature Sensors (AD4130 #1 & #2)

- [ ] **SPI & Silicon ID**: Test via menu key `'4'` ([`testAD4130()`](file:///Users/findp/qubesat/payload/src/ad4130.cpp)). Confirm silicon ID `0x01` on CS1 (pin 8) and CS2 (pin 17).
- [ ] **Single Channel Read**: Run menu `'r'` or call [`readSingleRTD(1)`](file:///Users/findp/qubesat/payload/src/sensors.cpp). Verify measured resistance is $\approx 1000\,\Omega$ at room temperature ($\approx 20{-}25^\circ\text{C}$).
- [ ] **All Channels**: Test with `'r'` or PyCubed command `0x11`. Verify enabled channels return plausible temperatures and open/unconnected channels do not crash the firmware.

### 4. Photodiode & Transimpedance Amplifier

- [ ] Test via menu key `'p'` ([`readPhotodiode()`](file:///Users/findp/qubesat/payload/src/sensors.cpp)) or command `0x10`.
- [ ] Verify single-ended reading on AD4130 #2, AIN15.
- [ ] Expose sensor to light and dark to verify photocurrent delta ($I = V_{\text{AIN}} / 100\,\text{k}\Omega$).

### 5. Microwave Generator (HMC832)

- [ ] Test via menu key `'5'` ([`testMicrowave()`](file:///Users/findp/qubesat/payload/src/microwave.cpp)).
- [ ] Check `MIC_REGEN` goes HIGH and SPI mode 2 communicates with chip.
- [ ] Verify VCO frequency lock and RF output using a spectrum analyzer or power meter at 1500 MHz and 2870 MHz.
- [ ] Run contrast scan via menu key `'w'` ([`runMicrowaveContrastSweep()`](file:///Users/findp/qubesat/payload/src/microwave.cpp)) or command `0x12`.

### 6. External UART & Framing Interface

- [ ] Test via menu key `'7'` ([`testExtUART()`](file:///Users/findp/qubesat/payload/src/external_bus.cpp)).
- [ ] Loopback TX (pin 38) to RX (pin 37) to verify hardware serial operation.
- [ ] Send sample binary packet `[0x57, 0xAC, 0x08, 0x01, 0x00, 0x..., 0x...]` and confirm `ACK` response.

---

## 5. Actionable Implementation Checklist

### ESP32 Payload Firmware Tasks

- [X] Split monolithic 1822-line `payloadcode.cpp` into modular headers in `include/` and sources in `src/`.
- [X] Implement non-blocking packet framing parser in [`src/command_interface.cpp`](file:///Users/findp/qubesat/payload/src/command_interface.cpp).
- [X] Implement CRC-16-CCITT validation and dispatch functions.
- [X] Connect `checkUART()` in [`src/main.cpp`](file:///Users/findp/qubesat/payload/src/main.cpp) `loop()` so OBC commands run concurrently with developer CLI.
- [X] Verify project compiles cleanly with zero warnings (`pio run`).
- [ ] Add persistent parameter configuration (e.g. saving RTD calibration offsets to ESP32 NVS flash).
- [ ] Implement non-blocking or sliced execution for `runMicrowaveContrastSweep()` if background servicing of other commands is required during the 10-cycle scan.

### PyCubed OBC Driver Tasks ([`payload_uart.py`](file:///Users/findp/qubesat/applications/flight/Tasks/payload_uart.py))

- [ ] Implement CircuitPython/Python `crc16_ccitt(data)` function matching the ESP32 implementation.
- [ ] Implement packet builder: `build_packet(pkt_type, seq, payload) -> bytes`.
- [ ] Implement packet parser: state machine or header read (`read(5)`) followed by payload and CRC verification.
- [ ] Implement `ping_payload() -> bool` in the task loop.
- [ ] Implement `read_photodiode() -> float` and log telemetry to SD card.
- [ ] Implement `read_rtd_temperatures() -> list[float]` and unpack 14 IEEE-754 floats (`struct.unpack("<14f", data)`).
- [ ] Implement timeout and retry logic (3 retries on NACK or timeout).
- [ ] Add state machine integration (e.g., transition payload power on/off during safe mode vs science mode).
