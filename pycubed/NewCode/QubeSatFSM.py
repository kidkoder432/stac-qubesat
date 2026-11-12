import time

from BurnWire import BurnWire
from PayloadUART import PayloadUART
from PowerLevel import PowerLevel
from StateCodeGenerator import StateCodec, StateID
from Task import Task

# Same import form as Comms.py. Importing it under two names (pycubed vs lib.pycubed)
# would load the module twice and create two hardware objects.
from lib.pycubed import cubesat
from Comms import build_beacon_packet

import struct

# NVM map (Q-X6). The pycubed library uses bytes 0-16, Comms.py uses 20-26. The FSM uses:
#   19      deployed flag (magic)
#   32-71   mission-time ring: 8 slots x 5 bytes (u32 seconds big-endian + checksum)
#   72-74   state lock: magic, locked state, state ^ 0xC3
#   75      "ground has been heard since deploy" flag (magic)
# Fresh NVM may read as 0x00 or 0xFF; every record below needs a valid magic/checksum, and
# neither all-zero nor all-0xFF passes, so fresh NVM reads as "nothing saved".
_NVM_DEPLOYED = 19
_DEPLOYED_MAGIC = 0xD5
_NVM_CLOCK = 32
_CLOCK_SLOTS = 8
_CLOCK_SLOT_SIZE = 5
_NVM_LOCK = 72
_LOCK_MAGIC = 0xA5
_NVM_CONTACT = 75
_CONTACT_MAGIC = 0xC7

try:
    import microcontroller

    _nvm = microcontroller.nvm
except ImportError:
    _nvm = bytearray(256)  # desktop fallback


def _nvm_put(index, value):
    """Write one NVM byte only if it changed (flash wear)."""
    if _nvm[index] != value:
        _nvm[index] = value


def _load_deployed():
    try:
        return _nvm[_NVM_DEPLOYED] == _DEPLOYED_MAGIC
    except Exception:
        return False


def _save_deployed():
    try:
        _nvm_put(_NVM_DEPLOYED, _DEPLOYED_MAGIC)
    except Exception as e:
        print("[FSM] Could not persist deployed flag:", e)


def _load_contact():
    try:
        return _nvm[_NVM_CONTACT] == _CONTACT_MAGIC
    except Exception:
        return False


def _save_contact():
    try:
        _nvm_put(_NVM_CONTACT, _CONTACT_MAGIC)
    except Exception as e:
        print("[FSM] Could not persist ground-contact flag:", e)


def _clock_checksum(raw4):
    return (raw4[0] + raw4[1] + raw4[2] + raw4[3]) & 0xFF ^ 0x5A


def _clock_slot_value(slot):
    base = _NVM_CLOCK + slot * _CLOCK_SLOT_SIZE
    rec = bytes(_nvm[base : base + _CLOCK_SLOT_SIZE])
    if len(rec) != _CLOCK_SLOT_SIZE or _clock_checksum(rec) != rec[4]:
        return None
    return struct.unpack(">I", rec[:4])[0]


def _load_clock():
    """Return (seconds, slot) of the newest valid record. (0, -1) if there is none."""
    best, best_slot = None, -1
    try:
        for slot in range(_CLOCK_SLOTS):
            v = _clock_slot_value(slot)
            if v is not None and (best is None or v > best):
                best, best_slot = v, slot
    except Exception:
        return 0, -1
    return (best if best is not None else 0), best_slot


def _save_clock(seconds, last_slot):
    """Write to the slot after the newest one, so a power cut mid-write leaves the older record valid."""
    slot = (last_slot + 1) % _CLOCK_SLOTS
    raw = struct.pack(">I", int(seconds) & 0xFFFFFFFF)
    base = _NVM_CLOCK + slot * _CLOCK_SLOT_SIZE
    _nvm[base : base + _CLOCK_SLOT_SIZE] = raw + bytes([_clock_checksum(raw)])
    return slot


