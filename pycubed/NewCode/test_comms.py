"""
Desktop tests for Comms.py. The first group is Tyler's (tinygs branch of ArcticaNova/qubesat,
unit_tests/test_newcode_comms.py), adapted to the merged Comms: the state callback now gets
(code, lock). The second group covers what the merge added: the lock bit, no dedup in Comms,
the radio error counter and the 437.42 MHz carrier.

Run from this directory:   python3 test_comms.py
"""
import sys
import types
import unittest

sys.path.insert(0, '.')


class FakeRadio:
    """Mimics pycubed_rfm9x's RadioHead header handling: send() prepends a 4-byte
    header (destination, node, identifier, flags); receive() drops packets under
    5 bytes, filters on destination vs node, and strips the header unless
    with_header=True."""

    def __init__(self):
        self.node = 0xFF
        self.destination = 0xFF
        self.identifier = 0
        self.flags = 0
        self.air = []     # every packet sent, exactly as it would appear on air
        self.inbox = []   # on-air packets waiting to be received
        self.regs = {}

    def _write_u8(self, address, val):
        self.regs[address] = val

    def sleep(self):
        pass

    def idle(self):
        pass

    def send(self, data, *, keep_listening=False, destination=None, node=None,
             identifier=None, flags=None):
        assert 0 < len(data) <= 252
        header = bytes([
            self.destination if destination is None else destination,
            self.node if node is None else node,
            self.identifier if identifier is None else identifier,
            self.flags if flags is None else flags,
        ])
        self.air.append(header + bytes(data))
        return True

    def receive(self, *, keep_listening=True, with_header=False, with_ack=False,
                timeout=None, debug=False, view=False):
        if not self.inbox:
            return None
        packet = self.inbox.pop(0)
        if len(packet) < 5:
            return None
        if self.node != 0xFF and packet[0] != 0xFF and packet[0] != self.node:
            return None
        return bytes(packet if with_header else packet[4:])


# Comms.py imports the board object from hardware.py, which falls back to `pycubed` on a desktop;
# give it a fake board.
_fake_pycubed = types.ModuleType('pycubed')
_fake_pycubed.cubesat = types.SimpleNamespace(hardware={"Radio1": True}, radio1=FakeRadio())
sys.modules['pycubed'] = _fake_pycubed

import Comms
import tinygs_decoder


class TestNewCodeComms(unittest.TestCase):

    def setUp(self):
        _fake_pycubed.cubesat.radio1 = FakeRadio()
        self.radio = Comms.configure_radio()
        self.comms = Comms.CommsManager(self.radio, default_modulation=Comms.LORA)
        self.comms.state_code = Comms.STATE_IDLE

    def test_configure_radio_sets_sync_word_and_broadcast_node(self):
        self.assertEqual(self.radio.regs[0x39], 0x12)
        self.assertEqual(self.radio.node, 0xFF)

    def test_beacon_on_air_is_16_bytes_and_decodes(self):
        self.comms.push_telemetry(Comms.build_beacon_packet(Comms.STATE_SCIENCE, 7.4, 25.3, 99))
        self.comms._tx_tick()
        on_air = self.radio.air[-1]
        self.assertEqual(len(on_air), 16)
        self.assertEqual(on_air[0], Comms.HDR_TELEMETRY)
        decoded = tinygs_decoder.decode(on_air)
        self.assertEqual(decoded["state_name"], "SCIENCE")
        self.assertEqual(decoded["battery_v"], 7.4)
        self.assertEqual(decoded["temperature_c"], 25)
        self.assertEqual(decoded["mission_time_s"], 99)

    def test_beacon_with_missing_sensors_encodes_unknown(self):
        packet = Comms.build_beacon_packet(Comms.STATE_IDLE, None, None, 120)
        decoded = tinygs_decoder.decode(bytes([Comms.HDR_TELEMETRY]) + packet)
        self.assertIsNone(decoded["battery_v"])
        self.assertIsNone(decoded["temperature_c"])
        self.assertEqual(decoded["state_name"], "IDLE")

    def test_ground_state_command_round_trip(self):
        ground = FakeRadio()
        received = []
        self.comms.on_state_command = lambda code, lock: received.append((code, lock))
        Comms.send_raw(ground, Comms.build_state_command(Comms.STATE_COMMS))
        self.radio.inbox.append(ground.air[-1])
        self.assertTrue(self.comms._rx_tick())
        self.assertEqual(received, [(Comms.STATE_COMMS, False)])
        self.assertEqual(self.comms.state_code, Comms.STATE_COMMS)

    def test_send_raw_pads_short_packets(self):
        Comms.send_raw(self.radio, bytes([Comms.HDR_AMATEUR, 0x01]))
        self.assertEqual(self.radio.air[-1], bytes([Comms.HDR_AMATEUR, 0x01, 0, 0, 0]))

    def test_fresh_nvm_uses_default_schedule(self):
        for blank in (0x00, 0xFF):
            Comms._nvm[Comms._NVM_CFG_RX] = blank
            Comms._nvm[Comms._NVM_CFG_TX] = blank
            Comms._nvm[Comms._NVM_CFG_CAD] = blank
            config = Comms.CommsConfig()
            self.assertEqual(
                (config.rx_ticks, config.tx_packet_count, config.telem_cadence),
                (Comms.CommsConfig.DEFAULT_RX_TICKS,
                 Comms.CommsConfig.DEFAULT_TX_PACKET_COUNT,
                 Comms.CommsConfig.DEFAULT_TELEM_CADENCE))

    def test_nvm_does_not_overlap_pycubed(self):
        pycubed_bytes = {0, 6, 7, 9, 10, 11, 16}
        ours = {Comms._NVM_S1, Comms._NVM_S2, Comms._NVM_S3, Comms._NVM_CS,
                Comms._NVM_CFG_RX, Comms._NVM_CFG_TX, Comms._NVM_CFG_CAD}
        self.assertFalse(ours & pycubed_bytes)


