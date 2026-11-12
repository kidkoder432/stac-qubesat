"""
Desktop tests for the FSM, Task scheduler and Comms command path.

Run from this directory:   python3 test_fsm.py
No hardware needed. `pycubed`, `BurnWire` and `PayloadUART` are stubbed, and the clock is
faked. The stub `cubesat` only has attributes that exist in the board's pycubed.py
(checked against pc-backup/lib/pycubed.py), so if the FSM touches one that doesn't exist
it fails here instead of being silently swallowed by a try/except on the board.
"""

import contextlib
import io
import os
import sys
import tempfile
import time
import types

sys.path.insert(0, ".")

# ---- fake clock (Task, Comms and the FSM all call time.monotonic / time.sleep) ----
clock = [0.0]
time.monotonic = lambda: clock[0]


class StopRun(BaseException):  # BaseException so run()'s `except Exception` doesn't eat it
    pass


# ---- stubs ----
class CubeSat:
    """Only what the real board library provides."""

    battery_voltage = 8.2  # V
    temperature = 25.0  # degC (IMU)
    solar_charging = True
    charge_current = 120.0  # mA
    c_state_err = 0
    hardware = {"Radio1": True}
    sd_ok = True

    sd_dir = tempfile.mkdtemp()
    n_files = 0

    def new_file(self, substring, binary=False):
        if not self.sd_ok:
            return None
        CubeSat.n_files += 1
        return os.path.join(CubeSat.sd_dir, "mission%05d.txt" % CubeSat.n_files)

    def log(self, msg):
        pass

    class micro:
        pass


cubesat = CubeSat()
pycubed = types.ModuleType("pycubed")
pycubed.cubesat = cubesat
sys.modules["pycubed"] = pycubed
# The FSM and BurnWire import `lib.pycubed`, Comms and PayloadUART import `pycubed`. Stub both
# names to the same object here. (On the board that mix could load the library twice: Q-X5.)
_lib = types.ModuleType("lib")
_lib.__path__ = []
_lib.pycubed = pycubed
sys.modules["lib"] = _lib
sys.modules["lib.pycubed"] = pycubed

burns = []  # time of every wire burn
burn_wires = []  # which wire each burn used
burn_mode = {"fail": False, "fail_wire": None}


class FakeBurnWire:
    def __init__(self, *a):
        pass

    def cubesatBurn(self, num, duty, dur):
        if burn_mode["fail"] or burn_mode["fail_wire"] == num:
            raise RuntimeError("relay fail")
        burns.append(clock[0])
        burn_wires.append(num)

    def burningCheck(self):
        return "not burning"


m = types.ModuleType("BurnWire")
m.BurnWire = FakeBurnWire
sys.modules["BurnWire"] = m
payload_mode = {"fail": False}


class FakePayload:
    def ping(self):
        return not payload_mode["fail"]

    def read_photodiode(self):
        return None if payload_mode["fail"] else 1.5e-6

    def measure_contrast(self, freq, timeout=30.0):
        return None if payload_mode["fail"] else 0.01 * (freq - 2790)


m = types.ModuleType("PayloadUART")
m.PayloadUART = lambda *a: FakePayload()
sys.modules["PayloadUART"] = m

import Comms as C  # noqa: E402
import QubeSatFSM as Q  # noqa: E402
from StateCodeGenerator import StateID  # noqa: E402
from Task import Task  # noqa: E402


class Radio:
    def __init__(self):
        self.rx, self.tx = [], []

    def receive(self, timeout=0):
        return self.rx.pop(0) if self.rx else None

    def send(self, b):
        self.tx.append(bytes(b))


def reset_world():
    clock[0] = 0.0
    cubesat.battery_voltage = 8.2
    cubesat.temperature = 25.0
    cubesat.sd_ok = True
    for name in os.listdir(CubeSat.sd_dir):
        os.remove(os.path.join(CubeSat.sd_dir, name))
    CubeSat.n_files = 0
    burns.clear()
    burn_wires.clear()
    burn_mode["fail"] = False
    burn_mode["fail_wire"] = None
    payload_mode["fail"] = False
    for i in range(len(Q._nvm)):
        Q._nvm[i] = 0
    for i in range(len(C._nvm)):
        C._nvm[i] = 0


