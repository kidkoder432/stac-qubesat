"""
test_payload.py — Interactive CircuitPython REPL Test Suite for ESP32 Payload.

Usage in CircuitPython REPL:
    >>> import test_payload
    (or if already imported: >>> test_payload.run())

Supports:
    [1] Heartbeat / Ping with latency check
    [2] Query Hardware Status (Rails & Heaters)
    [3] Read Photodiode (Fluorescence)
    [4] Read 7-Channel RTD Temperatures & Resistances
    [5] 5V Power Rail Control
    [6] 10V Power Rail Control
    [7] Heaters IN1..IN4 Control
    [8] Single-Frequency ODMR Point Contrast Measurement
    [9] Automated ODMR Frequency Sweep (with optional SD logging)
    [A] Automated End-to-End Regression Self-Test
    [Q] Exit back to REPL
"""

import struct
import sys
import time

try:
    from PayloadUART import PayloadUART
except ImportError:
    # Handle direct directory imports
    from .PayloadUART import PayloadUART


class MockUARTBridge:
    """Simulates the ESP32 Payload for desktop testing without physical hardware."""

    def __init__(self):
        self.in_waiting = 0
        self._rx_buf = bytearray()
        self.v5 = False
        self.v10 = False
        self.heaters = [False, False, False, False]

    def write(self, data: bytes):
        if len(data) >= 6 and data[0] == 0x57 and data[1] == 0xAC:
            cmd = chr(data[2])
            d0, d1 = data[3], data[4]

            if cmd == "1":  # Ping -> ACK
                resp = bytes([0x57, 0xAC, ord("A"), (0x57 + 0xAC + ord("A")) & 0xFF])
                self._rx_buf.extend(resp)
            elif cmd == "2":  # Rail
                if d0 == 0x00:
                    self.v5 = d1 == 0xFF
                elif d0 == 0xFF:
                    self.v10 = d1 == 0xFF
                resp = bytes([0x57, 0xAC, ord("A"), (0x57 + 0xAC + ord("A")) & 0xFF])
                self._rx_buf.extend(resp)
            elif cmd == "3":  # Heater
                if 1 <= d0 <= 4:
                    self.heaters[d0 - 1] = d1 == 0xFF
                resp = bytes([0x57, 0xAC, ord("A"), (0x57 + 0xAC + ord("A")) & 0xFF])
                self._rx_buf.extend(resp)
            elif cmd == "4":  # Single point contrast
                freq = (d0 << 8) | d1
                # Simulate Lorentzian resonance dip around 2870 MHz
                contrast = 0.98 - 0.13 / (1.0 + ((freq - 2870) / 10.0) ** 2)
                body = struct.pack("<BBBBf", 0x57, 0xAC, ord("W"), 0, contrast)
                # Correction: frame is [0x57, 0xAC, 'W', float, CS]
                body = struct.pack("<BBBf", 0x57, 0xAC, ord("W"), contrast)
                cs = sum(body) & 0xFF
                self._rx_buf.extend(body + bytes([cs]))
            elif cmd == "5":  # Status
                states = [
                    1 if self.v5 else 0,
                    1 if self.v10 else 0,
                    1 if self.heaters[0] else 0,
                    1 if self.heaters[1] else 0,
                    1 if self.heaters[2] else 0,
                    1 if self.heaters[3] else 0,
                ]
                body = bytes([0x57, 0xAC, ord("S")] + states)
                cs = sum(body) & 0xFF
                self._rx_buf.extend(body + bytes([cs]))
            elif cmd == "P":  # Read PD
                body = struct.pack("<BBBf", 0x57, 0xAC, ord("P"), 1.42e-6)
                cs = sum(body) & 0xFF
                self._rx_buf.extend(body + bytes([cs]))
            elif cmd == "R":  # Read RTD
                # 7 pairs of [temp, res]
                floats = [
                    22.5,
                    108.8,
                    23.1,
                    109.0,
                    22.8,
                    108.9,
                    24.0,
                    109.3,
                    22.6,
                    108.8,
                    23.5,
                    109.1,
                    22.9,
                    108.9,
                ]
                body = struct.pack("<BBB14f", 0x57, 0xAC, ord("R"), *floats)
                cs = sum(body) & 0xFF
                self._rx_buf.extend(body + bytes([cs]))

        self.in_waiting = len(self._rx_buf)

    def read(self, n: int = -1):
        if n == -1 or n >= len(self._rx_buf):
            res = bytes(self._rx_buf)
            self._rx_buf.clear()
        else:
            res = bytes(self._rx_buf[:n])
            self._rx_buf = self._rx_buf[n:]
        self.in_waiting = len(self._rx_buf)
        return res


