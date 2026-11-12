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
import sys
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

    def new_file(self, substring, binary=False):
        return "/sd/data/mission00000.txt" if self.sd_ok else None

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

burns = []
burn_mode = {"fail": False}


class FakeBurnWire:
    def __init__(self, *a):
        pass

    def cubesatBurn(self, num, duty, dur):
        burns.append(clock[0])
        if burn_mode["fail"]:
            raise RuntimeError("relay fail")

    def burningCheck(self):
        return "not burning"


m = types.ModuleType("BurnWire")
m.BurnWire = FakeBurnWire
sys.modules["BurnWire"] = m
m = types.ModuleType("PayloadUART")
m.PayloadUART = lambda *a: None
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
    burns.clear()
    burn_mode["fail"] = False
    Q._nvm[Q._NVM_DEPLOYED] = 0
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
            f.mission_time = clock[0]
            tl = f.tasks
            for t in sorted(tl, key=lambda t: t.priority):
                if t.is_due(clock[0]):
                    t.run()
                    if f.tasks is not tl:
                        break
            if cm:
                cm.update()


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
    assert f.state in (StateID.SCIENCE, StateID.COMMS)


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
    assert len(burns) == 1, "repeats of DEPLOY while in DEPLOY must not re-arm the burn"


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
    assert len(burns) > 10 and f.state == StateID.IDLE and not f.deployed
    burn_mode["fail"] = False
    step(f, cm, 30, int(3 * 3600 / 30))
    assert f.deployed


def test_burn_ok_but_silent_reburns_until_ground_heard():
    f, cm, radio = make()
    step(f, cm, 30, int(40 * 3600 / 30))
    assert len(burns) >= 3  # first burn + 12 h re-burns
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
    assert f.state == StateID.DEPLOY and len(burns) == n + 1


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
    assert len(pkt) == 13 and pkt[0] == 1 and pkt[1] == StateID.IDLE


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
    assert f.mission_time > 3600
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
