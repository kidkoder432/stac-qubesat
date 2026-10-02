import struct
import tasko
from time import monotonic
from Tasks.log import LogTask as Task

# ======================= PACKET PROTOCOL CONSTANTS =======================

START1 = 0x57
START2 = 0xAC

# Packet Types (Master/Slave response indicator)
PKT_TYPE_DATA  = 0x01
PKT_TYPE_ACK   = 0x06
PKT_TYPE_NACK  = 0x15
PKT_TYPE_ERROR = 0x20

# Command Types (Sent from OBC master to Payload ESP32)
PKT_CMD_PING       = 0x08
PKT_CMD_READ_PD    = 0x10
PKT_CMD_READ_RTD   = 0x11
PKT_CMD_SWEEP      = 0x12
PKT_CMD_SET_RAIL   = 0x13
PKT_CMD_SET_HEATER = 0x14
PKT_CMD_GET_STATUS = 0x15

# Error Codes
ERR_NONE               = 0x00
ERR_BAD_CRC            = 0x01
ERR_UNKNOWN_CMD        = 0x02
ERR_RAIL_NOT_ENABLED   = 0x03
ERR_AD4130_TIMEOUT     = 0x04
ERR_AD4130_CONFIG_FAIL = 0x05
ERR_MICROWAVE_FAIL     = 0x06
ERR_INVALID_PARAM      = 0x07
ERR_BUSY               = 0x08

ERROR_NAMES = {
    ERR_NONE: "ERR_NONE",
    ERR_BAD_CRC: "ERR_BAD_CRC (CRC mismatch)",
    ERR_UNKNOWN_CMD: "ERR_UNKNOWN_CMD (Unrecognized command)",
    ERR_RAIL_NOT_ENABLED: "ERR_RAIL_NOT_ENABLED (Power rail disabled)",
    ERR_AD4130_TIMEOUT: "ERR_AD4130_TIMEOUT (ADC conversion timeout)",
    ERR_AD4130_CONFIG_FAIL: "ERR_AD4130_CONFIG_FAIL (AD4130 setup failure)",
    ERR_MICROWAVE_FAIL: "ERR_MICROWAVE_FAIL (HMC832 synthesizer fault)",
    ERR_INVALID_PARAM: "ERR_INVALID_PARAM (Parameter out of range)",
    ERR_BUSY: "ERR_BUSY (Payload busy with long task)",
}

# ======================= CRC & PACKET FRAMING =======================