def init_payload():
    """Initializes the PayloadUART driver with real hardware or mock fallback."""
    sat = None
    try:
        from pycubed import cubesat

        sat = cubesat
        if getattr(sat, "uart", None) is not None:
            return PayloadUART(sat), False
    except Exception:
        pass

    # Fallback to desktop mock
    class MockSatellite:
        def __init__(self):
            self.uart = MockUARTBridge()

    return PayloadUART(MockSatellite()), True


# Global payload instance
payload, is_mock = init_payload()


def test_ping():
    print("\n--- [1] Ping / Heartbeat Link Check ---")
    t0 = time.monotonic()
    success = payload.ping()
    dt_ms = (time.monotonic() - t0) * 1000.0

    if success:
        print(f"✓ PING SUCCESS: Payload responded with ACK in {dt_ms:.1f} ms")
        return True
    else:
        print(
            f"✗ PING FAILED: No response or NACK received from ESP32 ({dt_ms:.1f} ms)"
        )
        return False


def test_status():
    print("\n--- [2] Hardware Status (Rails & Heaters) ---")
    st = payload.get_status()
    if st:
        print("Power Rails:")
        print(f"  5V Rail:       {'ENABLED' if st['v5_rail'] else 'DISABLED'}")
        print(f"  10V Rail:      {'ENABLED' if st['10v_rail'] else 'DISABLED'}")
        print("Heaters:")
        print(f"  IN1:           {'ON' if st['in1'] else 'OFF'}")
        print(f"  IN2:           {'ON' if st['in2'] else 'OFF'}")
        print(f"  IN3:           {'ON' if st['in3'] else 'OFF'}")
        print(f"  IN4:           {'ON' if st['in4'] else 'OFF'}")
        return True
    else:
        print("✗ Failed to query hardware status")
        return False


def test_photodiode():
    print("\n--- [3] Read Photodiode (Fluorescence) ---")
    t0 = time.monotonic()
    val = payload.read_photodiode()
    dt = time.monotonic() - t0

    if val is not None:
        val_ua = val * 1e6
        val_na = val * 1e9
        print(f"✓ Photocurrent: {val:.4e} A ({val_ua:.3f} µA / {val_na:.1f} nA)")
        print(f"  Sample Latency: {dt:.3f} s")
        if 1e-10 <= val <= 5e-7:
            print("  Status: Within expected operational range")
        else:
            print(
                "  Notice: Value outside nominal range (verify optical excitation)"
            )
        return True
    else:
        print("✗ Photodiode measurement failed or timed out")
        return False


def test_rtds():
    print("\n--- [4] Read All 7 RTD Temperatures ---")
    t0 = time.monotonic()
    rtds = payload.read_rtds()
    dt = time.monotonic() - t0

    if rtds:
        print(f"✓ Read {len(rtds)} RTD channels in {dt:.3f} s:")
        print("  Chan | Temp (°C) | Resistance (Ω) | Status")
        print("  -----+-----------+----------------+-------")
        for r in rtds:
            ch = r["channel"]
            temp = r["temp"]
            res = r["res"]
            status = "OK" if (-40.0 <= temp <= 85.0) else "WARN"
            print(f"  RTD{ch} |   {temp:6.2f}  |        {res:6.1f}  | {status}")
        return True
    else:
        print("✗ Failed to read RTD temperatures")
        return False


def test_power_rail(rail: int):
    print(f"\n--- [{5 if rail == 5 else 6}] Power Rail {rail}V Control ---")
    choice = input(
        f"Set {rail}V Rail state [1 = ON, 0 = OFF, Enter to toggle]: "
    ).strip()

    st = payload.get_status()
    current_state = False
    if st:
        current_state = st["v5_rail"] if rail == 5 else st["10v_rail"]

    if choice == "1":
        new_state = True
    elif choice == "0":
        new_state = False
    else:
        new_state = not current_state

    print(
        f"Setting {rail}V Rail to {'ON' if new_state else 'OFF'} (was {'ON' if current_state else 'OFF'})..."
    )
    ok = payload.set_rail(rail, new_state)
    if ok:
        print(f"✓ {rail}V Rail successfully updated!")
        return True
    else:
        print(f"✗ Failed to update {rail}V Rail")
        return False


