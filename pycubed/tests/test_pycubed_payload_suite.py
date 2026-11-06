"""
test_pycubed_payload_suite.py — Automated verification harness for test_payload.py.
Runs on desktop macOS to test the interactive test suite without physical hardware.
"""

import os
import sys
import unittest
from unittest.mock import patch

# Add NewCode to import path
newcode_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "NewCode")
)
if newcode_dir not in sys.path:
    sys.path.insert(0, newcode_dir)

import test_payload  # noqa: E402


class TestPyCubedPayloadSuite(unittest.TestCase):
    def setUp(self):
        # Ensure fresh mock bridge
        test_payload.payload, test_payload.is_mock = (
            test_payload.init_payload()
        )

    def test_mock_initialization(self):
        """Verify that desktop fallback cleanly instantiates mock bridge."""
        self.assertTrue(test_payload.is_mock)
        self.assertIsNotNone(test_payload.payload)

    def test_ping(self):
        """Verify heartbeat/ping command returns True."""
        self.assertTrue(test_payload.test_ping())

    def test_hardware_status(self):
        """Verify status command correctly reports rail and heater states."""
        self.assertTrue(test_payload.test_status())
        st = test_payload.payload.get_status()
        self.assertIn("v5_rail", st)
        self.assertIn("10v_rail", st)
        self.assertIn("in1", st)

    def test_photodiode_reading(self):
        """Verify photodiode reading parses valid float photocurrent."""
        self.assertTrue(test_payload.test_photodiode())
        self.assertIsNotNone(test_payload.payload.last_pd)
        self.assertAlmostEqual(test_payload.payload.last_pd, 1.42e-6, places=8)

    def test_rtd_readings(self):
        """Verify 7 RTD channels are parsed and within realistic ranges."""
        self.assertTrue(test_payload.test_rtds())
        rtds = test_payload.payload.last_rtds
        self.assertEqual(len(rtds), 7)
        for r in rtds:
            self.assertIn("temp", r)
            self.assertIn("res", r)
            self.assertGreater(r["res"], 50.0)

    def test_power_rail_switching(self):
        """Verify 5V and 10V rail control via mock input."""
        with patch("builtins.input", return_value="1"):
            self.assertTrue(test_payload.test_power_rail(5))
        st = test_payload.payload.get_status()
        self.assertTrue(st["v5_rail"])

        with patch("builtins.input", return_value="0"):
            self.assertTrue(test_payload.test_power_rail(5))
        st = test_payload.payload.get_status()
        self.assertFalse(st["v5_rail"])

    def test_heater_switching(self):
        """Verify heater control via mock input."""
        with patch("builtins.input", side_effect=["2", "1"]):
            self.assertTrue(test_payload.test_heaters())
        st = test_payload.payload.get_status()
        self.assertTrue(st["in2"])

    def test_single_contrast_measurement(self):
        """Verify Command '4' ODMR point measurement."""
        with patch("builtins.input", return_value="2870"):
            self.assertTrue(test_payload.test_single_contrast())
        c = test_payload.payload.last_contrast
        self.assertIsNotNone(c)
        # 2870 MHz should show resonance dip (around 0.85)
        self.assertLess(c, 0.90)

    def test_odmr_sweep(self):
        """Verify multi-point ODMR frequency sweep."""
        with patch("builtins.input", side_effect=["2860", "2880", "10"]):
            self.assertTrue(test_payload.test_odmr_sweep())

    def test_automated_selftest(self):
        """Verify 8-step regression self-test passes 100%."""
        all_passed = test_payload.run_automated_selftest()
        self.assertTrue(all_passed)

    def test_interactive_menu_loop(self):
        """Simulate user navigating menu and pressing 'Q' to quit."""
        simulated_inputs = ["1", "2", "3", "M", "Q"]
        with patch("builtins.input", side_effect=simulated_inputs):
            test_payload.run()


if __name__ == "__main__":
    unittest.main()
