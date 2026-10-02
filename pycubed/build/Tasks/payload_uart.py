import struct
import tasko
from time import monotonic
from typing import List
from Tasks.log import LogTask as Task

# ======================= PROTOCOL DEFINITIONS =======================

START1 = 0x57
START2 = 0xAC

# Packet Response Signatures
RESP_ACK    = ord('A')  # 4 bytes total
RESP_NACK   = ord('N')  # 4 bytes total
RESP_ERROR  = ord('E')  # 6 bytes total
RESP_PD     = ord('P')  # 8 bytes total (4 float bytes)
RESP_RTD    = ord('R')  # 60 bytes total (56 float bytes)
RESP_STATUS = ord('S')  # 10 bytes total (6 state bytes)
RESP_CONTRAST = ord('W') # 608 bytes total (604 uint32 bytes for 151 steps)

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

def calculate_checksum(data: bytearray) -> int:
    """Computes modulo-256 sum of all bytes."""
    return sum(data) & 0xFF

def build_command(cmd_char: str, d0: int, d1: int) -> bytes:
    """Builds a uniform 6-byte command packet: [0x57, 0xAC, CMD, D0, D1, CS]."""
    body = struct.pack("BBBBB", START1, START2, ord(cmd_char), d0 & 0xFF, d1 & 0xFF)
    cs = calculate_checksum(bytearray(body))
    return body + struct.pack("B", cs)


# ======================= FLIGHT TASK =======================