def test_heaters():
    print("\n--- [7] Thermal Heaters IN1..IN4 Control ---")
    h_str = input("Select heater channel (1..4) [1]: ").strip() or "1"
    try:
        h_num = int(h_str)
        if not (1 <= h_num <= 4):
            print("Invalid channel (must be 1 to 4)")
            return False
    except ValueError:
        print("Invalid number")
        return False

    state_str = input(f"Set Heater IN{h_num} state [1 = ON, 0 = OFF]: ").strip()
    state = state_str == "1"

    print(f"Setting Heater IN{h_num} to {'ON' if state else 'OFF'}...")
    ok = payload.set_heater(h_num, state)
    if ok:
        print(f"✓ Heater IN{h_num} updated successfully!")
        return True
    else:
        print(f"✗ Failed to update Heater IN{h_num}")
        return False


def test_single_contrast(freq: int = None):
    print("\n--- [8] Single ODMR Contrast Point (Command '4') ---")
    if freq is None:
        freq_str = (
            input("Target frequency in MHz (2800..2950) [2870]: ").strip() or "2870"
        )
        try:
            freq = int(freq_str)
            if not (2800 <= freq <= 2950):
                print("Frequency must be between 2800 and 2950 MHz")
                return False
        except ValueError:
            print("Invalid frequency")
            return False

    print(f"Sending Command '4' for {freq} MHz (30s timeout)...")
    t0 = time.monotonic()
    contrast = payload.measure_contrast(freq, timeout=30.0)
    dt = time.monotonic() - t0

    if contrast is not None:
        print(f"✓ Contrast at {freq} MHz: {contrast:.4f} (latency: {dt:.2f} s)")
        return True
    else:
        print(f"✗ Contrast measurement failed or timed out after {dt:.2f} s")
        return False


def test_odmr_sweep():
    print("\n--- [9] Automated ODMR Frequency Sweep ---")
    start_str = input("Start frequency in MHz [2800]: ").strip() or "2800"
    stop_str = input("Stop frequency in MHz [2950]: ").strip() or "2950"
    step_str = input("Step size in MHz [10]: ").strip() or "10"

    try:
        f_start = int(start_str)
        f_stop = int(stop_str)
        f_step = int(step_str)
    except ValueError:
        print("Invalid numeric parameters")
        return False

    if not (2800 <= f_start <= f_stop <= 2950) or f_step < 1:
        print("Invalid frequency range or step size")
        return False

    frequencies = list(range(f_start, f_stop + 1, f_step))
    total_pts = len(frequencies)
    print(
        f"Starting ODMR sweep: {total_pts} points from {f_start} to {f_stop} MHz (step {f_step} MHz)"
    )

    # Attempt SD logging
    sd_file = None
    try:
        sd_file = open("/sd/odmr_test.csv", "a")
        sd_file.write(
            f"# ODMR Sweep Start: {time.monotonic()} | Points: {total_pts}\n"
        )
        sd_file.write("freq_mhz,contrast\n")
        print("✓ Logging sweep points to /sd/odmr_test.csv")
    except Exception:
        print("Notice: SD card not available for file logging (console only)")

    results = []
    min_contrast = 999.0
    dip_freq = None

    print("\nFreq (MHz) | Contrast | Status")
    print("-----------+----------+-----------------------")

    for idx, f in enumerate(frequencies, 1):
        c = payload.measure_contrast(f, timeout=10.0)
        if c is not None:
            results.append((f, c))
            if c < min_contrast:
                min_contrast = c
                dip_freq = f
            if sd_file:
                try:
                    sd_file.write(f"{f},{c:.4f}\n")
                    sd_file.flush()
                except Exception:
                    pass

            # Visual progress bar
            pct = int((idx / total_pts) * 100)
            bar = "=" * (pct // 10) + " " * (10 - (pct // 10))
            print(f" {f:4d} MHz  |   {c:6.4f} | [{bar}] {pct}%")
        else:
            print(f" {f:4d} MHz  |   FAILED | TIMEOUT")

    if sd_file:
        try:
            sd_file.close()
        except Exception:
            pass

    print("-------------------------------------------------")
    print(f"✓ Sweep complete: {len(results)}/{total_pts} points captured")
    if dip_freq:
        print(
            f"✓ Minimum contrast detected: {min_contrast:.4f} at {dip_freq} MHz"
        )
    return len(results) > 0


def run_automated_selftest():
    print("\n========================================================")
    print("        PAYLOAD AUTOMATED REGRESSION SELF-TEST          ")
    print("========================================================")

    tests = [
        ("1. Ping Link Check", test_ping),
        ("2. Hardware Status Query", test_status),
        ("3. Enable 5V Sensor Rail", lambda: payload.set_rail(5, True)),
        ("4. Read Photodiode", test_photodiode),
        ("5. Read RTD Sensors", test_rtds),
        ("6. Enable 10V Microwave Rail", lambda: payload.set_rail(10, True)),
        ("7. Single ODMR Point (2870 MHz)", lambda: test_single_contrast(2870)),
        ("8. Disable Power Rails", lambda: payload.set_rail(5, False) and payload.set_rail(10, False)),
    ]

    results = []
    for name, fn in tests:
        print(f"\n>> Executing: {name}")
        try:
            passed = fn()
            results.append((name, passed))
        except Exception as e:
            print(f"Exception during {name}: {e}")
            results.append((name, False))
        time.sleep(0.1)

    print("\n=================== TEST SUMMARY ===================")
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)

    for name, p in results:
        status_tag = "[PASS]" if p else "[FAIL]"
        print(f" {status_tag} {name}")

    print("----------------------------------------------------")
    pct = (passed_count / total_count) * 100
    print(
        f"Score: {passed_count}/{total_count} Passed ({pct:.1f}%) -> {'ALL PASSED' if passed_count == total_count else 'FAILURES DETECTED'}"
    )
    print("====================================================")
    return passed_count == total_count


