"""
A simulated PyCubed world around the REAL flight modules (QubeSatFSM, Comms, Task, StateCodeGenerator).

Only the hardware is faked: the board library, the burn wire driver, the payload UART, the radio
chip and the clock. Time is virtual, so days of mission time run in seconds, and blocking calls
(a burn, a payload measurement) advance the virtual clock by how long the real ones take.

Not simulated: SPI/RF behaviour, heap limits, real SD quirks, electrical behaviour. See README.md.
"""

import collections
import io
import math
import os
import random
import re
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
NEWCODE = os.path.join(os.path.dirname(HERE), "pycubed", "NewCode")
sys.path.insert(0, NEWCODE)

# ---------------------------------------------------------------- virtual clock
_clock = [0.0]
time.monotonic = lambda: _clock[0]
time.sleep = lambda s: _clock.__setitem__(0, _clock[0] + s)  # nothing in the FSM needs real waiting


def now():
    return _clock[0]


# ---------------------------------------------------------------- console capture
class _Console:
    """Everything the flight code prints, prefixed with virtual time. Kept in a ring; shown live if `live`."""

    def __init__(self):
        self.lines = collections.deque(maxlen=5000)
        self.live = False
        self.real = sys.stdout
        self.listener = None  # fn(time, text) called for every finished line
        self._buf = ""

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if self.listener:
                self.listener(now(), line)
            line = f"[{fmt_time(now())}] {line}"
            self.lines.append(line)
            if self.live:
                self.real.write(line + "\n")
        return len(s)

    def flush(self):
        pass


console = _Console()

# Lines the flight code prints that are events worth showing during `run`/`until`. Everything that
# starts with a [TAG] is one, except the chatty ones below (still in the full log: `log N`).
EVENT_SKIP = ("[SCIENCE] sweep ", "[BATTERY] Voltage:", "[COMMS] Solar charging")


