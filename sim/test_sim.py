"""
Scenario tests: the real FSM and Comms against the simulated world. Run:  python3 sim/test_sim.py

These pin down how the flight software behaves today (including the things that are awkward),
so a design change shows up here as a deliberate edit. Nothing here needs hardware.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world as W  # noqa: E402


def fresh(dt=1.0):
    return W.World(dt=dt)


def test_boot_idle_then_both_burns_then_science():
    w = fresh()
    w.advance(30 * 60)
    assert w.fsm.state == w.StateID.IDLE and not w.fsm.deployed
    w.advance(2 * 3600, stop=lambda: w.fsm.state == w.StateID.SCIENCE)
    assert w.fsm.state == w.StateID.SCIENCE and w.fsm.deployed
    assert [b[1] for b in W.burn_log] == ["1", "2"]


def test_the_real_burnwire_driver_fires_each_wire_for_the_duration_it_is_given():
    w = fresh()
    w.advance(2 * 3600, stop=lambda: w.fsm.deployed)
    assert [b[1] for b in W.burn_log] == ["1", "2"]
    for _t, _wire, duty, seconds in W.burn_log:
        assert abs(seconds - w.fsm.BURN_DURATION_S) < 1, "BurnWire holds for `duration`, no more"
        assert abs(duty - w.fsm.BURN_DUTY) < 0.01, "duty is a percent, 0 to 100"
    assert W.burn_log[1][0] - W.burn_log[0][0] >= w.fsm.BURN_DURATION_S, "wire 2 waits for wire 1"


def test_a_driver_fault_on_one_wire_is_retried_for_that_wire_only():
    w = fresh()
    W.S.burn_fail_wire = "2"
    w.advance(3 * 3600, stop=lambda: len(W.burn_log) >= 1)
    w.advance(10 * 60)
    assert [b[1] for b in W.burn_log] == ["1"] and not w.fsm.deployed
    W.S.burn_fail_wire = None
    # after 3 failed attempts the FSM gives up for now; the watchdog retries (only wire 2) each BURN_RETRY_BACKOFF_S
    w.advance(3 * 3600, stop=lambda: w.fsm.deployed)
    assert [b[1] for b in W.burn_log] == ["1", "2"] and w.fsm.deployed


def test_a_full_sweep_is_151_rows_and_shows_the_dip():
    w = fresh()
    w.advance(10 * 86400, stop=lambda: w.fsm.sweeps_completed >= 1)
    rows = [r for r in w.read_rows() if r[1] == "0"]
    assert [int(r[2]) for r in rows] == list(range(2800, 2951))
    freq, _ = min(((int(r[2]), float(r[3])) for r in rows), key=lambda p: p[1])
    assert abs(freq - 2863) <= 4 or abs(freq - 2877) <= 4


def test_ground_lock_holds_the_state():
    w = fresh()
    w.ground_send(w.StateID.SCIENCE, lock=True)
    w.advance(60)
    assert w.fsm.state == w.StateID.SCIENCE and w.fsm.locked
    w.advance(3 * 3600)
    assert w.fsm.state == w.StateID.SCIENCE, "autonomous transitions are off while locked"


def test_after_14_days_the_schedule_starts_giving_comms_slots():
    w = fresh(dt=10.0)
    w.advance(3 * 3600, stop=lambda: w.fsm.deployed)
    states = set()
    t_end = W.now() + 15 * 86400
    while W.now() < t_end:
        w.advance(600)
        states.add(w.fsm.state)
        if W.now() - 0 < w.fsm.SCIENCE_ONLY_S:
            assert w.fsm.state != w.StateID.COMMS, "no COMMS slots in the first 14 days"
    assert w.StateID.COMMS in states


def test_reboot_keeps_mission_time_and_deployed_but_restarts_the_sweep_in_a_new_file():
    """Documents current behaviour: a half sweep stays in the old file; the next starts at 2800."""
    w = fresh()
    w.advance(10 * 86400, stop=lambda: w.fsm.state == w.StateID.SCIENCE)
    w.advance(20 * 60)
    mt = w.fsm.mission_time
    files_before = len(w.science_files())
    assert 0 < w.fsm.current_sweep_freq - 2800 < 150, "stopped mid-sweep"
    w.reboot()
    assert w.fsm.deployed and w.fsm.mission_time > 0
    assert mt - w.fsm.mission_time <= w.fsm.MISSION_CLOCK_SAVE_S + 5
    assert w.fsm.current_sweep_freq == 2800
    w.advance(30 * 60)
    assert len(w.science_files()) >= files_before + 1, "a reboot starts a new file (and each new sweep another)"


def test_sd_card_pulled_fails_writes_and_only_a_reboot_brings_it_back():
    """lib/pycubed.py mounts the card once at boot; the FSM has no remount path."""
    w = fresh()
    w.advance(10 * 86400, stop=lambda: w.fsm.state == w.StateID.SCIENCE)
    w.advance(5 * 60)
    n = len(w.read_rows())
    assert n > 0
    w.set_sd(False)
    w.advance(5 * 60)
    assert len(w.read_rows()) == n, "nothing can be written with no card"
    assert any("[DATA] Record error" in text for _t, text in w.events)
    w.set_sd(True)
    w.advance(5 * 60)
    assert len(w.read_rows()) == n, "reinserting is not enough: the library never remounts"
    w.reboot()
    w.advance(5 * 60)
    assert len(w.read_rows()) > n, "after a reboot the card is mounted again and writing resumes"


def test_a_card_missing_at_boot_is_never_used_until_the_next_boot():
    w = fresh()
    W.S.sd_present = False
    w.reboot()
    w.advance(10 * 86400, stop=lambda: w.fsm.state == w.StateID.SCIENCE)
    w.advance(5 * 60)
    assert w.read_rows() == [] and not w.fsm.sd_card_initialized
    w.set_sd(True)
    w.advance(5 * 60)
    assert w.read_rows() == [], "inserting later does nothing"
    w.reboot()
    w.advance(5 * 60)
    assert w.read_rows(), "the card works after the next boot"


def test_dead_payload_is_recorded_as_ERR_counted_and_the_sweep_keeps_stepping():
    w = fresh()
    w.advance(10 * 86400, stop=lambda: w.fsm.state == w.StateID.SCIENCE)
    W.S.payload_online = False
    f0 = w.fsm.current_sweep_freq
    w.advance(10 * 60)
    assert w.fsm.payload_errors >= 2
    assert any(r[3] == "ERR" for r in w.read_rows())
    assert w.fsm.current_sweep_freq != f0


def test_small_sd_card_deletes_the_oldest_file_only():
    w = fresh()
    w.advance(10 * 86400, stop=lambda: w.fsm.state == w.StateID.SCIENCE)
    for _ in range(3):
        w.reboot()
        w.advance(2 * 60)
    names = w.science_files()
    assert len(names) >= 3
    used = sum(os.path.getsize(os.path.join(w.sd_dir, n)) for n in names)
    W.S.sd_capacity = used + w.fsm.SD_MIN_FREE_BYTES - 1  # just under the free-space limit
    w.advance(3 * 60)
    left = w.science_files()
    assert names[0] not in left, "oldest deleted"
    assert names[-1] in left, "the file being written is never deleted"
    assert len(left) < len(names) + 1


def test_a_radio_that_never_recovers_ends_in_a_reset_and_the_FSM_comes_back():
    """FatalFault('radio is not recovering') -> run() sleeps 10 s and hard resets (TODO A11)."""
    w = fresh()
    w.advance(10 * 86400, stop=lambda: w.fsm.state == w.StateID.SCIENCE)
    W.S.radio_hung = True
    w.advance(15 * 60)
    assert w.resets >= 1, "an unrecovering radio is a fault that resets the board"
    W.S.radio_hung = False
    w.advance(30 * 60)
    assert w.fsm.state == w.StateID.SCIENCE and w.fsm.deployed


def test_low_battery_forces_idle():
    w = fresh()
    w.advance(10 * 86400, stop=lambda: w.fsm.state == w.StateID.SCIENCE)
    W.S.battery_v = 5.9
    w.advance(5 * 60)
    assert w.fsm.state == w.StateID.IDLE


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name, file=W.console.real)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL", name, "->", repr(e), file=W.console.real)
    print(f"{len(tests) - failed}/{len(tests)} passed", file=W.console.real)
    sys.exit(1 if failed else 0)