def print_menu():
    mode_str = (
        "[MOCK DESKTOP SIMULATION]"
        if is_mock
        else "[CONNECTED TO HARDWARE CUBESAT]"
    )
    print("\n========================================================")
    print("       PyCubed <-> Payload Interactive Test Suite       ")
    print(f"               {mode_str}")
    print("========================================================")
    print("  [1] Ping / Heartbeat Link Check")
    print("  [2] Hardware Status (Rails & Heaters)")
    print("  [3] Read Photodiode (Fluorescence)")
    print("  [4] Read All 7 RTD Temperatures")
    print("  [5] Power Rail 5V Control")
    print("  [6] Power Rail 10V Control")
    print("  [7] Thermal Heaters IN1..IN4 Control")
    print("  [8] Single ODMR Contrast Point (Command '4')")
    print("  [9] Automated ODMR Frequency Sweep")
    print("  [A] Run Automated End-to-End Self-Test")
    print("  [Q] Exit back to REPL")
    print("========================================================")


def run():
    """Main interactive REPL loop."""
    print_menu()
    while True:
        try:
            choice = (
                input("\npycubed-test> ").strip().upper()  # noqa: F821
            )
            if not choice:
                continue

            if choice == "1":
                test_ping()
            elif choice == "2":
                test_status()
            elif choice == "3":
                test_photodiode()
            elif choice == "4":
                test_rtds()
            elif choice == "5":
                test_power_rail(5)
            elif choice == "6":
                test_power_rail(10)
            elif choice == "7":
                test_heaters()
            elif choice == "8":
                test_single_contrast()
            elif choice == "9":
                test_odmr_sweep()
            elif choice == "A":
                run_automated_selftest()
            elif choice == "M" or choice == "?":
                print_menu()
            elif choice in ("Q", "QUIT", "EXIT"):
                print(
                    "\nExiting test suite. Returned to CircuitPython REPL (>>>)."
                )
                print("Type 'test_payload.run()' anytime to re-open the menu.")
                break
            else:
                print(
                    f"Unknown option '{choice}'. Type 1..9, A for self-test, M for menu, or Q to quit."
                )

        except (KeyboardInterrupt, EOFError):
            print("\nExiting to REPL.")
            break
        except Exception as e:
            print(f"Error handling choice: {e}")


# Run automatically when imported on CircuitPython, or when run directly
if hasattr(sys, "implementation") and getattr(
    sys.implementation, "name", ""
) in ("circuitpython", "micropython"):
    run()
elif __name__ == "__main__":
    run()