class task(Task):
    name = "Payload Comms"
    color = "blue"

    # Run once every 2 seconds
    frequency = 0.5

    def __init__(self, satellite=None):
        super().__init__()
        if satellite is None:
            try:
                from pycubed import cubesat
                satellite = cubesat
            except Exception:
                pass
        self.satellite = satellite
        self.uart = getattr(satellite, "uart", getattr(satellite, "UART", None)) if satellite else None
        if self.uart is not None:
            try:
                if hasattr(self.uart, "baudrate") and self.uart.baudrate != 115200:
                    self.uart.baudrate = 115200
            except Exception:
                try:
                    import board, busio
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

    async def send_command(self, cmd_pkt: bytes, expected_type: int, expected_len: int, timeout: float = 1.0, retries: int = 3):
        """
        Sends a 6-byte command packet and waits non-blockingly for expected response.
        Retries automatically if checksum fails or if NACK is received.
        Returns: (success: bool, data: bytes or None)
        """
        if not self.uart:
            self.debug("UART not available", level=2)
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

            # 3. Non-blocking cooperative read loop
            start_time = monotonic()
            rx_buf = bytearray()

            while monotonic() - start_time < timeout:
                in_waiting = getattr(self.uart, "in_waiting", 0)
                if in_waiting > 0:
                    chunk = self.uart.read(in_waiting)
                    if chunk:
                        rx_buf.extend(chunk)

                # Search for [0x57, 0xAC] header
                if len(rx_buf) >= 2 and (rx_buf[0] != START1 or rx_buf[1] != START2):
                    for i in range(len(rx_buf) - 1):
                        if rx_buf[i] == START1 and rx_buf[i + 1] == START2:
                            break
                    
                # Check if we have at least 3 bytes to see the response type
                if len(rx_buf) >= 3:
                    resp_type = rx_buf[2]

                    # Check for NACK (4 bytes: [0x57, 0xAC, 'N', CS])
                    if resp_type == RESP_NACK and len(rx_buf) >= 4:
                        if calculate_checksum(rx_buf[:3]) == rx_buf[3]:
                            self.debug(f"Received NACK on attempt {attempt}, retrying...", level=2)
                            break  # Break inner loop to retry

                    # Check for ERROR (6 bytes: [0x57, 0xAC, 'E', ERR_H, ERR_L, CS])
                    if resp_type == RESP_ERROR and len(rx_buf) >= 6:
                        if calculate_checksum(rx_buf[:5]) == rx_buf[5]:
                            err_code = (rx_buf[3] << 8) | rx_buf[4]
                            err_name = ERROR_CODES.get(err_code, f"UNKNOWN_0x{err_code:04X}")
                            self.debug(f"Payload ERROR: {err_name} (0x{err_code:04X})", level=1)
                            return False, None

                    # Consume intermediate ACK when expecting a data packet (e.g. sweep contrast)
                    if resp_type == RESP_ACK and expected_type != RESP_ACK and len(rx_buf) >= 4:
                        if calculate_checksum(rx_buf[:3]) == rx_buf[3]:
                            self.debug("Command acknowledged, awaiting data packet...", level=2)
                            rx_buf = rx_buf[4:]
                            continue

                    # Check for expected packet
                    if resp_type == expected_type and len(rx_buf) >= expected_len:
                        frame = rx_buf[:expected_len]
                        computed_cs = calculate_checksum(frame[:-1])
                        received_cs = frame[-1]

                        if computed_cs != received_cs:
                            self.debug(f"Checksum mismatch on attempt {attempt}: got 0x{received_cs:02X}, expected 0x{computed_cs:02X}", level=2)
                            # Send NACK back to ESP32 to notify it of corrupt reception
                            nack_pkt = bytes([START1, START2, RESP_NACK, (START1 + START2 + RESP_NACK) & 0xFF])
                            self.uart.write(nack_pkt)
                            break  # Break inner loop to retry

                        # Checksum valid! Extract payload bytes between header/type and checksum
                        return True, frame[3:-1]

                # Yield cooperatively to Tasko scheduler
                await tasko.sleep(0.02)

            self.debug(f"Comms timeout (attempt {attempt}/{retries}) for cmd 0x{cmd_pkt[2]:02X}", level=2)

        return False, None

    # ======================= HIGH-LEVEL API =======================

    async def ping(self) -> bool:
        """Sends Heartbeat/Ping ('1', 'H', 'B'). Returns True on ACK."""
        cmd = build_command('1', ord('H'), ord('B'))
        success, _ = await self.send_command(cmd, expected_type=RESP_ACK, expected_len=4, timeout=0.5, retries=2)
        self.payload_online = success
        return success

    async def set_rail(self, rail: int, state: bool) -> bool:
        """
        Sets 5V (rail=5) or 10V (rail=10) rail state (state=True/False).
        Command '2': d0 = 0x00 (5V) or 0xFF (10V), d1 = 0x00 (OFF) or 0xFF (ON).
        """
        d0 = 0x00 if rail == 5 else 0xFF
        d1 = 0xFF if state else 0x00
        cmd = build_command('2', d0, d1)
        success, _ = await self.send_command(cmd, expected_type=RESP_ACK, expected_len=4)
        return success

    async def set_heater(self, heater_num: int, state: bool) -> bool:
        """
        Controls heater IN1..IN4 (heater_num: 1..4).
        Command '3': d0 = heater_num, d1 = 0x00 (OFF) or 0xFF (ON).
        """
        d1 = 0xFF if state else 0x00
        cmd = build_command('3', heater_num, d1)
        success, _ = await self.send_command(cmd, expected_type=RESP_ACK, expected_len=4)
        return success

    async def start_sweep(self) -> bool:
        """Triggers microwave sweep ('4', 'M', 'W'). Returns True on ACK."""
        cmd = build_command('4', ord('M'), ord('W'))
        success, _ = await self.send_command(cmd, expected_type=RESP_ACK, expected_len=4)
        return success

    async def run_sweep_and_get_contrast(self, timeout: float = 60.0) -> list[float] | None:
        """
        Triggers microwave sweep ('4', 'M', 'W') and receives the 151-point ODMR contrast packet.
        Returns list of 151 normalized contrast values (~1.0 with resonance dips),
        or None on timeout or error.
        """
        cmd = build_command('4', ord('M'), ord('W'))
        success, data = await self.send_command(
            cmd,
            expected_type=RESP_CONTRAST,
            expected_len=608,
            timeout=timeout,
            retries=1
        )
        if success and data and len(data) >= 604:
            contrasts = list(struct.unpack("<151f", data[:604]))
            self.last_contrast = contrasts
            return contrasts
        return None

    async def get_status(self) -> dict | None:
        """Queries rail and heater states ('5', 'G', 'S'). Returns state dict."""
        cmd = build_command('5', ord('G'), ord('S'))
        success, data = await self.send_command(cmd, expected_type=RESP_STATUS, expected_len=10)
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

    async def read_photodiode(self) -> float | None:
        """
        Requests photodiode reading ('P', 'P', 'D').
        Returns photocurrent in Amperes, or None on failure.
        """
        cmd = build_command('P', ord('P'), ord('D'))
        success, data = await self.send_command(cmd, expected_type=RESP_PD, expected_len=8, timeout=1.5)
        if success and data and len(data) >= 4:
            photocurrent = struct.unpack("<f", data[:4])[0]
            self.last_pd = photocurrent
            return photocurrent
        return None

    async def read_rtds(self) -> list[dict] | None:
        """
        Requests 7 RTD temperatures and resistances ('R', 'R', 'T').
        Returns list of 7 dicts with keys 'channel', 'temp' (°C), and 'res' (Ω).
        """
        cmd = build_command('R', ord('R'), ord('T'))
        success, data = await self.send_command(cmd, expected_type=RESP_RTD, expected_len=60, timeout=2.5)
        if success and data and len(data) >= 56:
            floats = struct.unpack("<14f", data[:56])
            results = []
            for i in range(7):
                results.append({
                    "channel": i + 1,
                    "temp": floats[2 * i],
                    "res": floats[2 * i + 1]
                })
            self.last_rtds = results
            return results
        return None

    # ======================= MAIN TASK =======================

    async def main_task(self):
        """Periodic task loop executed cooperatively by Tasko."""
        if not self.uart:
            self.debug("UART not initialized", level=2)
            return

        # 1. Ping Payload
        online = await self.ping()
        if not online:
            self.debug("Payload board offline", level=2)
            return

        # 2. Read Photodiode
        pd = await self.read_photodiode()
        if pd is not None:
            self.debug(f"Photocurrent: {pd * 1e9:.3f} nA", level=1, log=True)

        # 3. Read RTDs
        rtds = await self.read_rtds()
        if rtds:
            active = [r for r in rtds if r["res"] > 10.0]
            if active:
                temps = ", ".join([f"RTD{r['channel']}={r['temp']:.1f}°C" for r in active])
                self.debug(f"RTDs: {temps}", level=1, log=True)