def crc16_ccitt(data: bytes) -> int:
    """
    Computes CRC-16-CCITT (Poly: 0x1021, Init: 0xFFFF) across byte buffer.
    Matches ESP32 firmware crc16_ccitt() bit-for-bit.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def build_packet(cmd_type: int, seq: int, payload: bytes = b"") -> bytes:
    """
    Constructs a framed packet:
    [START1(0x57), START2(0xAC), TYPE, SEQ, LEN, PAYLOAD..., CRC_MSB, CRC_LSB]
    """
    length = len(payload)
    if length > 250:
        raise ValueError(f"Payload length {length} exceeds maximum 250 bytes")
    header = struct.pack("BBBBB", START1, START2, cmd_type, seq, length)
    body = header + payload
    crc = crc16_ccitt(body)
    return body + struct.pack(">H", crc)  # Big-endian CRC-16


# ======================= FLIGHT TASK =======================

class task(Task):
    name = "Payload Comms"
    color = "blue"

    # Default execution frequency in Hertz (every 2 seconds)
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
        self.seq = 0
        self.payload_online = False
        self.last_pd_reading = None
        self.last_rtd_readings = None

    async def send_command(self, cmd_type: int, payload: bytes = b"", timeout: float = 1.0, retries: int = 3):
        """
        Sends a command packet to the ESP32 payload and cooperatively awaits response.
        Yields execution to Tasko while waiting for response bytes.
        Returns: (success: bool, err_code: int | None, response_payload: bytes)
        """
        if not self.uart:
            self.debug("UART hardware not available on satellite", level=1)
            return False, None, b""

        for attempt in range(1, retries + 1):
            self.seq = (self.seq + 1) & 0xFF
            packet = build_packet(cmd_type, self.seq, payload)

            # Flush any stale input bytes before sending
            try:
                if hasattr(self.uart, "reset_input_buffer"):
                    self.uart.reset_input_buffer()
                else:
                    while getattr(self.uart, "in_waiting", 0) > 0:
                        self.uart.read(self.uart.in_waiting)
            except Exception:
                pass

            self.uart.write(packet)

            # Cooperative read loop
            start_time = monotonic()
            rx_buf = bytearray()
            packet_len = None

            while monotonic() - start_time < timeout:
                in_waiting = getattr(self.uart, "in_waiting", 0)
                if in_waiting > 0:
                    chunk = self.uart.read(in_waiting)
                    if chunk:
                        rx_buf.extend(chunk)

                # Search for start markers if not aligned
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

                # Once header is received, extract expected total length
                if packet_len is None and len(rx_buf) >= 5:
                    _, _, _, _, plen = struct.unpack("BBBBB", rx_buf[:5])
                    packet_len = 7 + plen

                # Once full packet received, validate CRC and parse
                if packet_len is not None and len(rx_buf) >= packet_len:
                    frame = bytes(rx_buf[:packet_len])
                    rx_payload = frame[5:packet_len - 2]
                    expected_crc = struct.unpack(">H", frame[packet_len - 2:packet_len])[0]
                    computed_crc = crc16_ccitt(frame[:packet_len - 2])

                    if computed_crc != expected_crc:
                        self.debug(f"CRC mismatch on attempt {attempt}: expected 0x{expected_crc:04X}, computed 0x{computed_crc:04X}", level=2)
                        break  # Break inner loop to retry

                    _, _, resp_type, resp_seq, _ = struct.unpack("BBBBB", frame[:5])
                    if resp_seq != self.seq:
                        self.debug(f"Warning: SEQ mismatch (got {resp_seq}, expected {self.seq}), dropping frame", level=2)
                        rx_buf = rx_buf[packet_len:]
                        packet_len = None
                        continue

                    # Process response packet types
                    if resp_type == PKT_TYPE_ACK:
                        return True, ERR_NONE, rx_payload
                    elif resp_type == PKT_TYPE_DATA:
                        return True, ERR_NONE, rx_payload
                    elif resp_type in (PKT_TYPE_NACK, PKT_TYPE_ERROR):
                        err_code = rx_payload[0] if len(rx_payload) > 0 else ERR_NONE
                        err_name = ERROR_NAMES.get(err_code, f"UNKNOWN_ERR_0x{err_code:02X}")
                        self.debug(f"Payload responded {'NACK' if resp_type == PKT_TYPE_NACK else 'ERROR'}: {err_name}", level=1)
                        return False, err_code, rx_payload
                    else:
                        self.debug(f"Unknown response type 0x{resp_type:02X}", level=1)
                        return False, None, rx_payload

                # Yield cooperatively to Tasko scheduler while waiting
                await tasko.sleep(0.02)

            self.debug(f"Payload comms timeout (attempt {attempt}/{retries}) for cmd 0x{cmd_type:02X}", level=2)

        return False, None, b""

    # ======================= HIGH-LEVEL SENSOR API =======================

    async def ping(self) -> bool:
        """Sends ping to payload. Returns True if ACK received."""
        success, _, _ = await self.send_command(PKT_CMD_PING, timeout=0.5, retries=2)
        self.payload_online = success
        return success

    async def read_photodiode(self) -> float | None:
        """
        Reads photodiode photocurrent from AD4130 #2 AIN15.
        Returns photocurrent in Amperes, or None on failure.
        """
        success, _, payload = await self.send_command(PKT_CMD_READ_PD, timeout=1.5)
        if success and len(payload) >= 4:
            photocurrent = struct.unpack("<f", payload[:4])[0]
            self.last_pd_reading = photocurrent
            return photocurrent
        return None

    async def read_rtds(self) -> list[dict] | None:
        """
        Reads all 7 PT1000 RTD sensors.
        Returns a list of 7 dicts with keys 'temp' (°C) and 'res' (Ω), or None.
        """
        success, _, payload = await self.send_command(PKT_CMD_READ_RTD, timeout=2.5)
        if success and len(payload) >= 56:
            values = struct.unpack("<14f", payload[:56])
            results = []
            for i in range(7):
                results.append({
                    "channel": i + 1,
                    "temp": values[2 * i],
                    "res": values[2 * i + 1]
                })
            self.last_rtd_readings = results
            return results
        return None

    async def set_rail(self, rail: int, state: bool) -> bool:
        """Enables (state=True) or disables (state=False) 5V or 10V rail."""
        payload = struct.pack("BB", rail, 1 if state else 0)
        success, _, _ = await self.send_command(PKT_CMD_SET_RAIL, payload)
        return success

    async def set_heater(self, heater_num: int, state: bool) -> bool:
        """Controls heater IN1..IN4 (heater_num: 1..4)."""
        payload = struct.pack("BB", heater_num, 1 if state else 0)
        success, _, _ = await self.send_command(PKT_CMD_SET_HEATER, payload)
        return success

    async def get_status(self) -> dict | None:
        """Queries rail and heater GPIO states from payload."""
        success, _, payload = await self.send_command(PKT_CMD_GET_STATUS)
        if success and len(payload) >= 6:
            v5, v10, in1, in2, in3, in4 = struct.unpack("6B", payload[:6])
            return {
                "5v_rail": bool(v5),
                "10v_rail": bool(v10),
                "heater_1": bool(in1),
                "heater_2": bool(in2),
                "heater_3": bool(in3),
                "heater_4": bool(in4)
            }
        return None

    async def start_sweep(self) -> bool:
        """Commands payload to start microwave contrast sweep experiment."""
        success, _, _ = await self.send_command(PKT_CMD_SWEEP, timeout=1.0)
        return success

    # ======================= MAIN TASK LOOP =======================

    async def main_task(self):
        """
        Periodic task loop executed cooperatively by Tasko.
        Monitors payload health and gathers science telemetry.
        """
        if not self.uart:
            self.debug("UART not initialized, skipping payload task", level=2)
            return

        # 1. Ping Payload ESP32
        online = await self.ping()
        if not online:
            self.debug("Payload board offline or unresponsive", level=2)
            return

        self.debug("Payload board connected", level=1)

        # 2. Sample Photodiode
        pd = await self.read_photodiode()
        if pd is not None:
            self.debug(f"Photocurrent: {pd * 1e9:.3f} nA", level=1, log=True)

        # 3. Sample RTDs
        rtds = await self.read_rtds()
        if rtds is not None:
            active_rtds = [r for r in rtds if r["res"] > 10.0]
            summary = ", ".join([f"RTD{r['channel']}={r['temp']:.1f}°C" for r in active_rtds])
            if summary:
                self.debug(f"RTD Temps: {summary}", level=1, log=True)