def make(comms=True):
    reset_world()
    with contextlib.redirect_stdout(io.StringIO()):
        f = Q.QubeSatFSM()
        radio = Radio()
        if comms:
            cm = C.CommsManager(radio)
            cm.state_code = StateID.IDLE
            f.attach_comms(cm)
        else:
            cm = None
    return f, cm, radio


def step(f, cm, dt, n=1):
    """One FSM loop iteration per step (same logic as run(), minus the sleep)."""
    with contextlib.redirect_stdout(io.StringIO()):
        for _ in range(n):
            clock[0] += dt
            f.tick(clock[0])  # the same loop body run() uses


def cmd(radio, code, lock=False):
    radio.rx.append(C.build_state_command(code, lock=lock))


# ---------------------------------------------------------------- tests
def test_state_codes_match_comms():
    assert StateID.STOP == C.STATE_STOP
    assert StateID.IDLE == C.STATE_IDLE
    assert StateID.DEPLOY == C.STATE_DEPLOY
    assert StateID.SCIENCE == C.STATE_SCIENCE
    assert StateID.COMMS == C.STATE_COMMS


def test_radio_frequency_is_the_team_answer():
    assert abs(C.FREQ_MHZ - 433.72) < 1e-9


def test_task_scheduling():
    ran = []
    now_task = Task("now", 1, 10, False, lambda: ran.append("now"))
    later = Task("later", 2, 10, True, lambda: ran.append("later"))
    once = Task("once", 3, None, False, lambda: ran.append("once"))
    delayed = Task("delayed", 4, None, False, lambda: ran.append("delayed"), delay=100)
    assert now_task.is_due(0) and not later.is_due(0) and once.is_due(0)
    assert not delayed.is_due(0) and not delayed.is_due(99) and delayed.is_due(100)
    assert later.is_due(10)
    once.run()
    assert once.done and not once.is_due(1e9)  # one-shot never reruns


def test_boot_idle_then_deploy_then_science():
    f, cm, radio = make()
    assert f.state == StateID.IDLE
    step(f, cm, 10, 300)  # 3000 s: still idle
    assert f.state == StateID.IDLE and not burns
    step(f, cm, 10, 70)  # past 3600 s
    assert burns, "burn wire should fire after DEPLOY_AFTER_IDLE_S"
    assert f.deployed and Q._nvm[Q._NVM_DEPLOYED] == Q._DEPLOYED_MAGIC
    step(f, cm, 10, 5)
    assert f.state == StateID.SCIENCE, "first 14 days after the burn are all science"


def test_reboot_does_not_reburn():
    f, cm, radio = make()
    step(f, cm, 10, 380)
    n = len(burns)
    assert n >= 1
    clock[0] = 0.0
    with contextlib.redirect_stdout(io.StringIO()):
        f2 = Q.QubeSatFSM()  # fresh object, same NVM
    assert f2.deployed
    f2.state = StateID.IDLE
    step(f2, None, 10, 500)
    assert len(burns) == n  # deployed flag survived; no deploy path


def test_low_battery_forces_idle_from_science():
    f, cm, radio = make()
    step(f, cm, 10, 380)
    assert f.state != StateID.IDLE
    cubesat.battery_voltage = 5.9
    step(f, cm, 30, 3)
    assert f.state == StateID.IDLE


def test_ground_lock_unlock():
    f, cm, radio = make()
    cmd(radio, StateID.SCIENCE, lock=True)
    step(f, cm, 1, 2)
    assert f.state == StateID.SCIENCE and f.locked
    step(f, cm, 10, 400)  # transition check would have moved us; lock holds
    assert f.state == StateID.SCIENCE
    cmd(radio, StateID.IDLE, lock=True)
    step(f, cm, 1, 2)
    step(f, cm, 10, 400)
    assert f.state == StateID.IDLE and f.locked
    cmd(radio, StateID.IDLE, lock=False)
    step(f, cm, 1, 2)
    assert not f.locked


