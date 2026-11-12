# Payload ESP32 Developer Diagnostics & CLI Guide

This document describes the interactive developer CLI interface available on the **ESP32-S3 Payload Board** via the USB Serial monitor (115200 baud).

---

## 1. Connecting to the CLI

Open a serial terminal connected to the ESP32-S3 USB port:
```bash
# Using PlatformIO device monitor:
pio device monitor -b 115200

# Or using screen / minicom / tio:
tio /dev/cu.usbmodem* -b 115200
screen /dev/cu.usbmodem* 115200
```

When connected, the board prompts with:
```text
payload> 
```
Commands can be typed with backspace support, full words, or quick single-character shortcuts.

---

## 2. Command Reference

### [Power Rails]
| Command | Shortcut | Description | Example |
|---|---|---|---|
| `pwr 5 [on\|off]` | `1` | Enable or disable 5V sensor power rail | `pwr 5 on` |
| `pwr 10 [on\|off]` | `2` | Enable or disable 10V microwave synthesizer rail | `pwr 10 on` |
| `pwr status` | — | Display current 5V and 10V rail states | `pwr status` |

### [Thermal Management / Heaters]
| Command | Shortcut | Description | Example |
|---|---|---|---|
| `heat <1..4> [on\|off]` | `8`..`b` | Control heater channel 1 to 4 | `heat 1 on` |
| `heat all [on\|off]` | — | Turn all 4 heaters on or off simultaneously | `heat all off` |

### [Sensors: RTD & Photodiode]
| Command | Shortcut | Description | Example |
|---|---|---|---|
| `rtd [all]` | `r` | Read all 7 RTD temperatures and resistances | `rtd all` |
| `rtd <1..7>` | `r1`..`r7` | Read individual RTD sensor with pin details | `rtd 1` |
| `rtd cal` | `c` | Run interactive calibration routine for RTDs | `rtd cal` |
| `rtd mon` | `t` | Continuous real-time RTD temperature stream | `rtd mon` |
| `pd` or `photo` | `p` | Read photodiode photocurrent (nA) and voltage | `pd` |
| `bat` | `3` | Query INA228 battery monitor for bus voltage and ID | `bat` |

### [Microwave Synthesizer (HMC832) & ODMR]
| Command | Shortcut | Description | Example |
|---|---|---|---|
| `mw test` | `5` | Test HMC832 SPI communication and enable rails | `mw test` |
| `mw freq <MHz>` | — | Set microwave VCO frequency (25 to 3000 MHz) | `mw freq 2870` |
| `mw point <MHz>` | — | Measure optical contrast at target MHz (Command '4') | `mw point 2870` |
| `mw quick` | `q` | Quick ODMR sweep: 2 cycles, 5 samples, every 5 MHz (about 1 min) | `mw quick` |
| `mw sweep <cycles> <samples> <step>` | — | Custom ODMR sweep (cycles 1..100, samples 1..1000, step 1..150 MHz) | `mw sweep 2 5 5` |
| `mw sweep` | `w` | Full ODMR sweep: 10 cycles, 100 samples, every 1 MHz (about 5 hours) | `mw sweep` |

Any key cancels a running sweep. Each finished frequency prints `DATA,<cycle>,<freq_mhz>,<contrast>`; save the console to a file and run `python3 plot_odmr_sweep.py <file>` for a CSV and a plot.

### [Communication (PyCubed UART & External I2C)]
| Command | Shortcut | Description | Example |
|---|---|---|---|
| `i2c` | `6` | Scan external I2C bus and list detected addresses | `i2c` |
| `uart test` | `7` | Send test string to PyCubed and listen for reply | `uart test` |
| `uart send <text>` | `u:<text>` | Send arbitrary text message to PyCubed OBC | `uart send PING_TEST` |
| `uart sim pd` | `y` | Simulate transmitting photodiode packet to OBC | `uart sim pd` |
| `uart sim rtd` | `z` | Simulate transmitting 60-byte RTD telemetry packet | `uart sim rtd` |

### [System & Diagnostics]
| Command | Shortcut | Description | Example |
|---|---|---|---|
| `status` | `s` | Display comprehensive dashboard (rails, heap, pins) | `status` |
| `diag` | `d` | Run full automated diagnostic self-test | `diag` |
| `reset` or `reboot` | — | Perform software reboot of the ESP32 | `reboot` |
| `help` or `menu` | `m`, `?` | Display command menu | `help` |

---

## 3. Quick Keystroke Cheat Sheet

For rapid testing on a terminal without typing full sentences:
```text
1: Toggle 5V Rail          8: Toggle Heater 1         r: Read all RTDs
2: Toggle 10V Rail         9: Toggle Heater 2         p: Read Photodiode
3: Test Battery Monitor    a: Toggle Heater 3         w: Full ODMR Sweep
4: Test RTD ADC (AD4130)   b: Toggle Heater 4         s: Status Dashboard
5: Test Microwave Module                              d: Full Diagnostics
6: Scan External I2C                                  m: Help Menu
7: Test External UART
```
