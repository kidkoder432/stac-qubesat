"""
PayloadUART.py — CircuitPython driver for ESP32-S3 Quantum Diamond Payload.
Uses a simplified, fixed-length binary protocol with modulo-256 checksums over UART (115200 baud).
"""

import struct
import time

START1 = 0x57  # 'W'
START2 = 0xAC

# Packet Response Signatures
RESP_ACK = ord("A")  # 4 bytes total
RESP_NACK = ord("N")  # 4 bytes total
RESP_ERROR = ord("E")  # 6 bytes total
RESP_PD = ord("P")  # 8 bytes total (4 float bytes)
RESP_RTD = ord("R")  # 60 bytes total (56 float bytes)
RESP_STATUS = ord("S")  # 10 bytes total (6 state bytes)
RESP_CONTRAST = ord("W")  # 8 bytes total (4 float bytes: single-point ODMR contrast)

# Error Code Mapping
ERROR_CODES = {
    0x0001: "ERR_BAD_CHECKSUM",
    0x0002: "ERR_UNKNOWN_CMD",
    0x0003: "ERR_RAIL_DISABLED",
    0x0004: "ERR_ADC_TIMEOUT",
    0x0005: "ERR_ADC_CONFIG",
    0x0006: "ERR_MICROWAVE_FAIL",
    0x0007: "ERR_INVALID_PARAM",
}


def calculate_checksum(data: bytes) -> int:
    """Computes modulo-256 sum of all bytes."""
    return sum(data) & 0xFF


def build_command(cmd_char: str, d0: int, d1: int) -> bytes:
    """Builds a uniform 6-byte command packet: [0x57, 0xAC, CMD, D0, D1, CS]."""
    body = struct.pack("BBBBB", START1, START2, ord(cmd_char), d0 & 0xFF, d1 & 0xFF)
    cs = calculate_checksum(body)
    return body + struct.pack("B", cs)