def test_transition_itself_respects_lock():
    """Defense in depth: even a direct autonomous transition() call is blocked while locked."""
    f, cm, radio = make()
    f.locked = True
    with contextlib.redirect_stdout(io.StringIO()):
        f.transition(StateID.SCIENCE)
    assert f.state == StateID.IDLE
    with contextlib.redirect_stdout(io.StringIO()):
        f.transition(StateID.SCIENCE, force=True)
    assert f.state == StateID.SCIENCE


def test_comms_state_confirms_solar_and_flags_no_charge():
    """The FSM swallows hardware errors in try/except, so assert the *outcome*."""
    f, cm, radio = make()
    cmd(radio, StateID.COMMS, lock=True)
    step(f, cm, 1, 3)
    assert f.state == StateID.COMMS
    step(f, cm, 1, 5)  # solar task is immediate in COMMS
    assert f.equipment_check["solar_panel"] is True
    f.equipment_check["solar_panel"] = False
    cubesat.solar_charging = False
    with contextlib.redirect_stdout(io.StringIO()):
        f._task_enable_solar_panels()
    cubesat.solar_charging = True
    assert f.equipment_check["solar_panel"] is False


def test_locked_deploy_sends_no_handshake():
    """While locked the transition task must have no side effects (e.g. a false handshake)."""
    f, cm, radio = make()
    calls = []
    f._send_handshake = lambda: calls.append(1)
    cmd(radio, StateID.DEPLOY, lock=True)
    step(f, cm, 1, 3)  # burn + SD init happen; deploy is now complete
    assert f.deployed and f.equipment_check["sd_card"]
    step(f, cm, 10, 50)
    assert f.state == StateID.DEPLOY and not calls
    cmd(radio, StateID.DEPLOY, lock=False)
    step(f, cm, 61, 2)  # dedup window passes; now unlocked
    step(f, cm, 10, 5)
    assert calls, "handshake is sent once the lock is released and deploy is complete"


def test_overheat_forces_idle():
    f, cm, radio = make()
    cmd(radio, StateID.SCIENCE, lock=True)
    step(f, cm, 1, 2)
    cubesat.temperature = 75.0
    step(f, cm, 30, 3)
    assert f.state == StateID.IDLE


def test_command_spam_is_harmless():
    """Ground repeats a code; every copy reaches the FSM but nothing changes after the first."""
    f, cm, radio = make()
    writes = []
    real = C._nvm_write_state
    C._nvm_write_state = lambda c: (writes.append(c), real(c))
    try:
        for _ in range(5):
            cmd(radio, StateID.SCIENCE, lock=True)
        seen = []
        orig = f.command_state
        cm.on_state_command = lambda c, l: (seen.append((c, l)), orig(c, l))
        step(f, cm, 1, 10)
    finally:
        C._nvm_write_state = real
    assert len(seen) == 5, "no dedup window any more: every copy is delivered"
    assert f.state == StateID.SCIENCE and f.locked
    assert writes == [StateID.SCIENCE], "NVM written once, not once per repeat"


def test_deploy_command_spam_burns_once():
    f, cm, radio = make()
    for _ in range(4):
        cmd(radio, StateID.DEPLOY, lock=True)
    step(f, cm, 1, 10)
    assert len(burns) == 2, "one cycle (both wires); repeats of DEPLOY must not re-arm the burn"


def test_safety_overrides_lock_and_clears_it():
    f, cm, radio = make()
    cmd(radio, StateID.SCIENCE, lock=True)
    step(f, cm, 1, 2)
    cubesat.battery_voltage = 5.9
    step(f, cm, 30, 3)
    assert f.state == StateID.IDLE and not f.locked


def test_stop_command_halts_tx_but_not_fsm():
    f, cm, radio = make()
    cm.push_telemetry(b"x")
    cmd(radio, StateID.STOP)
    step(f, cm, 1, 2)
    assert cm.state_code == C.STATE_STOP
    sent_before = len(radio.tx)
    step(f, cm, 1, 300)  # long enough for several TX windows
    assert len(radio.tx) == sent_before, "no transmissions while STOPped"
    assert f.state == StateID.IDLE  # FSM unaffected


