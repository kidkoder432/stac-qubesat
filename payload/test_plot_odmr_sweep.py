"""Tests for plot_odmr_sweep.py. Run:  python3 test_plot_odmr_sweep.py
The plotting test needs matplotlib and is skipped without it; everything else is standard library."""

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest

import plot_odmr_sweep as P

# What the console really holds: monitor timestamps, the in-place progress line (\r), blank-padded
# clears, the estimate line, and one cancelled cycle.
LOG = (
    "12:00:00.100 SWEEP,cycles=2,samples=5,step=5,points=3\n"
    "12:00:00.101 DATA_COLUMNS,cycle,freq_mhz,contrast\n"
    "12:00:00.102 Send any key to cancel the sweep.\n"
    "\r1/2 2800MHz  10%  \r1/2 2800MHz  40%  \r                        \r"
    "12:00:01.000 DATA,1,2800,0.990000\n"
    "12:00:01.001 (first frequency took 0.7 s; estimated total about 4 s = 0.1 min)\n"
    "\r1/2 2805MHz  50%  \r                        \r12:00:01.700 DATA,1,2805,0.912345\n"
    "12:00:02.400 DATA,1,2810,0.995\n"
    "12:00:02.401 [cycle 1/2 done in 2.1 s]\n"
    "12:00:03.100 DATA,2,2800,0.980000\n"
    "12:00:03.800 DATA,2,2805,0.9e0\n"
    "\n^C Sweep CANCELLED by user; VCO set back to 1500 MHz\n"
)


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


class TestParse(unittest.TestCase):
    def test_data_lines_are_found_through_timestamps_and_progress_junk(self):
        rows = P.parse_console_log(LOG)
        self.assertEqual(rows, [(1, 2800, 0.99), (1, 2805, 0.912345), (1, 2810, 0.995),
                                (2, 2800, 0.98), (2, 2805, 0.9)])

    def test_nothing_else_is_mistaken_for_data(self):
        self.assertEqual(P.parse_console_log("SWEEP,cycles=2\nDATA_COLUMNS,cycle,freq_mhz,contrast\n"), [])
        self.assertEqual(P.parse_console_log("DATA,1,2800,\nDATA,x,2800,0.9\n"), [])

    def test_negative_and_exponent_values(self):
        self.assertEqual(P.parse_console_log("DATA,1,2800,-0.5\nDATA,1,2805,1.5e-2"),
                         [(1, 2800, -0.5), (1, 2805, 0.015)])

    def test_summary_mean_std_and_count_use_every_cycle_that_has_the_frequency(self):
        s = P.summarize(P.parse_console_log(LOG))
        self.assertEqual(list(s), [2800, 2805, 2810])
        self.assertAlmostEqual(s[2800][0], 0.985)
        self.assertAlmostEqual(s[2800][1], 0.005)
        self.assertEqual((s[2800][2], s[2805][2], s[2810][2]), (2, 2, 1))

    def test_dip_is_the_lowest_mean(self):
        self.assertEqual(P.dip(P.summarize(P.parse_console_log(LOG)))[0], 2805)
        self.assertIsNone(P.dip({}))


class TestLegacyFormats(unittest.TestCase):
    def test_two_column_csv_and_comments(self):
        x, y = P.parse_legacy("# c\n2800,0.9\n2850,0.8\n")
        self.assertEqual((x, y), ([2800.0, 2850.0], [0.9, 0.8]))

    def test_plain_values_are_spread_over_the_band(self):
        x, y = P.parse_legacy("1\n2\n3\n")
        self.assertEqual(x, [2800.0, 2875.0, 2950.0])

    def test_mission_log_lines(self):
        x, y = P.parse_legacy("12.4,FREQ=2870MHz,CONTRAST=0.8521,PD=1.2e-06A\n")
        self.assertEqual((x, y), ([2870.0], [0.8521]))


class TestMain(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def path(self, name):
        return os.path.join(self.dir, name)

    def test_writes_a_csv_next_to_the_log_and_never_overwrites_the_input(self):
        log = self.path("sweep_log.txt")
        open(log, "w").write(LOG)
        self.assertEqual(quiet(P.main, [log, "--no-plot"]), 0)
        lines = open(self.path("sweep_log.csv")).read().splitlines()
        self.assertEqual(lines[0], "cycle,freq_mhz,contrast")
        self.assertEqual(len(lines), 1 + 5)
        self.assertEqual(lines[1], "1,2800,0.99")
        # a log that is itself called .csv must not be clobbered
        csvlog = self.path("raw.csv")
        with open(csvlog, "w", newline="") as fh:
            fh.write(LOG)
        quiet(P.main, [csvlog, "--no-plot"])
        with open(csvlog, newline="") as fh:
            self.assertEqual(fh.read(), LOG)
        self.assertTrue(os.path.exists(self.path("raw_data.csv")))

    def test_explicit_csv_path(self):
        log = self.path("a.txt")
        open(log, "w").write(LOG)
        out = self.path("mine.csv")
        quiet(P.main, [log, "--csv", out, "--no-plot"])
        self.assertTrue(os.path.exists(out))

    def test_missing_file_and_empty_log_fail_cleanly(self):
        self.assertEqual(quiet(P.main, [self.path("nope.txt")]), 1)
        empty = self.path("empty.txt")
        open(empty, "w").write("boot messages only\n")
        self.assertEqual(quiet(P.main, [empty, "--no-plot"]), 1)

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"), "matplotlib not installed")
    def test_plot_is_written_for_cycles_and_for_a_single_cycle(self):
        log = self.path("s.txt")
        open(log, "w").write(LOG)
        png = self.path("p.png")
        self.assertEqual(quiet(P.main, [log, "--png", png]), 0)
        self.assertGreater(os.path.getsize(png), 5000)
        one = self.path("one.txt")
        open(one, "w").write("DATA,1,2800,0.99\nDATA,1,2805,0.9\nDATA,1,2810,0.99\n")
        png1 = self.path("p1.png")
        self.assertEqual(quiet(P.main, [one, "--png", png1]), 0)
        self.assertGreater(os.path.getsize(png1), 5000)
        legacy = self.path("legacy.csv")
        open(legacy, "w").write("2800,0.9\n2850,0.8\n")
        png2 = self.path("p2.png")
        self.assertEqual(quiet(P.main, [legacy, "--png", png2]), 0)
        self.assertGreater(os.path.getsize(png2), 5000)


if __name__ == "__main__":
    unittest.main()