def fmt_time(t):
    d, rem = divmod(int(t), 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return (f"{d}d " if d else "") + f"{h:02d}:{m:02d}:{s:02d}"


def parse_duration(text):
    """'90s', '10m', '2h', '3d', or a plain number of seconds."""
    text = text.strip().lower()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if text and text[-1] in units:
        return float(text[:-1]) * units[text[-1]]
    return float(text)


# ---------------------------------------------------------------- fake hardware
class Settings:
    """Knobs the CLI and tests turn. Defaults describe a healthy satellite."""

    battery_v = 8.2
    temperature_c = 25.0
    solar_charging = True
    sd_present = True
    sd_capacity = None  # bytes; None = effectively unlimited
    payload_online = True
    radio_hung = False
    burn_fail = False
    burn_fail_wire = None  # '1' or '2'
    contrast_latency_s = 1.0  # measured on the board
    photodiode_latency_s = 0.4  # inferred, see docs/FSM_TODO.md F6
    # synthetic ODMR spectrum: two dips (Zeeman split) around 2870 MHz
    odmr_center = 2870.0
    odmr_split = 14.0
    odmr_depth = 0.12
    odmr_width = 5.0
    odmr_noise = 0.004


S = Settings()
burn_log = []  # (virtual time, wire, duty, duration)


class FakeCubeSat:
    """Only what the real board library provides (checked against pycubed/NewCode/lib/pycubed.py)."""

    hardware = {"Radio1": True}
    c_state_err = 0
    c_boot = 1

    def __init__(self, sd_dir):
        self._relayA = types.SimpleNamespace(drive_mode=None, value=False)
        self.sd_dir = sd_dir
        self.n_files = 0
        self.micro = _Micro(self)

    battery_voltage = property(lambda self: S.battery_v)
    temperature = property(lambda self: S.temperature_c)
    solar_charging = property(lambda self: S.solar_charging)

    def charge_current(self):  # a plain method on the real board
        return 120.0 if S.solar_charging else 0.0

    mounted = True  # the board library mounts the card once, in __init__, and never again

    def new_file(self, substring, binary=False):
        if not (S.sd_present and self.mounted):
            return None
        self.n_files += 1
        return os.path.join(self.sd_dir, "mission%05d.txt" % self.n_files)

    def log(self, msg):
        pass


class _Micro:
    class RunMode:
        NORMAL = 0

    def __init__(self, owner):
        self.owner = owner
        self.resets = 0

    def on_next_reset(self, mode):
        pass

    def reset(self):
        self.resets += 1
        raise _Reset()


class _Reset(BaseException):
    """A hard reset requested by the flight code; the world turns it into a reboot."""


class _PWMOut:
    """pwmio.PWMOut as the real BurnWire.py uses it. Logs how long each wire was really driven."""

    def __init__(self, pin, frequency=500, duty_cycle=0):
        if S.burn_fail or S.burn_fail_wire == pin[-1]:
            raise RuntimeError("burn driver fault (simulated)")
        self.pin, self._duty, self._on_at, self._peak = pin, 0, None, 0
        self.duty_cycle = duty_cycle

    @property
    def duty_cycle(self):
        return self._duty

    @duty_cycle.setter
    def duty_cycle(self, value):
        if value > 0 and self._on_at is None:
            self._on_at = now()
            print(f"[SIM] burn wire {self.pin[-1]} ON at {value / 0xFFFF * 100:.2f}% duty")
        if value > 0:
            self._peak = max(self._peak, value)
        if value == 0:
            self._end()
        self._duty = value

    def _end(self):
        if self._on_at is not None:
            burn_log.append((now(), self.pin[-1], round(self._peak / 0xFFFF * 100, 3), now() - self._on_at))
            print(f"[SIM] burn wire {self.pin[-1]} OFF after {now() - self._on_at:.0f} s")
            self._on_at = None

    def deinit(self):
        self._end()


def _hardware_modules():
    board = types.ModuleType("board")
    board.BURN1, board.BURN2 = "BURN1", "BURN2"
    digitalio = types.ModuleType("digitalio")
    digitalio.DriveMode = types.SimpleNamespace(PUSH_PULL="push-pull", OPEN_DRAIN="open-drain")
    pwmio = types.ModuleType("pwmio")
    pwmio.PWMOut = _PWMOut
    microcontroller = types.ModuleType("microcontroller")
    microcontroller.cpu = types.SimpleNamespace(reset_reason="POWER_ON (simulated)")
    return {"board": board, "digitalio": digitalio, "pwmio": pwmio, "microcontroller": microcontroller}


def _import_real_burnwire():
    """Import the real BurnWire.py over fake board/pwmio/digitalio/microcontroller, then take the fakes
    away again so Comms and the FSM still see 'no microcontroller' and use their desktop NVM fallback."""
    fakes = _hardware_modules()
    saved = {k: sys.modules.get(k) for k in fakes}
    sys.modules.update(fakes)
    try:
        sys.modules.pop("BurnWire", None)
        import BurnWire  # noqa: F401
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return sys.modules["BurnWire"]


def odmr_contrast(freq, rng=random):
    lo, hi = S.odmr_center - S.odmr_split / 2, S.odmr_center + S.odmr_split / 2
    w2 = S.odmr_width ** 2
    dip = S.odmr_depth * (w2 / ((freq - lo) ** 2 + w2) + w2 / ((freq - hi) ** 2 + w2))
    return 1.0 - dip + rng.gauss(0, S.odmr_noise)


class FakePayload:
    def ping(self):
        return S.payload_online

    def read_photodiode(self):
        _clock[0] += S.photodiode_latency_s
        return 1.5e-6 if S.payload_online else None

    def measure_contrast(self, freq, timeout=30.0):
        if not S.payload_online:
            _clock[0] += min(timeout, 30.0)  # a dead payload costs the whole timeout
            return None
        _clock[0] += S.contrast_latency_s
        return odmr_contrast(freq)


class FakeRadio:
    """The SX127x as the FSM and Comms see it. rx holds frames waiting to be heard, tx what was sent."""

    def __init__(self):
        self.rx, self.tx = [], []

    def receive(self, timeout=0, with_header=False):
        if S.radio_hung:
            raise RuntimeError("spi hang (simulated)")
        return self.rx.pop(0) if self.rx else None

    def send(self, b, destination=None, node=None, identifier=None, flags=None, **kw):
        if S.radio_hung:
            raise RuntimeError("spi hang (simulated)")
        self.tx.append(bytes([destination or 0, node or 0, identifier or 0, flags or 0]) + bytes(b))

    regs = None

    def sleep(self):
        pass

    def idle(self):
        pass

    def _write_u8(self, address, value):
        if self.regs is None:
            self.regs = {}
        self.regs[address] = value


_pycubed = types.ModuleType("pycubed")  # one module object for the whole process: BurnWire keeps a reference


def _install_fake_modules(cubesat):
    _pycubed.cubesat = cubesat
    sys.modules["pycubed"] = _pycubed
    if "BurnWire" not in sys.modules or not hasattr(sys.modules["BurnWire"], "_sim_real"):
        _import_real_burnwire()
        sys.modules["BurnWire"]._sim_real = True
    m = types.ModuleType("PayloadUART")
    m.PayloadUART = lambda *a: FakePayload()
    sys.modules["PayloadUART"] = m
    # The real DualModeRadio needs SX127x register access (tested on its own in test_dual_mode_radio.py).
    dm = types.ModuleType("DualModeRadio")
    dm.LORA, dm.FSK, dm.MAX_FSK_PACKET = 0, 1, 63

    class Stub:
        def __init__(self, radio):
            self.radio = radio
            self.modulation = dm.LORA

        def set_modulation(self, modulation):
            self.modulation = modulation

        def send_packet(self, packet):
            self.radio.tx.append(bytes(packet))
            return True

        def receive_packet(self, timeout=0.1):
            if S.radio_hung:
                raise RuntimeError("spi hang (simulated)")
            return self.radio.rx.pop(0) if self.radio.rx else None

    dm.DualModeRadio = Stub
    sys.modules["DualModeRadio"] = dm


# ---------------------------------------------------------------- the world
class World:
    def __init__(self, dt=1.0, sd_dir=None, seed=1):
        random.seed(seed)
        _clock[0] = 0.0
        S.__dict__.clear()  # back to the healthy defaults
        burn_log.clear()
        console.lines.clear()
        self.dt = dt
        self.sd_dir = sd_dir or tempfile.mkdtemp(prefix="qubesat_sd_")
        self.cubesat = FakeCubeSat(self.sd_dir)
        sys.stdout = console  # flight code prints into the capture, the CLI prints via console.real
        console.listener = self._on_line
        self.events = []  # (time, text): see _on_line
        self.echo = False
        self._last_key, self._repeat, self._last_t = None, 0, 0.0
        _install_fake_modules(self.cubesat)
        import Comms
        import QubeSatFSM
        import StateCodeGenerator

        self.C, self.Q, self.StateID = Comms, QubeSatFSM, StateCodeGenerator.StateID
        Comms.cubesat = QubeSatFSM.cubesat = self.cubesat  # modules cached from an earlier World hold the old one
        self.radio = FakeRadio()
        self.resets = 0
        self.beacons = []  # decoded TinyGS beacons heard by the "ground"
        self.other_tx = []  # anything else the satellite sent
        self._patch_sd_free()
        self.fsm = None
        self.comms = None
        self.boot(clear_nvm=True)

    # -- SD size limit ----------------------------------------------------------------
    def _patch_sd_free(self):
        def free_bytes(directory):
            if S.sd_capacity is None:
                return None
            used = sum(os.path.getsize(os.path.join(self.sd_dir, n)) for n in os.listdir(self.sd_dir))
            return max(0, S.sd_capacity - used)

        self.Q._sd_free_bytes = free_bytes

    # -- power cycle -------------------------------------------------------------------
    def boot(self, clear_nvm=False):
        """Create a fresh FSM and Comms on the same NVM (a reboot), or on blank NVM (a factory-fresh board)."""
        if clear_nvm:
            for nvm in (self.Q._nvm, self.C._nvm):
                for i in range(len(nvm)):
                    nvm[i] = 0
            os.chmod(self.sd_dir, 0o755)
            for name in os.listdir(self.sd_dir):
                os.remove(os.path.join(self.sd_dir, name))
            self.cubesat.n_files = 0
            burn_log.clear()
        self.cubesat.mounted = S.sd_present  # the library tries the card at boot
        self._apply_sd()
        self.fsm = self.Q.QubeSatFSM()
        self.comms = self.C.CommsManager(self.radio)
        if clear_nvm:
            self.comms.state_code = self.StateID.IDLE  # blank NVM would be STOP (silent); see FSM_TODO F1
        self.fsm.attach_comms(self.comms)
        self.radio.rx.clear()

    # -- SD card -----------------------------------------------------------------------
    def set_sd(self, present):
        """Pull or insert the card. A pulled card makes writes fail at once; an inserted one is only
        mounted at the next boot (lib/pycubed.py has no remount), so writes stay broken until `reboot`."""
        S.sd_present = present
        if not present:
            self.cubesat.mounted = False  # the mount is dead once the card has gone; only a boot makes a new one
        self._apply_sd()

    def _apply_sd(self):
        ok = S.sd_present and self.cubesat.mounted
        os.chmod(self.sd_dir, 0o755 if ok else 0o555)
        for n in os.listdir(self.sd_dir):
            os.chmod(os.path.join(self.sd_dir, n), 0o644 if ok else 0o444)

    def reboot(self):
        self.resets += 1
        print(f"[SIM] reboot #{self.resets}")
        self.boot(clear_nvm=False)

    # -- events --------------------------------------------------------------------------
    def _on_line(self, t, text):
        if not (text.startswith("[") and "]" in text[:16]) or text.startswith(EVENT_SKIP):
            return
        self.events.append((t, text))
        if len(self.events) > 20000:
            del self.events[:5000]
        if self.echo:
            self._show(t, text)

    def _show(self, t, text):
        """Print an event now, but fold a run of near-identical ones (same text, other numbers) into one line."""
        key = re.sub(r"\d+(?:\.\d+)?", "#", text)
        if key == self._last_key:
            self._repeat += 1
            self._last_t = t
            return
        self.flush_events()
        self._last_key = key
        console.real.write(f"  [{fmt_time(t)}] {text}\n")

    def flush_events(self):
        if self._repeat:
            console.real.write(f"      ... {self._repeat} more like that, last at {fmt_time(self._last_t)}\n")
        self._last_key, self._repeat = None, 0

    # -- running -----------------------------------------------------------------------
    def advance(self, seconds, stop=None, echo=False):
        """Run the FSM loop for `seconds` of virtual time (or until stop() is true). Returns seconds run.
        With echo=True, events (state changes, burns, faults, commands heard, packets sent) print as they happen."""
        self.echo = echo
        try:
            return self._advance(seconds, stop)
        finally:
            if echo:
                self.flush_events()
            self.echo = False

    def _advance(self, seconds, stop):
        start = now()
        end = start + seconds
        while now() < end:
            if stop and stop():
                break
            _clock[0] += self.dt
            try:
                try:
                    self.fsm.tick(now())
                except _Reset:
                    raise
                except Exception as e:  # mirrors the handler in QubeSatFSM.run(): count, wait 10 s, hard reset
                    print("[FSM] FATAL ERROR:", e)
                    self.fsm.crash_streak += 1
                    self.Q._save_streak(self.fsm.crash_streak)
                    _clock[0] += 10
                    raise _Reset()
            except _Reset:
                self.reboot()
            self._collect_tx()
        return now() - start

    def _collect_tx(self):
        if not self.radio.tx:
            return
        import tinygs_decoder

        for pkt in self.radio.tx:
            info = tinygs_decoder.decode(pkt)
            (self.beacons if info else self.other_tx).append((now(), info or pkt))
            if info:
                print(f"[SIM] TX TinyGS beacon ({len(pkt)} B): state {info['state_name']}, mission time {info['mission_time_s']} s")
            else:
                kind = pkt[1] if len(pkt) > 1 else 0
                print(f"[SIM] TX {len(pkt)} B packet, type 0x{kind:02x}: tinygs_decoder cannot decode it")
        self.radio.tx.clear()

    # -- ground station ----------------------------------------------------------------
    def ground_send(self, state, lock=False, repeat=1):
        print(f"[SIM] ground queues: set state {self.StateID.name(state)}{' + lock' if lock else ''}")
        for _ in range(repeat):
            self.radio.rx.append(self.C.build_state_command(state, lock=lock))

    # -- inspection --------------------------------------------------------------------
    def science_files(self):
        return sorted(n for n in os.listdir(self.sd_dir) if n.startswith("mission"))

    def read_rows(self, name=None):
        names = [name] if name else self.science_files()
        rows = []
        for n in names:
            with open(os.path.join(self.sd_dir, n)) as fh:
                for line in fh:
                    p = line.strip().split(",")
                    if line.strip() and p[0] != "mission_s":
                        rows.append(p)
        return rows

    def status(self):
        f, S_ = self.fsm, self.StateID
        sweep_rows = len(self.read_rows(self.science_files()[-1])) if self.science_files() else 0
        return collections.OrderedDict(
            time=fmt_time(now()),
            state=S_.name(f.state),
            locked=f.locked,
            uptime=fmt_time(f.uptime),
            mission_time=fmt_time(f.mission_time),
            deployed=f.deployed,
            burns=f"{len(burn_log)} (wires {[b[1] for b in burn_log]})",
            sweeps_completed=f.sweeps_completed,
            sweep_freq_mhz=f.current_sweep_freq,
            science_files=len(self.science_files()),
            rows_in_latest_file=sweep_rows,
            battery_v=S.battery_v,
            comms_state_code=self.comms.state_code,
            beacons_heard=len(self.beacons),
            payload_errors=f.payload_errors,
            task_errors=f.task_error_total,
            reboots=self.resets,
        )