def test_unknown_state_code_rejected():
    f, cm, radio = make()
    with contextlib.redirect_stdout(io.StringIO()):
        f.command_state(99, False)
    assert f.state == StateID.IDLE


def test_burn_error_retries_forever_then_recovers():
    f, cm, radio = make()
    burn_mode["fail"] = True
    step(f, cm, 30, int(24 * 3600 / 30))
    assert not burns and f.state == StateID.IDLE and not f.deployed
    assert f.burn_attempts >= 3, "kept retrying"
    burn_mode["fail"] = False
    step(f, cm, 30, int(3 * 3600 / 30))
    assert f.deployed


def test_burn_ok_but_silent_reburns_until_ground_heard():
    f, cm, radio = make()
    step(f, cm, 30, int(40 * 3600 / 30))
    assert len(burns) >= 6  # first burn + 12 h re-burns, two wires each
    n = len(burns)
    cmd(radio, StateID.IDLE)
    step(f, cm, 1, 2)
    assert f.last_ground_contact is not None
    step(f, cm, 30, int(48 * 3600 / 30))
    assert len(burns) == n  # contact stops the watchdog


def test_ground_deploy_command_rearms_burn():
    f, cm, radio = make()
    f.burn_attempts = 3
    n = len(burns)
    cmd(radio, StateID.DEPLOY, lock=True)
    step(f, cm, 1, 3)
    assert f.state == StateID.DEPLOY and len(burns) == n + 2  # both wires


def test_sd_failure_is_detected():
    f, cm, radio = make()
    cubesat.sd_ok = False
    step(f, cm, 10, 380)
    assert not f.sd_card_initialized
    assert f.state == StateID.DEPLOY  # waits in DEPLOY, doesn't proceed without SD


def test_beacon_is_tinygs_packet_and_goes_out():
    f, cm, radio = make()
    f._task_beacon()
    step(f, cm, 1, C.CommsConfig.DEFAULT_RX_TICKS + 5)  # reach a TX window
    beacons = [p for p in radio.tx if p[0] == C.HDR_TELEMETRY]
    assert beacons, "beacon should be transmitted"
    body = beacons[0][1:]
    assert len(body) == 15 and body[:6] == b"STAC  "
    assert C._crc8(body[:-1]) == body[-1]


def test_snapshot_packet_layout():
    f, cm, radio = make()
    pkt = f.telemetry_packet()
    assert len(pkt) == 17 and pkt[0] == 2 and pkt[1] == StateID.IDLE


def test_both_wires_fire_and_deploy_needs_both():
    f, cm, radio = make()
    step(f, cm, 10, 380)
    assert burn_wires[:2] == ["1", "2"] and f.deployed


def test_wire2_failure_retries_only_wire2():
    f, cm, radio = make()
    burn_mode["fail_wire"] = "2"
    step(f, cm, 10, 380)
    assert burn_wires == ["1"] and not f.deployed
    assert Q._nvm[Q._NVM_DEPLOYED] != Q._DEPLOYED_MAGIC
    burn_mode["fail_wire"] = None
    step(f, cm, 30, int(3 * 3600 / 30))
    assert burn_wires == ["1", "2"], "wire 1 must not be fired again"
    assert f.deployed


def test_watchdog_reburns_both_wires():
    f, cm, radio = make()
    step(f, cm, 30, int(14 * 3600 / 30))  # one cycle, then 12 h of silence
    assert burn_wires[:4] == ["1", "2", "1", "2"]


def test_mission_time_starts_at_burn():
    f, cm, radio = make()
    step(f, cm, 10, 300)  # 3000 s of uptime, no burn yet
    assert f.mission_time == 0 and not f.deployed
    step(f, cm, 10, 80)
    assert f.deployed
    t0 = f.mission_time
    step(f, cm, 10, 10)
    assert abs((f.mission_time - t0) - 100) < 1e-6


def _reboot():
    with contextlib.redirect_stdout(io.StringIO()):
        return Q.QubeSatFSM()