class PayloadUART:
    def __init__(self, satellite=None):
        if satellite is None:
            try:
                from pycubed import cubesat

                satellite = cubesat
            except Exception:
                pass
        self.satellite = satellite
        self.uart = (
            getattr(satellite, "uart", getattr(satellite, "UART", None))
            if satellite
            else None
        )

        # Ensure UART baudrate is 115200 for ESP32 payload link
        if self.uart is not None:
            try:
                if hasattr(self.uart, "baudrate") and self.uart.baudrate != 115200:
                    self.uart.baudrate = 115200
            except Exception:
                try:
                    import board
                    import busio

                    self.uart.deinit()
                    self.uart = busio.UART(board.TX, board.RX, baudrate=115200)
                    if satellite and hasattr(satellite, "uart"):
                        satellite.uart = self.uart
                except Exception:
                    pass

        self.payload_online = False
        self.last_pd = None
        self.last_rtds = None
        self.last_contrast = None

    def send_command(
        self,
        cmd_pkt: bytes,
        expected_type: int,
        expected_len: int,
        timeout: float = 1.0,
        retries: int = 2,
    ):
        """
        Sends a 6-byte command packet and waits for expected response.
        Retries automatically if checksum fails or if NACK is received.
        Returns: (success: bool, data: bytes or None)
        """
        if not self.uart:
            print("[PAYLOAD] UART not available")
            return False, None

        for attempt in range(1, retries + 1):
            # 1. Flush old bytes from UART input buffer
            try:
                while getattr(self.uart, "in_waiting", 0) > 0:
                    self.uart.read(self.uart.in_waiting)
            except Exception:
                pass

            # 2. Transmit 6-byte command packet
            self.uart.write(cmd_pkt)

            # 3. Read loop
            start_time = time.monotonic()
            rx_buf = bytearray()

            while time.monotonic() - start_time < timeout:
                in_waiting = getattr(self.uart, "in_waiting", 0)
                if in_waiting > 0:
                    chunk = self.uart.read(in_waiting)
                    if chunk:
                        rx_buf.extend(chunk)

                # Search for [0x57, 0xAC] header
                if len(rx_buf) >= 2 and (rx_buf[0] != START1 or rx_buf[1] != START2):
                    start_idx = -1
                    for i in range(len(rx_buf) - 1):
                        if rx_buf[i] == START1 and rx_buf[i + 1] == START2:
                            start_idx = i
                            break
                    if start_idx >= 0:
                        rx_buf = rx_buf[start_idx:]
                    else:
                        if rx_buf[-1] == START1:
                            rx_buf = rx_buf[-1:]
                        else:
                            rx_buf.clear()

                # Process packet if at least 3 bytes present
                if len(rx_buf) >= 3:
                    resp_type = rx_buf[2]

                    # Check for NACK (4 bytes)
                    if resp_type == RESP_NACK and len(rx_buf) >= 4:
                        if calculate_checksum(rx_buf[:3]) == rx_buf[3]:
                            print(f"[PAYLOAD] Received NACK on attempt {attempt}")
                            break

                    # Check for ERROR (6 bytes)
                    if resp_type == RESP_ERROR and len(rx_buf) >= 6:
                        if calculate_checksum(rx_buf[:5]) == rx_buf[5]:
                            err_code = (rx_buf[3] << 8) | rx_buf[4]
                            err_name = ERROR_CODES.get(
                                err_code, f"UNKNOWN_0x{err_code:04X}"
                            )
                            print(f"[PAYLOAD] Error: {err_name} (0x{err_code:04X})")
                            return False, None

                    # Consume intermediate ACK if awaiting data
                    if (
                        resp_type == RESP_ACK
                        and expected_type != RESP_ACK
                        and len(rx_buf) >= 4
                    ):
                        if calculate_checksum(rx_buf[:3]) == rx_buf[3]:
                            rx_buf = rx_buf[4:]
                            continue

                    # Check for expected packet
                    if resp_type == expected_type and len(rx_buf) >= expected_len:
                        frame = bytes(rx_buf[:expected_len])
                        computed_cs = calculate_checksum(frame[:-1])
                        received_cs = frame[-1]

                        if computed_cs != received_cs:
                            print(
                                f"[PAYLOAD] Checksum mismatch (got 0x{received_cs:02X}, expected 0x{computed_cs:02X})"
                            )
                            # Send NACK back
                            nack_pkt = bytes(
                                [
                                    START1,
                                    START2,
                                    RESP_NACK,
                                    (START1 + START2 + RESP_NACK) & 0xFF,
                                ]
                            )
                            self.uart.write(nack_pkt)
                            break

                        # Checksum valid! Extract payload bytes
                        return True, frame[3:-1]

                time.sleep(0.01)

            print(
                f"[PAYLOAD] Comms timeout on attempt {attempt}/{retries} for cmd 0x{cmd_pkt[2]:02X}"
            )

        return False, None

    # ======================= HIGH-LEVEL API =======================

    def ping(self) -> bool:
        """Sends Heartbeat/Ping ('1', 'H', 'B'). Returns True on ACK."""
        cmd = build_command("1", ord("H"), ord("B"))
        success, _ = self.send_command(
            cmd, expected_type=RESP_ACK, expected_len=4, timeout=1.0
        )
        self.payload_online = success
        return success

    def read_photodiode(self) -> float | None:
        """Requests photodiode reading ('P', 'P', 'D'). Returns photocurrent in Amperes."""
        cmd = build_command("P", ord("P"), ord("D"))
        success, data = self.send_command(
            cmd, expected_type=RESP_PD, expected_len=8, timeout=1.5
        )
        if success and data and len(data) >= 4:
            val = struct.unpack("<f", data[:4])[0]
            self.last_pd = val
            return val
        return None

    def read_rtds(self) -> list | None:
        """Requests 7 RTD temperatures and resistances ('R', 'R', 'T')."""
        cmd = build_command("R", ord("R"), ord("T"))
        success, data = self.send_command(
            cmd, expected_type=RESP_RTD, expected_len=60, timeout=2.5
        )
        if success and data and len(data) >= 56:
            floats = struct.unpack("<14f", data[:56])
            results = []
            for i in range(7):
                results.append(
                    {"channel": i + 1, "temp": floats[2 * i], "res": floats[2 * i + 1]}
                )
            self.last_rtds = results
            return results
        return None

    def measure_contrast(self, freq_mhz: int, timeout: float = 30.0) -> float | None:
        """
        Requests single-frequency ODMR optical contrast measurement at freq_mhz (2800..2950 MHz).
        Encodes freq_mhz across d0 and d1: cmd = '4', d0 = MSB, d1 = LSB.
        Returns optical contrast ratio (~0.85 to 1.0) or None on error/timeout.
        """
        if not (2800 <= freq_mhz <= 2950):
            print(
                f"[PAYLOAD] Frequency out of range: {freq_mhz} MHz (must be 2800-2950)"
            )
            return None

        d0 = (freq_mhz >> 8) & 0xFF
        d1 = freq_mhz & 0xFF
        cmd = build_command("4", d0, d1)

        success, data = self.send_command(
            cmd, expected_type=RESP_CONTRAST, expected_len=8, timeout=timeout, retries=1
        )
        if success and data and len(data) >= 4:
            contrast = struct.unpack("<f", data[:4])[0]
            self.last_contrast = contrast
            return contrast
        return None

    def set_rail(self, rail: int, state: bool) -> bool:
        """Controls 5V (rail=5) or 10V (rail=10) rail state."""
        d0 = 0x00 if rail == 5 else 0xFF
        d1 = 0xFF if state else 0x00
        cmd = build_command("2", d0, d1)
        success, _ = self.send_command(cmd, expected_type=RESP_ACK, expected_len=4)
        return success

    def set_heater(self, heater_num: int, state: bool) -> bool:
        """Controls heater IN1..IN4."""
        d1 = 0xFF if state else 0x00
        cmd = build_command("3", heater_num, d1)
        success, _ = self.send_command(cmd, expected_type=RESP_ACK, expected_len=4)
        return success

    def get_status(self) -> dict | None:
        """Queries rail and heater GPIO states."""
        cmd = build_command("5", ord("G"), ord("S"))
        success, data = self.send_command(
            cmd, expected_type=RESP_STATUS, expected_len=10
        )
        if success and data and len(data) >= 6:
            return {
                "v5_rail": bool(data[0]),
                "10v_rail": bool(data[1]),
                "in1": bool(data[2]),
                "in2": bool(data[3]),
                "in3": bool(data[4]),
                "in4": bool(data[5]),
            }
        return None
