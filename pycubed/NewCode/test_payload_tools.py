"""
Desktop tests for the interactive payload tools in test_payload.py (sweep, heaters, photodiode,
RTDs, cancelling). They use the mock payload that test_payload.py falls back to when there is
no board. Run from this directory:   python3 test_payload_tools.py
"""

import builtins
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, ".")

import test_payload as t  # noqa: E402

assert t.is_mock, "these tests need the mock payload (run them on a desktop)"
bridge = t.payload.uart  # the MockUARTBridge behind the driver


def run(fn, *inputs):
    """Call fn() with scripted input() answers; return (result, printed text)."""
    answers = iter(inputs)
    real_input = builtins.input
    builtins.input = lambda prompt="": next(answers)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            result = fn()
    finally:
        builtins.input = real_input
    return result, out.getvalue()


class Patch:
    """Temporarily replace attributes: with Patch((obj, "name", value), ...):"""

    def __init__(self, *items):
        self.items = items

    def __enter__(self):
        self.saved = [(o, n, getattr(o, n)) for o, n, _ in self.items]
        for o, n, v in self.items:
            setattr(o, n, v)

    def __exit__(self, *exc):
        for o, n, v in self.saved:
            setattr(o, n, v)


def fresh():
    bridge.heaters[:] = [False] * 4
    bridge._heat = 0.0
    t.last_sweep = {}


def counter_after(n):
    """A callable that returns False n times, then True forever (a user pressing Enter)."""
    state = {"calls": 0}

    def f(*a):
        state["calls"] += 1
        return state["calls"] > n

    return f


# ---------------------------------------------------------------- sweep
def test_full_sweep_captures_all_151_points_in_order_and_finds_the_dip():
    fresh()
    log = os.path.join(tempfile.mkdtemp(), "sweep.csv")
    with Patch((t, "LOG_PATH", log), (t, "_cancel_requested", lambda: False)):
        ok, text = run(t.test_full_sweep)
    assert ok
    rows = t.last_sweep["rows"]
    assert [r[0] for r in rows] == list(range(2800, 2951))
    assert all(r[2] is not None for r in rows), "photodiode read at every point"
    assert not t.last_sweep["cancelled"] and t.last_sweep["failed"] == 0
    assert "Sweep complete: 151/151" in text and "Minimum contrast" in text and "2870 MHz" in text
    lines = open(log).read().splitlines()
    assert lines[1] == "freq_mhz,contrast,photodiode_a" and len(lines) == 2 + 151


def test_full_sweep_can_be_cancelled_with_a_keypress():
    fresh()
    with Patch((t, "LOG_PATH", "/nonexistent/x.csv"), (t, "_cancel_requested", counter_after(10))):
        ok, text = run(t.test_full_sweep)
    assert ok, "the points captured before the cancel still count"
    assert len(t.last_sweep["rows"]) == 10 and t.last_sweep["cancelled"]
    assert "CANCELLED" in text and "10/151" in text
    assert [r[0] for r in t.last_sweep["rows"]] == list(range(2800, 2810))


def test_ctrl_c_in_the_middle_of_a_point_ends_the_sweep_cleanly():
    fresh()
    calls = {"n": 0}
    real = t.payload.measure_contrast

    def boom(freq, timeout=30.0):
        calls["n"] += 1
        if calls["n"] == 6:
            raise KeyboardInterrupt
        return real(freq, timeout=timeout)

    with Patch((t, "LOG_PATH", "/nonexistent/x.csv"), (t, "_cancel_requested", lambda: False), (t.payload, "measure_contrast", boom)):
        ok, text = run(t.test_full_sweep)
    assert ok and t.last_sweep["cancelled"] and len(t.last_sweep["rows"]) == 5
    assert "Interrupted" in text


def test_failed_points_are_reported_and_the_sweep_continues():
    fresh()
    real = t.payload.measure_contrast
    with Patch(
        (t, "LOG_PATH", "/nonexistent/x.csv"),
        (t, "_cancel_requested", lambda: False),
        (t.payload, "measure_contrast", lambda f, timeout=30.0: None if f == 2850 else real(f, timeout=timeout)),
    ):
        ok, text = run(t.test_full_sweep)
    assert t.last_sweep["failed"] == 1 and len(t.last_sweep["rows"]) == 150
    assert "FAILED" in text and "150/151" in text


def test_custom_sweep_range_and_step():
    fresh()
    with Patch((t, "LOG_PATH", "/nonexistent/x.csv"), (t, "_cancel_requested", lambda: False)):
        ok, text = run(t.test_odmr_sweep, "2860", "2880", "5")
    assert [r[0] for r in t.last_sweep["rows"]] == [2860, 2865, 2870, 2875, 2880]
    assert all(r[2] is None for r in t.last_sweep["rows"]), "custom sweep is contrast only, as before"


def test_custom_sweep_rejects_bad_input():
    fresh()
    ok, text = run(t.test_odmr_sweep, "2900", "2800", "1")
    assert not ok and not t.last_sweep
    ok, text = run(t.test_odmr_sweep, "abc", "2950", "1")
    assert not ok