def test_mission_time_survives_reboot():
    f, cm, radio = make()
    step(f, cm, 30, int(3 * 3600 / 30))
    elapsed = f.mission_time
    assert elapsed > 3600
    clock[0] = 0.0
    f2 = _reboot()
    assert 0 < f2.mission_time <= elapsed
    assert elapsed - f2.mission_time <= Q.QubeSatFSM.MISSION_CLOCK_SAVE_S + 30, "lose at most one save period"


def test_mission_time_ring_wraps_and_skips_a_torn_write():
    f, cm, radio = make()
    step(f, cm, 30, int(5 * 3600 / 30))  # ~20 saves: the 8-slot ring has wrapped
    saves_ok = f.mission_time
    # tear the newest record (power cut mid-write): the previous one must still load
    newest = Q._load_clock()[1]
    base = Q._NVM_CLOCK + newest * Q._CLOCK_SLOT_SIZE
    Q._nvm[base + 4] ^= 0xFF
    clock[0] = 0.0
    f2 = _reboot()
    assert 0 < f2.mission_time < saves_ok
    assert saves_ok - f2.mission_time <= 2 * Q.QubeSatFSM.MISSION_CLOCK_SAVE_S + 30


def test_fresh_nvm_ff_reads_as_nothing_saved():
    reset_world()
    for i in range(len(Q._nvm)):
        Q._nvm[i] = 0xFF
    f = _reboot()
    assert not f.deployed and f.mission_time == 0 and f.last_ground_contact is None


def test_ground_contact_survives_reboot_so_antenna_is_not_reburned():
    f, cm, radio = make()
    step(f, cm, 10, 380)
    cmd(radio, StateID.IDLE)
    step(f, cm, 1, 2)
    assert f.last_ground_contact is not None
    n = len(burns)
    clock[0] = 0.0
    f2 = _reboot()
    assert f2.last_ground_contact is not None
    step(f2, None, 30, int(36 * 3600 / 30))
    assert len(burns) == n, "ground was heard before the reboot; no re-burn"


def _set_mission_time(f, seconds):
    f._clock_base = seconds
    f._clock_started_at = f.uptime


def test_schedule_14_days_science_then_7_comms_3_science():
    f, cm, radio = make()
    S = Q.QubeSatFSM
    for t in (0, 100, S.SCIENCE_ONLY_S - 1):
        _set_mission_time(f, t)
        assert f._scheduled_state() == StateID.SCIENCE
    for k in range(25):  # 2.5 cycles
        _set_mission_time(f, S.SCIENCE_ONLY_S + k * S.SLOT_S)
        expected = StateID.COMMS if (k % 10) < 7 else StateID.SCIENCE
        assert f._scheduled_state() == expected, k
    _set_mission_time(f, S.SCIENCE_ONLY_S + 7 * S.SLOT_S - 1)
    assert f._scheduled_state() == StateID.COMMS
    _set_mission_time(f, S.SCIENCE_ONLY_S + 7 * S.SLOT_S)
    assert f._scheduled_state() == StateID.SCIENCE


def test_split_is_70_30_after_two_weeks():
    f, cm, radio = make()
    step(f, cm, 10, 380)  # deploy
    assert f.deployed
    S = Q.QubeSatFSM
    _set_mission_time(f, S.SCIENCE_ONLY_S)
    comms = science = 0
    for _ in range(6000):  # 10 full cycles of 100 min, 10 s per step
        step(f, cm, 10, 1)
        if f.state == StateID.COMMS:
            comms += 1
        elif f.state == StateID.SCIENCE:
            science += 1
    frac = comms / float(comms + science)
    assert 0.69 <= frac <= 0.71, frac


def test_after_low_battery_returns_to_the_scheduled_state():
    f, cm, radio = make()
    step(f, cm, 10, 380)
    S = Q.QubeSatFSM
    _set_mission_time(f, S.SCIENCE_ONLY_S + 2 * S.SLOT_S)  # a COMMS slot
    cubesat.battery_voltage = 5.9
    step(f, cm, 30, 3)
    assert f.state == StateID.IDLE
    cubesat.battery_voltage = 8.4
    step(f, cm, 10, 3)
    assert f.state == StateID.COMMS


