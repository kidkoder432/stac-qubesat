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
    [7] Heaters: inspect, set (with readback), run with live RTD monitor
    [8] Single-Frequency ODMR Point Contrast Measurement
    [9] ODMR Frequency Sweep, custom range (cancellable, optional SD logging)
    [F] FULL ODMR sweep 2800..2950 MHz, 1 MHz steps (cancellable)
    [P] Photodiode stream (repeated reads with statistics, cancellable)
    [T] RTD monitor (repeated reads, cancellable)
    [A] Automated End-to-End Regression Self-Test
    [Q] Exit back to REPL

Cancelling a long operation: press Enter (any key on the board) to stop after the current point,
or Ctrl-C to stop immediately. Heaters are always switched off again when a heater run ends.
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
        self.baudrate = 115200
        self._heat = 0.0  # fake warming: rises on each RTD read while a heater is on

    def deinit(self):  # PayloadUART re-creates the UART on the board; nothing to do here
        pass

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
                if any(self.heaters):
                    self._heat += 0.4
                else:
                    self._heat = max(0.0, self._heat - 0.4)
                # 7 pairs of [temp, res]
                floats = [
                    22.5 + self._heat,
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
        from hardware import cubesat  # the one hardware import every module shares

        sat = cubesat
        if getattr(sat, "uart", None) is not None:
            return PayloadUART(sat), False
    except Exception:
        pass

    # Fallback to desktop mock. PayloadUART re-creates the UART with board/busio, which do not
    # exist on a desktop, so give it stand-ins that hand back the mock.
    bridge = MockUARTBridge()
    try:
        import board  # noqa: F401
        import busio  # noqa: F401
    except ImportError:
        import types

        fake_board = types.ModuleType("board")
        fake_board.TX2 = fake_board.RX2 = None
        fake_busio = types.ModuleType("busio")
        fake_busio.UART = lambda *a, **k: bridge
        sys.modules["board"] = fake_board
        sys.modules["busio"] = fake_busio

    class MockSatellite:
        def __init__(self):
            self.uart = bridge

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


# ======================= HELPERS: cancel, drain, text plots =======================

LOG_PATH = "/sd/odmr_test.csv"  # sweep log (console only if there is no SD card)


def _cancel_requested():
    """
    True if the user pressed Enter / any key since the last check. Never blocks.
    On the board this reads the USB serial console; on a desktop it reads stdin.
    """
    try:
        import supervisor

        n = supervisor.runtime.serial_bytes_available
        if n:
            sys.stdin.read(n)
            return True
        return False
    except ImportError:
        pass  # not CircuitPython: fall through to the desktop check
    except Exception:
        return False
    try:
        import select

        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.readline() != ""  # "" = end of input, not a keypress
    except Exception:
        pass
    return False


def _wait_or_cancel(seconds):
    """Sleep for `seconds`, returning True early if the user asked to cancel."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if _cancel_requested():
            return True
        time.sleep(min(0.1, max(0.0, end - time.monotonic())))
    return False


def _drain_uart():
    """Discard bytes left in the UART after a cancelled command (the driver also flushes before each command)."""
    try:
        u = payload.uart
        while getattr(u, "in_waiting", 0) > 0:
            u.read(u.in_waiting)
    except Exception:
        pass


def _sparkline(values, width=60):
    """One line of text showing how `values` (None = missing) change: ' ' lowest ... '@' highest."""
    pts = [v for v in values if v is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(pts), max(pts)
    n = len(values)
    width = min(width, n)
    if hi == lo:
        return "-" * width
    chars = " .:-=+*#%@"
    out = ""
    for b in range(width):
        a = b * n // width
        z = max(a + 1, (b + 1) * n // width)
        chunk = [v for v in values[a:z] if v is not None]
        if not chunk:
            out += "?"
            continue
        m = sum(chunk) / len(chunk)
        out += chars[int((m - lo) / (hi - lo) * (len(chars) - 1))]
    return out


def _ask_number(prompt, default, lo=None, hi=None, as_int=False):
    """input() with a default; returns None for a bad or out-of-range answer."""
    raw = input(f"{prompt} [{default}]: ").strip() or str(default)
    try:
        v = int(raw) if as_int else float(raw)
    except ValueError:
        print("Invalid number")
        return None
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        print(f"Must be between {lo} and {hi}")
        return None
    return v


# ======================= HEATERS: inspect, set, run =======================


def _print_hw_state():
    st = payload.get_status()
    if not st:
        print("✗ Could not read hardware status")
        return None
    print(f"  Rails:   5V {'ON' if st['v5_rail'] else 'OFF'} | 10V {'ON' if st['10v_rail'] else 'OFF'}")
    print(
        "  Heaters: "
        + " | ".join(f"IN{n} {'ON' if st[f'in{n}'] else 'OFF'}" for n in (1, 2, 3, 4))
    )
    return st


def _set_heater_checked(n, on):
    """Set heater n, then read the status back to confirm the board really did it."""
    ok = payload.set_heater(n, on)
    st = payload.get_status()
    actual = None if not st else st[f"in{n}"]
    if ok and actual == on:
        print(f"✓ Heater IN{n} is {'ON' if on else 'OFF'} (confirmed by status readback)")
        return True
    print(
        f"✗ Heater IN{n} -> {'ON' if on else 'OFF'} not confirmed "
        f"(ack={ok}, readback={'?' if actual is None else ('ON' if actual else 'OFF')})"
    )
    return False


def _all_heaters_off():
    ok = True
    for n in (1, 2, 3, 4):
        ok = payload.set_heater(n, False) and ok
    st = payload.get_status()
    confirmed = bool(st) and not any(st[f"in{n}"] for n in (1, 2, 3, 4))
    print("✓ All heaters OFF (confirmed)" if (ok and confirmed) else "✗ Could not confirm all heaters are OFF")
    return ok and confirmed


def _heater_run(n):
    """Heater n ON with a live RTD readout, until the time is up or the user cancels. Always ends with the heater OFF."""
    minutes = _ask_number(f"Run heater IN{n} for how many minutes", 2, 0.05, 30)
    interval = _ask_number("Seconds between readings", 5, 1, 120)
    if minutes is None or interval is None:
        return False
    if not _set_heater_checked(n, True):
        _all_heaters_off()
        return False

    print("Press Enter (any key on the board) to stop, or Ctrl-C. The heater is switched OFF on exit.")
    print("\n t (s) | heater | RTD temperatures (°C)                              | biggest rise since start")
    print("-------+--------+----------------------------------------------------+-------------------------")
    start = time.monotonic()
    first = None
    try:
        while time.monotonic() - start < minutes * 60:
            rtds = payload.read_rtds()
            st = payload.get_status()
            heater = "?" if not st else ("ON " if st[f"in{n}"] else "OFF")
            if rtds:
                temps = [r["temp"] for r in rtds]
                if first is None:
                    first = temps
                rises = [t - f0 for t, f0 in zip(temps, first)]
                k = max(range(len(rises)), key=lambda i: rises[i])
                shown = " ".join(f"{t:5.1f}" for t in temps)
                print(f" {time.monotonic() - start:5.0f} |  {heater}   | {shown} | {rises[k]:+.2f} °C (RTD{k + 1})")
            else:
                print(f" {time.monotonic() - start:5.0f} |  {heater}   | RTD read failed")
            if _wait_or_cancel(interval):
                print("Cancelled by user.")
                break
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl-C).")
        _drain_uart()
    finally:
        print("Switching heater OFF...")
        payload.set_heater(n, False)
        _set_heater_checked(n, False)
        print("(If you do not see a confirmation above, use [a] All heaters OFF.)")
    return True


def test_heaters():
    print("\n--- [7] Thermal Heaters IN1..IN4 ---")
    while True:
        print("\nHeaters:  [s] show state   [1-4] set a heater (with readback)   [a] all OFF")
        print("          [r] run a heater with a live RTD monitor   [b] back")
        choice = input("heaters> ").strip().lower()
        if choice in ("", "b", "back", "q"):
            return True
        if choice == "s":
            _print_hw_state()
        elif choice == "a":
            _all_heaters_off()
        elif choice in ("1", "2", "3", "4"):
            n = int(choice)
            st = payload.get_status()
            current = bool(st and st[f"in{n}"])
            raw = input(f"Set Heater IN{n} [1 = ON, 0 = OFF, Enter = toggle (now {'ON' if current else 'OFF'})]: ").strip()
            on = (raw == "1") if raw in ("0", "1") else (not current)
            _set_heater_checked(n, on)
        elif choice == "r":
            n = _ask_number("Which heater (1..4)", 1, 1, 4, as_int=True)
            if n is not None:
                _heater_run(n)
        else:
            print("Unknown option")


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


# ======================= SWEEPS, PHOTODIODE, RTD MONITOR =======================

last_sweep = {}  # result of the most recent sweep, for inspection from the REPL (test_payload.last_sweep)


def _open_log(total, with_pd):
    try:
        fh = open(LOG_PATH, "a")
        fh.write(f"# ODMR sweep start: {time.monotonic()} | Points: {total}\n")
        fh.write("freq_mhz,contrast,photodiode_a\n" if with_pd else "freq_mhz,contrast\n")
        print(f"✓ Logging sweep points to {LOG_PATH}")
        return fh
    except Exception:
        print("Notice: SD card not available for file logging (console only)")
        return None


def _run_sweep(frequencies, with_pd=True, timeout=30.0):
    """
    One ODMR point per frequency over UART: contrast ('4') and, if with_pd, the photodiode ('P')
    like the FSM's SCIENCE state does. Cancel with Enter (stops after the current point) or Ctrl-C.
    Returns True if at least one point was captured. Details are left in `last_sweep`.
    """
    global last_sweep
    total = len(frequencies)
    print(f"Sweep: {total} points, {frequencies[0]} to {frequencies[-1]} MHz, per-point timeout {timeout:.0f} s.")
    print("Press Enter (any key on the board) to cancel after the current point, or Ctrl-C to stop now.")
    log = _open_log(total, with_pd)

    rows = []  # (freq, contrast, photodiode or None)
    failed = 0
    latencies = []
    cancelled = False
    print("\nFreq (MHz) | Contrast | Photodiode (A) | Latency | Progress")
    print("-----------+----------+----------------+---------+-------------------")
    t_start = time.monotonic()
    try:
        for idx, f in enumerate(frequencies, 1):
            if _cancel_requested():
                cancelled = True
                break
            t0 = time.monotonic()
            c = payload.measure_contrast(f, timeout=timeout)
            pd = payload.read_photodiode() if (with_pd and c is not None) else None
            dt = time.monotonic() - t0
            pct = int(idx * 100 / total)
            bar = "=" * (pct // 10) + " " * (10 - pct // 10)
            if c is None:
                failed += 1
                print(f" {f:4d} MHz  |  FAILED  |       -        | {dt:5.1f} s | [{bar}] {pct}%")
                continue
            latencies.append(dt)
            rows.append((f, c, pd))
            pd_txt = "      ERR       " if (with_pd and pd is None) else (f" {pd:.4e}   " if with_pd else "       -        ")
            print(f" {f:4d} MHz  |  {c:6.4f}  |{pd_txt}| {dt:5.1f} s | [{bar}] {pct}%")
            if log:
                try:
                    if with_pd:
                        log.write(f"{f},{c:.4f},{'ERR' if pd is None else format(pd, '.4e')}\n")
                    else:
                        log.write(f"{f},{c:.4f}\n")
                    log.flush()
                except Exception:
                    pass
    except KeyboardInterrupt:
        cancelled = True
        _drain_uart()
        print("\nInterrupted (Ctrl-C).")
    finally:
        if log:
            try:
                log.close()
            except Exception:
                pass

    elapsed = time.monotonic() - t_start
    last_sweep = {
        "rows": rows,
        "failed": failed,
        "cancelled": cancelled,
        "elapsed_s": elapsed,
        "planned": total,
    }
    print("-----------+----------+----------------+---------+-------------------")
    print(
        f"{'✗ Sweep CANCELLED' if cancelled else '✓ Sweep complete'}: {len(rows)}/{total} points captured, "
        f"{failed} failed, {elapsed:.1f} s"
    )
    if latencies:
        print(f"  Per-point time: mean {sum(latencies) / len(latencies):.2f} s, max {max(latencies):.2f} s")
    if rows:
        f_min, c_min, _ = min(rows, key=lambda r: r[1])
        print(f"  Minimum contrast {c_min:.4f} at {f_min} MHz")
        line = _sparkline([r[1] for r in rows])
        if line:
            print(f"  contrast   [{line}]  (' ' lowest ... '@' highest; {rows[0][0]}..{rows[-1][0]} MHz)")
        pds = [r[2] for r in rows]
        if any(v is not None for v in pds):
            line = _sparkline(pds)
            if line:
                print(f"  photodiode [{line}]")
    return len(rows) > 0


def test_full_sweep():
    print("\n--- [F] FULL ODMR sweep 2800..2950 MHz, 1 MHz steps (contrast + photodiode per point) ---")
    return _run_sweep(list(range(2800, 2951)), with_pd=True, timeout=30.0)


def test_odmr_sweep():
    print("\n--- [9] ODMR Frequency Sweep (custom range) ---")
    f_start = _ask_number("Start frequency in MHz", 2800, 2800, 2950, as_int=True)
    f_stop = _ask_number("Stop frequency in MHz", 2950, 2800, 2950, as_int=True)
    f_step = _ask_number("Step size in MHz", 10, 1, 150, as_int=True)
    if None in (f_start, f_stop, f_step) or f_start > f_stop:
        print("Invalid frequency range or step size")
        return False
    return _run_sweep(list(range(f_start, f_stop + 1, f_step)), with_pd=False, timeout=10.0)


def test_photodiode_stream():
    print("\n--- [P] Photodiode stream ---")
    count = _ask_number("Number of readings (0 = until cancelled)", 20, 0, 100000, as_int=True)
    interval = _ask_number("Seconds between readings", 0.5, 0.0, 60)
    if count is None or interval is None:
        return False
    print("Press Enter (any key on the board) to stop, or Ctrl-C.")
    vals = []
    failed = 0
    try:
        while count == 0 or len(vals) + failed < count:
            v = payload.read_photodiode()
            if v is None:
                failed += 1
                print(f"  #{len(vals) + failed:4d}  FAILED")
            else:
                vals.append(v)
                print(f"  #{len(vals) + failed:4d}  {v:.4e} A  ({v * 1e9:8.1f} nA)")
            if _wait_or_cancel(interval):
                print("Cancelled by user.")
                break
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl-C).")
        _drain_uart()
    if vals:
        mean = sum(vals) / len(vals)
        spread = (sum((x - mean) ** 2 for x in vals) / len(vals)) ** 0.5
        print(f"✓ {len(vals)} readings ({failed} failed): min {min(vals):.4e}  max {max(vals):.4e}  mean {mean:.4e}  std {spread:.2e} A")
    else:
        print("✗ No successful readings")
    return bool(vals)


def test_rtd_monitor():
    print("\n--- [T] RTD monitor ---")
    count = _ask_number("Number of readings (0 = until cancelled)", 10, 0, 100000, as_int=True)
    interval = _ask_number("Seconds between readings", 2, 0.0, 600)
    if count is None or interval is None:
        return False
    print("Press Enter (any key on the board) to stop, or Ctrl-C.")
    lo = [None] * 7
    hi = [None] * 7
    done = 0
    failed = 0
    try:
        while count == 0 or done + failed < count:
            rtds = payload.read_rtds()
            if not rtds:
                failed += 1
                print(f"  #{done + failed:4d}  RTD read FAILED")
            else:
                done += 1
                temps = [r["temp"] for r in rtds]
                for i, t in enumerate(temps):
                    lo[i] = t if lo[i] is None else min(lo[i], t)
                    hi[i] = t if hi[i] is None else max(hi[i], t)
                print(f"  #{done + failed:4d}  " + " ".join(f"{t:6.2f}" for t in temps))
            if _wait_or_cancel(interval):
                print("Cancelled by user.")
                break
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl-C).")
        _drain_uart()
    if done:
        print(f"✓ {done} readings ({failed} failed). Per channel min..max (°C):")
        for i in range(7):
            print(f"   RTD{i + 1}: {lo[i]:.2f} .. {hi[i]:.2f}")
    else:
        print("✗ No successful readings")
    return done > 0


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
    print("  [7] Heaters: inspect, set, run with live RTD monitor")
    print("  [8] Single ODMR Contrast Point (Command '4')")
    print("  [9] ODMR Frequency Sweep (custom range)")
    print("  [F] FULL ODMR sweep 2800..2950 MHz, 1 MHz steps")
    print("  [P] Photodiode stream (repeated reads + stats)")
    print("  [T] RTD monitor (repeated reads)")
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
            elif choice == "F":
                test_full_sweep()
            elif choice == "P":
                test_photodiode_stream()
            elif choice == "T":
                test_rtd_monitor()
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
                    f"Unknown option '{choice}'. Type 1..9, F, P, T, A for self-test, M for menu, or Q to quit."
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