class TestMergedChanges(unittest.TestCase):
    """Lock bit, no dedup, radio_errors, frequency. (reconfigure() is tested in test_dual_mode_radio.py.)"""

    def setUp(self):
        _fake_pycubed.cubesat.radio1 = FakeRadio()
        self.radio = Comms.configure_radio()
        self.comms = Comms.CommsManager(self.radio, default_modulation=Comms.LORA)
        self.comms.state_code = Comms.STATE_IDLE
        self.got = []
        self.comms.on_state_command = lambda code, lock: self.got.append((code, lock))

    def send_command(self, packet):
        ground = FakeRadio()
        Comms.send_raw(ground, packet)
        self.radio.inbox.append(ground.air[-1])
        self.comms._rx_tick()

    def test_carrier_is_437_42_mhz(self):
        self.assertAlmostEqual(Comms.FREQ_MHZ, 437.42)
        self.assertAlmostEqual(self.radio.frequency_mhz, 437.42)

    def test_lock_bit_is_bit_7_of_the_state_byte_and_defaults_to_off(self):
        plain = Comms._decrypt(Comms.build_state_command(Comms.STATE_SCIENCE)[1:])
        locked = Comms._decrypt(Comms.build_state_command(Comms.STATE_SCIENCE, lock=True)[1:])
        self.assertEqual(plain[1], Comms.STATE_SCIENCE)
        self.assertEqual(locked[1], Comms.STATE_SCIENCE | 0x80)
        self.assertEqual((locked[1] ^ locked[-2]), 0xFF)  # complement check still holds

    def test_lock_reaches_the_fsm_callback_but_not_the_stored_state_code(self):
        self.send_command(Comms.build_state_command(Comms.STATE_SCIENCE, lock=True))
        self.assertEqual(self.got, [(Comms.STATE_SCIENCE, True)])
        self.assertEqual(self.comms.state_code, Comms.STATE_SCIENCE)  # 7-bit code only
        self.send_command(Comms.build_state_command(Comms.STATE_SCIENCE, lock=False))
        self.assertEqual(self.got[-1], (Comms.STATE_SCIENCE, False))

    def test_every_repeat_reaches_the_fsm_and_nvm_is_written_once(self):
        writes = []
        real = Comms._nvm_write_state
        Comms._nvm_write_state = lambda c: (writes.append(c), real(c))
        try:
            for _ in range(4):
                self.send_command(Comms.build_state_command(Comms.STATE_COMMS))
        finally:
            Comms._nvm_write_state = real
        self.assertEqual(len(self.got), 4)
        self.assertEqual(writes, [Comms.STATE_COMMS])

    def test_a_command_equal_to_the_stored_code_is_still_delivered(self):
        """Stored code is IDLE (the last ground command). The FSM may have moved on since."""
        self.send_command(Comms.build_state_command(Comms.STATE_IDLE))
        self.assertEqual(self.got, [(Comms.STATE_IDLE, False)])

    def test_stop_command_and_unknown_code(self):
        self.send_command(Comms.build_state_command(Comms.STATE_STOP))
        self.assertEqual(self.got, [(Comms.STATE_STOP, False)])
        self.assertEqual(self.comms.state_code, Comms.STATE_STOP)
        body = bytes([Comms.CMD_SET_STATE, 99, (~99) & 0xFF])
        self.send_command(bytes([Comms.HDR_COMMAND]) + Comms._encrypt(body + bytes([Comms._crc8(body)])))
        self.assertEqual(len(self.got), 1)

    def test_radio_errors_count_in_a_row_and_clear_after_a_good_call(self):
        def boom(**kw):
            raise RuntimeError("spi")
        good = self.radio.receive
        self.radio.receive = boom
        for _ in range(3):
            self.comms._receive()
        self.assertEqual(self.comms.radio_errors, 3)
        self.radio.receive = good
        self.comms._receive()
        self.assertEqual(self.comms.radio_errors, 0)

    def test_tx_errors_count_too(self):
        self.radio.send = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("spi"))
        self.comms._send(Comms.HDR_TELEMETRY, b"abcd")
        self.assertEqual(self.comms.radio_errors, 1)


if __name__ == '__main__':
    unittest.main()