def _science_files():
    return sorted(
        os.path.join(CubeSat.sd_dir, n) for n in os.listdir(CubeSat.sd_dir) if n.startswith("mission")
    )


def _read_rows():
    rows = []
    for path in _science_files():
        with open(path) as fh:
            rows += [ln.strip().split(",") for ln in fh if ln.strip()]
    return [r for r in rows if r[0] != "mission_s"]


def test_science_sweeps_all_points_and_counts_completed_sweeps():
    f, cm, radio = make()
    cmd(radio, StateID.SCIENCE, lock=True)
    step(f, cm, 1, 2)
    n_points = (f.SWEEP_END_MHZ - f.SWEEP_START_MHZ) // f.SWEEP_STEP_MHZ + 1
    step(f, cm, 10, n_points * 2 + 5)  # a bit over two full sweeps at 10 s per point
    assert f.sweeps_completed == 2
    rows = _read_rows()
    first = [r for r in rows if r[1] == "0"]
    assert [int(r[2]) for r in first] == list(range(2800, 2951)), "every frequency once, in order"
    assert all(r[3] != "ERR" and r[4] != "ERR" for r in first)


def test_science_file_has_header_and_mission_time_column():
    f, cm, radio = make()
    cmd(radio, StateID.SCIENCE, lock=True)
    step(f, cm, 1, 2)
    step(f, cm, 10, 5)
    with open(_science_files()[-1]) as fh:
        assert fh.readline().strip() == Q.QubeSatFSM.SCIENCE_FILE_HEADER


def test_science_records_after_a_reboot_without_passing_through_deploy():
    """After a reboot the FSM goes IDLE -> SCIENCE; the SD card must still get initialized."""
    f, cm, radio = make()
    step(f, cm, 10, 380)
    assert f.deployed
    clock[0] = 0.0
    f2 = _reboot()
    assert not f2.sd_card_initialized
    before = len(_read_rows())
    step(f2, None, 10, 30)
    assert f2.state == StateID.SCIENCE and f2.sd_card_initialized
    assert len(_read_rows()) > before


def test_payload_failure_is_recorded_counted_and_does_not_stop_the_sweep():
    f, cm, radio = make()
    cmd(radio, StateID.SCIENCE, lock=True)
    step(f, cm, 1, 2)
    payload_mode["fail"] = True
    step(f, cm, 10, 6)
    assert f.payload_errors >= 5
    assert any(r[3] == "ERR" for r in _read_rows())
    assert f.current_sweep_freq > 2800, "the sweep keeps stepping"
    payload_mode["fail"] = False
    step(f, cm, 10, 2)
    assert f.payload_errors == 0
    pkt = f.telemetry_packet()
    assert pkt[-1] == 0


def test_telemetry_reports_sweep_progress_and_ground_contact():
    f, cm, radio = make()
    cmd(radio, StateID.SCIENCE, lock=True)
    step(f, cm, 1, 2)
    step(f, cm, 10, 12)
    pkt = f.telemetry_packet()
    sweeps, point = pkt[13] << 8 | pkt[14], pkt[15]
    assert sweeps == 0 and point == f.current_sweep_freq - 2800 and point >= 10


def test_real_run_loop():
    """Drives QubeSatFSM.run() itself (not a copy of its loop) for ~70 min of fake time."""
    f, cm, radio = make()
    f.comms = cm
    ticks = [0]

    def fake_sleep(dt):
        clock[0] += 10.0  # each loop iteration = 10 s of fake time
        ticks[0] += 1
        if ticks[0] >= 440:
            raise StopRun()

    real_sleep = time.sleep
    time.sleep = fake_sleep
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                f.run()
            except StopRun:
                pass
    finally:
        time.sleep = real_sleep
    assert f.deployed, "run() should have reached DEPLOY and burned"
    assert f.uptime > 3600
    assert 0 < f.mission_time < f.uptime, "mission time counts from the burn, not from boot"
    assert f.state in (StateID.SCIENCE, StateID.COMMS)


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