def _load_lock():
    """The state the ground locked, or None."""
    try:
        if _nvm[_NVM_LOCK] == _LOCK_MAGIC and _nvm[_NVM_LOCK + 2] == _nvm[_NVM_LOCK + 1] ^ 0xC3:
            return _nvm[_NVM_LOCK + 1]
    except Exception:
        pass
    return None


def _save_lock(state):
    """state = the locked state code, or None to clear. Magic is written last."""
    try:
        if state is None:
            _nvm_put(_NVM_LOCK, 0)
        else:
            _nvm_put(_NVM_LOCK + 1, state)
            _nvm_put(_NVM_LOCK + 2, state ^ 0xC3)
            _nvm_put(_NVM_LOCK, _LOCK_MAGIC)
    except Exception as e:
        print("[FSM] Could not persist lock:", e)


def _temperature_c():
    """IMU temperature in degC (the board has no CPU/battery temp sensor), or None."""
    try:
        return cubesat.temperature
    except Exception:
        return None


class TemperatureCheck:
    MAX_C = 60.0

    def is_safe(self):
        temp = _temperature_c()
        if temp is None:
            return True  # no reading (IMU missing); don't force IDLE on a missing sensor
        return temp < self.MAX_C


class QubeSatFSM:
    high_level_threshold = 8.4  # this is enforced by pycube itself
    low_level_threshold = (
        6.0  # when it reaches this low level -> switch to idle/charging state
    )

    # ---- configurable mission constants (all in seconds unless noted) ----
    DEPLOY_AFTER_IDLE_S = 60 * 60  # boot in IDLE, go to DEPLOY after this long
    BURN_MAX_ATTEMPTS = 3  # tries per visit to DEPLOY before falling back to IDLE

    # Antenna watchdog. There is no sensor saying the antenna actually deployed, and if it
    # didn't, the ground probably can't reach us, so recovery has to be autonomous.
    # "Ground contact" = a valid command received after the burn ran.
    BURN_RETRY_BACKOFF_S = 60 * 60  # burn raised an error: retry this often (any state)
    BURN_REBURN_AFTER_S = 12 * 60 * 60  # burn "worked" but we never heard from ground: re-burn
    BURN_MAX_TOTAL = 20  # cap on wire burns that actually ran, per boot (10 per wire); errors don't count
    # Both wires are needed: each releases one half of the dipole antenna (Q-D3).
    BURN_WIRES = ("1", "2")
    # UNKNOWN until the burn-wire team answers Q-D1. Passed to BurnWire exactly as before
    # (it treats the first as a percent and ignores the second, see docs/FSM_SPEC.md section 6).
    BURN_DUTY = 0.25
    BURN_DURATION_S = 30
    MISSION_CLOCK_SAVE_S = 15 * 60  # save mission time to NVM this often (lost on reboot: up to this much)
    BAT_THRESH_SCIENCE = 8.0  # volts needed to leave IDLE (low threshold above = 6.0)

    # Science / comms split (Q-S6, TODO B1). Measured in mission time (seconds since the burn):
    #   first SCIENCE_ONLY_S: 100% SCIENCE (the IARU agreement)
    #   after that: a repeating cycle of SLOT_S slots, COMMS_SLOTS of COMMS then SCIENCE_SLOTS of
    #   SCIENCE (7 x 10 min comms, 3 x 10 min science = 70% / 30%).
    # The state is a pure function of mission time, so it also survives a reboot.
    SCIENCE_ONLY_S = 14 * 24 * 3600
    SLOT_S = 10 * 60
    COMMS_SLOTS = 7
    SCIENCE_SLOTS = 3

    # When the ground has locked a state, should a low battery / overheat still force IDLE?
    # True  = yes (safe: protects against brownout; the lock is cleared when it happens)
    # False = no, the lock wins no matter what
    LOW_BATTERY_OVERRIDES_LOCK = True

    # initalizing some values/parts of the qubesat (still very incomplete atp)
    """
            let mission time be counted in seconds since FSM starts
            for a task:
                if scheduled_later==False -> wait the amount of time specified by period 
                otherwise -> execute state immediately
    """

    def __init__(self):
        self.state = StateID.IDLE  # default state = charging mode
        self.current_code = StateCodec.encode(StateID.IDLE)
        # Two clocks. `uptime` = seconds since this boot (timers: deploy wait, watchdog, ...).
        # `mission_time` (property) = seconds since the burn wire first fired, kept in NVM
        # so it survives reboots (Q-M3). It is 0 until the burn.
        self.uptime = 0.0
        self._start_time = time.monotonic()
        self._clock_base = 0  # mission seconds already counted before this boot
        self._clock_started_at = None  # uptime when mission time started counting; None = not started
        self._clock_slot = -1
        self._clock_saved_at = 0.0
        self.log_file = None
        self.deployed = _load_deployed()  # True once both burn wires have fired (persists)
        if self.deployed:
            self._clock_base, self._clock_slot = _load_clock()
            self._clock_started_at = 0.0
        self.burn_done = {w: False for w in self.BURN_WIRES}  # wires fired in the current burn cycle
        self.burn_attempts = 0
        self.burn_total = 0  # burns attempted since boot (watchdog cap)
        self._last_burn_time = None  # uptime of the last burn attempt
        # uptime of the first command heard after deploy; remembered across reboots so a
        # working antenna is not burned again after every reset
        self.last_ground_contact = 0.0 if (self.deployed and _load_contact()) else None
        self.locked = False  # True = ground has locked the state; transition checks do nothing
        self.power = PowerLevel()
        self.temperature = (
            TemperatureCheck()
        )  # makes sure that the temperature doesn't overheat and mess up the battery since there's apparently a way to check the temperature we js gotta figure out how to do that but don't worry about it for now

        # making a dictionary with key = "equipment" and value = period (in seconds)
        # have to fill in the periods for the other things later on!!
        self.periods = {
            "beacon": 30 * 60,
            "battery_check": 60,
            "transition": 10,
            "sd_card": 30 * 60,
            "burn_wire": 60,  # retry interval if the burn fails (the 60 min wait is DEPLOY_AFTER_IDLE_S)
            "receive_data": 10,
            "record_memory": 10,
            "init_payload": (30 * 60),
            "watchdog": 10 * 60,
        }

        # boolean values to check different stages of mission
        self.experiment_started = (
            False  # this is True if experiment has started/isrunning and false if not
        )
        self.sd_card_initialized = (
            False  # shouldn't be initalized until after deployment
        )
        self.solar_panels_on = False

        # boolean values to check that the equipment is functional
        # initialize them to false (after they are checked -> every value should = True)
        self.equipment_check = {
            "sd_card": False,
            "burn_wire": False,
            "payload": False,
            "solar_panel": False,
            "radio": False,
        }

        # Payload Subsystem
        self.payload = PayloadUART(cubesat)
        self.current_sweep_freq = 2800  # Start of ODMR sweep range (2800..2950 MHz)
        self.latest_data = None

        self.comms = None

        # making a dictionary to be able to call each state
        # should execute all of the actions in each state
        self.tasks = self._build_tasks_for_state(self.state)

    @property
    def mission_time(self):
        """Seconds since the burn wire first fired (persisted); 0 before the burn."""
        if self._clock_started_at is None:
            return float(self._clock_base)
        return self._clock_base + (self.uptime - self._clock_started_at)

    def _start_mission_clock(self):
        if self._clock_started_at is not None:
            return  # already counting; a re-burn does not restart it
        self._clock_base = 0
        self._clock_started_at = self.uptime
        self._save_mission_clock()

    def _save_mission_clock(self):
        try:
            self._clock_slot = _save_clock(self.mission_time, self._clock_slot)
        except Exception as e:
            print("[FSM] Could not persist mission time:", e)
        self._clock_saved_at = self.uptime

    def _maybe_save_mission_clock(self):
        if (
            self._clock_started_at is not None
            and self.uptime - self._clock_saved_at >= self.MISSION_CLOCK_SAVE_S
        ):
            self._save_mission_clock()

    def _state_builders(self):
        return {
            StateID.IDLE: self.build_idle_tasks,
            StateID.DEPLOY: self.build_deploy_tasks,
            StateID.SCIENCE: self.build_science_tasks,
            StateID.COMMS: self.build_comms_tasks,
        }

    def _build_tasks_for_state(self, state: StateID):
        return self._state_builders()[state]()

    # building tasks for each of the states

    # tasks that should be executed when in the idle state
    def build_idle_tasks(self):
        tasks = [
            Task(
                "Beacon",
                1,
                self.periods["beacon"],
                schedule_later=False,
                func=self._task_beacon,
            ),
            Task(
                "Battery Check",
                2,
                self.periods["battery_check"],
                schedule_later=True,
                func=self._task_battery_check,
            ),
            Task(
                "Transition Check",
                3,
                self.periods["transition"],
                schedule_later=True,
                func=self._task_transition_check,
            ),
            self._watchdog_task(4),
        ]
        return tasks

    def _watchdog_task(self, priority):
        return Task(
            "Antenna Watchdog",
            priority,
            self.periods["watchdog"],
            schedule_later=True,
            func=self._task_antenna_watchdog,
        )

    # initalize sd card -> activate burn wire -> check battery -> beacon -> transition
    def build_deploy_tasks(self):
        tasks = [
            # one-shot, runs immediately
            Task(
                "SD_Card",
                1,
                None,
                schedule_later=False,
                func=self._task_init_sd_card,
            ),
            # fires on entering DEPLOY; retries every period until it works (removes itself)
            Task(
                "Burn Wire",
                2,
                self.periods["burn_wire"],
                schedule_later=False,
                func=self._task_activate_burn_wire,
            ),
            Task(
                "Battery Check",
                3,
                self.periods["battery_check"],
                schedule_later=True,
                func=self._task_battery_check,
            ),
            Task(
                "Beacon",
                4,
                self.periods["beacon"],
                schedule_later=True,
                func=self._task_beacon,
            ),
            Task(
                "Transition Check",
                5,
                self.periods["transition"],
                schedule_later=True,
                func=self._task_transition_check,
            ),
        ]
        return tasks

    def build_comms_tasks(self):
        tasks = [
            Task(
                "Solar Panel Enable",
                1,
                self.periods["battery_check"],
                schedule_later=False,
                func=self._task_enable_solar_panels,
            ),
            Task(
                "Battery Check",
                2,
                self.periods["battery_check"],
                schedule_later=True,
                func=self._task_battery_check,
            ),
            Task(
                "Beacon",
                3,
                self.periods["beacon"],
                schedule_later=True,
                func=self._task_beacon,
            ),
            Task(
                "Transition Check",
                4,
                self.periods["transition"],
                schedule_later=True,
                func=self._task_transition_check,
            ),
            self._watchdog_task(5),
        ]
        return tasks

    def build_science_tasks(self):
        tasks = [
            # one-shot ping of the payload when entering science
            Task(
                "Initialize Payload",
                1,
                None,
                schedule_later=False,
                func=self._task_init_payload,
            ),
            Task(
                "Battery Check",
                2,
                self.periods["battery_check"],
                schedule_later=True,
                func=self._task_battery_check,
            ),
            Task(
                "Receive Data",
                3,
                self.periods["receive_data"],
                schedule_later=True,
                func=self._task_receive_data,
            ),
            Task(
                "Record to Memory",
                4,
                self.periods["record_memory"],
                schedule_later=True,
                func=self._task_record_memory,
            ),
            Task(
                "Transition Check",
                5,
                self.periods["transition"],
                schedule_later=True,
                func=self._task_transition_check,
            ),
            self._watchdog_task(6),
        ]
        return tasks

    """
        this state is entered when battery is below the low_power_threshold

    """

    # going to start defining the functions that are ran for each action in the tasks

    def transition(self, new_state: StateID, force=False):
        # force=True is for ground commands and safety overrides; everything the
        # autonomous logic does goes through here with force=False and respects the lock.
        if self.locked and not force:
            return
        if new_state == self.state:
            return  # already here, do nothing
        if new_state not in self._state_builders():
            # unknown code, or STOP (STOP is a Comms command, not an FSM state)
            print(f"[FSM] No task list for state {new_state}, ignoring transition.")
            return
        print(f"[FSM] Transition: {StateID.name(self.state)} -> {StateID.name(new_state)}")
        self.state = new_state
        self.current_code = StateCodec.encode(
            new_state
        )  # adding this so that when state changes -> so does current code
        self.tasks = self._build_tasks_for_state(new_state)

    # Check for critical battery voltages - not to be used for science. 
    def _task_battery_check(self):
        try:
            vbatt = cubesat.battery_voltage
            print(f"[BATTERY] Voltage: {vbatt:.2f} V")

            if not self.temperature.is_safe():
                print("[BATTERY] Temperature unsafe — going idle.")
                self._safety_idle()
                return

            if vbatt <= self.low_level_threshold:
                print("[BATTERY] Low battery — going idle.")
                self._safety_idle()
        except Exception as e:
            print("[BATTERY] Check error:", e)

    def _safety_idle(self):
        """Forced IDLE for low battery / overheating. Overrides a ground lock if configured to."""
        if self.state == StateID.IDLE:
            return
        if self.locked:
            if not self.LOW_BATTERY_OVERRIDES_LOCK:
                print("[FSM] Safety wants IDLE but state is locked; staying put.")
                return
            print("[FSM] Safety override: clearing ground lock.")
            self.locked = False
        self.transition(StateID.IDLE, force=True)

    # ---- ground commands (called by CommsManager) ----
    def attach_comms(self, comms):
        """Wire a CommsManager to the FSM: state commands in, telemetry out."""
        self.comms = comms
        comms.on_state_command = self.command_state
        comms.on_tx_window = self._on_tx_window

    def command_state(self, code, lock=False):
        """
        Ground says: go to state `code`, and lock (True) or unlock (False) the transition logic.
        lock=True  -> sit in this state; the transition check does nothing until unlocked
        lock=False -> go to this state, then autonomous transitions take over again
        """
        if not StateID.is_valid(code):
            print("[FSM] Ground sent unknown state code:", code)
            return
        new_state = code
        print(f"[FSM] Ground command: {StateID.name(new_state)}, lock={bool(lock)}")
        if self.deployed and self.last_ground_contact is None:
            self.last_ground_contact = self.uptime  # antenna evidently works
            _save_contact()
        if new_state == StateID.STOP:
            # Comms has already stopped transmitting (it keeps listening). The FSM keeps
            # running in its current state; sending any non-zero state resumes transmission.
            print("[FSM] STOP: transmission halted by Comms, FSM state unchanged.")
            return
        self.locked = bool(lock)
        # The ground repeats a command for reliability, so a command for the state we are
        # already in must change nothing (Q-H8, Q-G5): transition() ignores it.
        if new_state == StateID.DEPLOY and self.state != StateID.DEPLOY:
            # entering DEPLOY by command = try the burn wire again, even if it gave up before.
            # (To re-burn while already in DEPLOY, command another state first.)
            self.burn_attempts = 0
            self.burn_done = {w: False for w in self.BURN_WIRES}
        self.transition(new_state, force=True)

    def telemetry_packet(self):
        """
        13-byte snapshot of internal state, big-endian:
          u8  packet type/version (0x01). A TinyGS beacon starts with the ASCII callsign
              (e.g. 'S'), so a first byte of 0x01 identifies this packet.
          u8  state code
          u8  flags: b0 locked, b1 deployed, b2 sd, b3 burn wire, b4 payload, b5 solar, b6 radio
          u8  burn attempts
          u16 battery, centivolts
          i16 IMU temp, centi-degC
          u32 mission time, seconds
          u8  c_state_err (FSM crash count)
        """
        eq = self.equipment_check
        flags = (
            (self.locked << 0)
            | (self.deployed << 1)
            | (eq["sd_card"] << 2)
            | (eq["burn_wire"] << 3)
            | (eq["payload"] << 4)
            | (eq["solar_panel"] << 5)
            | (eq["radio"] << 6)
        )
        try:
            vbatt = int(cubesat.battery_voltage * 100)
        except Exception:
            vbatt = 0
        t = _temperature_c()
        temp = int(t * 100) if t is not None else 0
        err = getattr(cubesat, "c_state_err", 0)
        return struct.pack(
            ">BBBBHhIB",
            1,
            int(self.state),
            flags,
            self.burn_attempts & 0xFF,
            max(0, min(vbatt, 0xFFFF)),
            max(-32768, min(temp, 32767)),
            int(self.mission_time),
            err & 0xFF,
        )

    def _on_tx_window(self, window_num, cadence):
        """CommsManager calls this at the start of each TX window."""
        if self.comms and window_num % max(1, cadence) == 0:
            self.comms.push_telemetry(self.telemetry_packet())

    def halt_transmission(self):
        # stop beacon and any outgoing radio tasks
        self.tasks = [t for t in self.tasks if t.name != "Beacon"]

    # lowkey shouldnt it always be turned on?
    # okie need to turn on solar panel
    # i think solar input is enabled by hardware and not software, so ill just check current for now
    def _task_enable_solar_panels(self):
        try:
            # board API: solar_charging (bool, LTC4121 CHRG pin) and charge_current (mA)
            charging = cubesat.solar_charging
            print(f"[COMMS] Solar charging: {charging}, {cubesat.charge_current:.1f} mA")
            if charging:
                self.solar_panels_on = True
                self.equipment_check["solar_panel"] = True
                print("[COMMS] Solar panels confirmed charging.")
            else:
                self.solar_panels_on = False
                print("[COMMS] Warning: solar panels are not charging.")
        except Exception as e:
            print("[COMMS] Solar panel check error:", e)

    def _task_activate_burn_wire(self):
        """
        Fire every wire that has not fired yet in this cycle (both wires: Q-D3). If wire 2 fails
        after wire 1 worked, the retry fires only wire 2. `deployed` (and the mission clock)
        start only once all wires have fired.
        """
        self.burn_attempts += 1
        self._last_burn_time = self.uptime
        try:
            burn = BurnWire()
            for wire in self.BURN_WIRES:
                if self.burn_done[wire]:
                    continue
                burn.cubesatBurn(wire, self.BURN_DUTY, self.BURN_DURATION_S)
                self.burn_done[wire] = True
                self.burn_total += 1  # only burns that actually ran count toward the cap
            self.equipment_check["burn_wire"] = True
            self.deployed = True
            _save_deployed()
            self._start_mission_clock()
            print(f"[DEPLOY] Burn wire status: {burn.burningCheck()}")
            self._remove_task("Burn Wire")
        except Exception as e:
            print(f"[DEPLOY] Burn wire error (attempt {self.burn_attempts}):", e)
            if self.burn_attempts >= self.BURN_MAX_ATTEMPTS:
                print("[DEPLOY] Burn wire giving up.")
                self._remove_task("Burn Wire")

    def _task_antenna_watchdog(self):
        """
        Re-fire the burn wire if the antenna may not have deployed:
          - a burn raised an error and we never got a good one -> retry every BURN_RETRY_BACKOFF_S
          - a burn ran but no ground command has been heard since -> re-burn every BURN_REBURN_AFTER_S
        Stops once the ground is heard, or after BURN_MAX_TOTAL burns this boot.
        """
        if self.last_ground_contact is not None or self.burn_total >= self.BURN_MAX_TOTAL:
            return  # ground heard (antenna works) or burned enough already
        if self.deployed:
            # after a reboot there's no last burn time; count from boot
            ref = self._last_burn_time if self._last_burn_time is not None else 0.0
            wait = self.BURN_REBURN_AFTER_S
        else:
            if self._last_burn_time is None:
                return  # the first attempt is DEPLOY's job
            ref = self._last_burn_time
            wait = self.BURN_RETRY_BACKOFF_S
        if self.uptime - ref < wait:
            return
        try:
            if cubesat.battery_voltage < self.BAT_THRESH_SCIENCE:
                return  # don't burn on a weak battery; try again next check
        except Exception:
            return
        print(f"[WATCHDOG] No antenna confirmation; re-firing burn wires (wire burns so far: {self.burn_total}).")
        if self.deployed:
            # re-burn both: either half may be stuck. (Before deployment, retry only what failed.)
            self.burn_done = {w: False for w in self.BURN_WIRES}
        self._task_activate_burn_wire()

    def _remove_task(self, name):
        self.tasks = [t for t in self.tasks if t.name != name]

    def _task_init_sd_card(self):
        try:
            log_file = cubesat.new_file("/data/mission", binary=False)
            if log_file is None:  # new_file returns None if there's no SD card / can't make the dir
                raise RuntimeError("new_file returned None (no SD card?)")
            self.log_file = log_file
            self.sd_card_initialized = True
            self.equipment_check["sd_card"] = True
            print(f"[DEPLOY] SD card ready: {self.log_file}")
        except Exception as e:
            self.sd_card_initialized = False
            print("[DEPLOY] SD card init failed:", e)

    def _task_record_memory(self):
        if not self.sd_card_initialized or self.log_file is None:
            print("[DATA] SD not ready, skipping record.")
            return
        if self.latest_data is None:
            print("[DATA] No data to record.")
            return
        try:
            with open(self.log_file, "a") as f:
                f.write(f"{self.mission_time:.1f},{self.latest_data}\n")
            print(f"[DATA] Recorded at t={self.mission_time:.1f}s")
            self.latest_data = None  # don't write the same sample twice
        except Exception as e:
            print("[DATA] Record error:", e)

    def _task_beacon(self):
        """Queue a TinyGS-format beacon (Comms.build_beacon_packet) for the next TX window."""
        try:
            vbatt = cubesat.battery_voltage
        except Exception:
            vbatt = 0.0
        temp = _temperature_c()
        pkt = build_beacon_packet(
            self.state, vbatt, temp if temp is not None else 0.0, self.mission_time
        )
        if self.comms is None:
            print("[BEACON] (no comms attached)", pkt)
        elif not self.comms.push_telemetry(pkt):
            print("[BEACON] Telemetry queue full, beacon dropped.")

    # ---- transition logic ----
    # Low battery -> IDLE is handled by _task_battery_check (<= low_level_threshold).
    # Everything else lives here.
    #
    #   IDLE    -> DEPLOY          not deployed, idle for DEPLOY_AFTER_IDLE_S, battery ok, burn wire not given up
    #   IDLE    -> SCIENCE/COMMS   already deployed and battery >= BAT_THRESH_SCIENCE
    #   DEPLOY  -> SCIENCE/COMMS   burn wire done, SD ready, battery ok (sends handshake)
    #   DEPLOY  -> IDLE            battery low, or burn wire gave up
    #   SCIENCE <-> COMMS          follows _scheduled_state() (14 days science, then 7/3 slots)
    def _task_transition_check(self):
        if self.locked:
            return  # ground has locked the state
        try:
            vbatt = cubesat.battery_voltage
        except Exception as e:
            print("[TRANSITION] Can't read battery:", e)
            return
        battery_ok = vbatt >= self.BAT_THRESH_SCIENCE

        if self.state == StateID.IDLE:
            if not battery_ok:
                return
            if self.deployed:
                self.transition(self._scheduled_state())
            elif (
                self.uptime >= self.DEPLOY_AFTER_IDLE_S
                and self.burn_attempts < self.BURN_MAX_ATTEMPTS
            ):
                self.transition(StateID.DEPLOY)

        elif self.state == StateID.DEPLOY:
            if not battery_ok:
                self.transition(StateID.IDLE)
            elif self.deployed and self._check_equipment_functional():
                self._send_handshake()
                self.transition(self._scheduled_state())
            elif not self.deployed and self.burn_attempts >= self.BURN_MAX_ATTEMPTS:
                print("[TRANSITION] Burn wire failed -> IDLE")
                self.transition(StateID.IDLE)
            # otherwise: still waiting on burn wire / SD card, stay in DEPLOY

        elif self.state in (StateID.SCIENCE, StateID.COMMS):
            self.transition(self._scheduled_state())  # no-op when already in the right state

    def _check_equipment_functional(self):
        """Deploy-time check. Payload and solar panels are checked by their own states."""
        return bool(
            self.equipment_check["sd_card"] and self.equipment_check["burn_wire"]
        )

    def _scheduled_state(self):
        """SCIENCE for the first SCIENCE_ONLY_S of mission time, then COMMS_SLOTS of COMMS and SCIENCE_SLOTS of SCIENCE, repeating."""
        t = self.mission_time
        if t < self.SCIENCE_ONLY_S:
            return StateID.SCIENCE
        slot = int((t - self.SCIENCE_ONLY_S) // self.SLOT_S) % (self.COMMS_SLOTS + self.SCIENCE_SLOTS)
        return StateID.COMMS if slot < self.COMMS_SLOTS else StateID.SCIENCE

    def _send_handshake(self):
        """Tell the ground that deploy finished. Placeholder packet format."""
        msg = f"HANDSHAKE,DEPLOY_COMPLETE,t={self.mission_time:.0f}".encode()
        print("[DEPLOY]", msg)
        if self.comms:
            self.comms.push_telemetry(msg)

    def _task_init_payload(self):
        """Pings the ESP32 quantum diamond payload board and verifies link."""
        print("[PAYLOAD] Initializing link to ESP32 payload...")
        try:
            online = self.payload.ping()
            self.equipment_check["payload"] = online
            if online:
                print("[PAYLOAD] ✓ ESP32 Payload is ONLINE and responsive")
            else:
                print("[PAYLOAD] ⚠ ESP32 Payload did not respond to ping")
        except Exception as e:
            self.equipment_check["payload"] = False
            print("[PAYLOAD] Init error:", e)

    def _task_receive_data(self):
        """
        Samples science payload: photodiode current and single-point ODMR optical contrast.
        Steps frequency incrementally across 2800..2950 MHz without blocking.
        """
        try:
            # 1. Read Photodiode baseline
            pd = self.payload.read_photodiode()

            # 2. Measure single-frequency ODMR contrast at current frequency step
            target_freq = self.current_sweep_freq
            contrast = self.payload.measure_contrast(target_freq, timeout=30.0)

            # 3. Format telemetry string for SD card record
            pd_str = f"{pd:.4e}" if pd is not None else "ERR"
            contrast_str = f"{contrast:.4f}" if contrast is not None else "ERR"
            self.latest_data = (
                f"FREQ={target_freq}MHz,CONTRAST={contrast_str},PD={pd_str}A"
            )

            print(f"[SCIENCE] {self.latest_data}")

            # 4. Advance frequency step for next cycle (wrap around 2950 MHz)
            self.current_sweep_freq += 1
            if self.current_sweep_freq > 2950:
                self.current_sweep_freq = 2800
                print("[SCIENCE] Completed full 2800-2950 MHz sweep cycle!")

        except Exception as e:
            print("[SCIENCE] Receive data error:", e)

    def tick(self, now):
        """One loop iteration: update the clocks, run due tasks (highest priority first), service comms."""
        self.uptime = now - self._start_time
        self._maybe_save_mission_clock()

        task_list = self.tasks
        for task in sorted(task_list, key=lambda t: t.priority):
            if task.is_due(now):
                task.run()
                if self.tasks is not task_list:
                    break  # a task changed state; start over with the new list

        # tick comms every loop iteration (handles RX/TX scheduling)
        if self.comms:
            self.comms.update()

    def run(self):
        print("[FSM] Starting mission.")
        self._start_time = time.monotonic()
        while True:
            try:
                self.tick(time.monotonic())
                time.sleep(0.1)

            except Exception as e:
                print("[FSM] FATAL ERROR:", e)
                try:
                    cubesat.c_state_err += 1
                    cubesat.log(f"{e},{cubesat.c_state_err},{cubesat.c_boot}")
                except Exception:
                    pass
                # last resort: hard reset
                from time import sleep as _sleep

                _sleep(10)
                cubesat.micro.on_next_reset(cubesat.micro.RunMode.NORMAL)
                cubesat.micro.reset()