# ---------------------------------------------------------------- cancel key detection
def test_cancel_key_is_read_from_stdin_without_blocking():
    r, w = os.pipe()
    real_stdin = sys.stdin
    sys.stdin = os.fdopen(r)
    try:
        assert t._cancel_requested() is False, "nothing typed: must not block or cancel"
        os.write(w, b"\n")
        assert t._cancel_requested() is True
        assert t._cancel_requested() is False, "the keypress is consumed"
        os.close(w)
        assert t._cancel_requested() is False, "end of input is not a keypress"
    finally:
        sys.stdin = real_stdin


# ---------------------------------------------------------------- heaters
def test_heater_set_is_confirmed_by_readback():
    fresh()
    _, text = run(t.test_heaters, "2", "1", "b")
    assert bridge.heaters == [False, True, False, False]
    assert "IN2 is ON (confirmed by status readback)" in text
    _, text = run(t.test_heaters, "2", "", "b")  # Enter toggles
    assert bridge.heaters[1] is False


def test_heater_show_state_and_all_off():
    fresh()
    bridge.heaters[:] = [True, True, False, True]
    _, text = run(t.test_heaters, "s", "a", "s", "b")
    assert "IN1 ON | IN2 ON | IN3 OFF | IN4 ON" in text
    assert bridge.heaters == [False] * 4 and "All heaters OFF (confirmed)" in text


def test_heater_run_shows_the_rtd_rise_and_ends_off():
    fresh()
    with Patch((t, "_wait_or_cancel", counter_after(4))):
        _, text = run(t.test_heaters, "r", "2", "1", "5", "b")
    assert bridge.heaters == [False] * 4, "heater must be OFF when the run ends"
    assert "Cancelled by user" in text and "RTD1" in text
    assert "+" in text and "(RTD1)" in text, "the RTD that warms up is reported"
    assert "Heater IN2 is ON" in text and "Heater IN2 is OFF" in text


def test_heater_run_ctrl_c_still_switches_the_heater_off():
    fresh()
    calls = {"n": 0}
    real = t.payload.read_rtds

    def boom():
        calls["n"] += 1
        if calls["n"] == 3:
            raise KeyboardInterrupt
        return real()

    with Patch((t, "_wait_or_cancel", lambda s: False), (t.payload, "read_rtds", boom)):
        _, text = run(t.test_heaters, "r", "3", "1", "5", "b")
    assert bridge.heaters == [False] * 4
    assert "Interrupted" in text


def test_heater_run_bad_input_never_turns_a_heater_on():
    fresh()
    _, text = run(t.test_heaters, "r", "1", "abc", "5", "b")
    assert bridge.heaters == [False] * 4
    _, text = run(t.test_heaters, "r", "9", "b")  # heater 9 does not exist: back to the menu
    assert bridge.heaters == [False] * 4 and "Must be between" in text


def test_heater_run_off_even_if_the_on_command_is_not_confirmed():
    fresh()
    real = t.payload.get_status
    with Patch((t.payload, "get_status", lambda: None)):  # readback fails
        _, text = run(t.test_heaters, "r", "1", "1", "5", "b")
    assert "not confirmed" in text
    assert bridge.heaters == [False] * 4, "an unconfirmed heater is sent OFF again"


# ---------------------------------------------------------------- photodiode and RTD
def test_photodiode_stream_prints_statistics():
    fresh()
    ok, text = run(t.test_photodiode_stream, "5", "0")
    assert ok and "5 readings (0 failed)" in text and "mean 1.4200e-06" in text


def test_photodiode_stream_until_cancelled():
    fresh()
    with Patch((t, "_wait_or_cancel", counter_after(3))):
        ok, text = run(t.test_photodiode_stream, "0", "0")
    assert ok and "Cancelled by user" in text and "4 readings" in text


def test_rtd_monitor_reports_min_and_max_per_channel():
    fresh()
    ok, text = run(t.test_rtd_monitor, "4", "0")
    assert ok and "4 readings (0 failed)" in text
    for ch in range(1, 8):
        assert f"RTD{ch}:" in text


def test_rtd_monitor_counts_failed_reads():
    fresh()
    with Patch((t.payload, "read_rtds", lambda: None)):
        ok, text = run(t.test_rtd_monitor, "3", "0")
    assert not ok and "No successful readings" in text


def test_sparkline_shows_a_dip():
    line = t._sparkline([1.0] * 10 + [0.2] * 5 + [1.0] * 10, width=25)
    assert len(line) == 25 and line[12] == " " and line[0] == "@"
    assert t._sparkline([1.0], 10) == "" and t._sparkline([2.0, 2.0], 10) == "--"


# ---------------------------------------------------------------- menu
def test_menu_runs_the_new_options():
    fresh()
    with Patch((t, "_cancel_requested", lambda: False), (t, "LOG_PATH", "/nonexistent/x.csv")):
        _, text = run(t.run, "F", "P", "5", "0", "T", "2", "0", "Q")
    assert "Sweep complete: 151/151" in text
    assert "5 readings" in text and "2 readings" in text
    assert "Unknown option" not in text


if __name__ == "__main__":
    tests = [(n, fn) for n, fn in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:
            failed += 1
            import traceback

            print("FAIL", name, "->", repr(e))
            traceback.print_exc()
    print("\n%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
