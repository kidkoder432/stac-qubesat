import time

from BurnWire import BurnWire
from PayloadUART import PayloadUART
from PowerLevel import PowerLevel
from StateCodeGenerator import StateCodec, StateID
from Task import Task

from lib.pycubed import cubesat


class TemperatureCheck:
    def is_safe(self):
        try:
            temp = getattr(cubesat, "temperature_cpu", 25.0)
            return temp < 60.0
        except Exception:
            return True


class QubeSatFSM:
    high_level_threshold = 8.4  # this is enforced by pycube itself
    low_level_threshold = (
        6.0  # when it reaches this low level -> switch to idle/charging state
    )

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
        self.missionTime = 0.0  # how much time has passed so far, 0 at the beginning
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
            "burn_wire": (30 * 60),
            "receive_data": 10,
            "record_memory": 10,
            "init_payload": (30 * 60),
        }

        # boolean values to check different stages of mission
        self.experiment_started = (
            False  # this is True if experiment has started/isrunning and false if not
        )
        self.sd_card_initalized = (
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

        # making a dictionary to be able to call each state
        # should execute all of the actions in each state
        self.tasks = self._build_tasks_for_state(self.state)

    def _build_tasks_for_state(self, state: StateID):
        builders = {
            StateID.IDLE: self.build_idle_tasks,
            StateID.DEPLOY: self.build_deploy_tasks,
            StateID.SCIENCE: self.build_science_tasks,
            StateID.COMMS: self.build_comms_tasks,
        }
        return builders[state]()

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
        ]
        return tasks

    # initalize sd card -> activate burn wire -> check battery -> beacon -> transition
    def build_deploy_tasks(self):
        tasks = [
            Task(
                "SD_Card",
                1,
                self.periods["sd_card"],
                schedule_later=False,
                func=self._task_init_sd_card,
            ),
            Task(
                "Burn Wire",
                2,
                self.periods["burn_wire"],
                schedule_later=True,
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
        ]
        return tasks

    def build_science_tasks(self):
        tasks = [
            Task(
                "Initialize Payload",
                1,
                self.periods["init_payload"],
                schedule_later=False,
                func=self._task_init_payload,
            ),
            Task(
                "Receive Data",
                2,
                self.periods["receive_data"],
                schedule_later=True,
                func=self._task_receive_data,
            ),
            Task(
                "Record to Memory",
                3,
                self.periods["record_memory"],
                schedule_later=True,
                func=self._task_record_memory,
            ),
            Task(
                "Transition Check",
                4,
                self.periods["transition"],
                schedule_later=True,
                func=self._task_transition_check,
            ),
        ]
        return tasks

    """
        this state is entered when battery is below the low_power_threshold

    """

    # going to start defining the functions that are ran for each action in the tasks

    def transition(self, new_state: StateID):
        if new_state == self.state:
            return  # already here, do nothing
        self.state = new_state
        self.current_code = StateCodec.encode(
            new_state
        )  # adding this so that when state changes -> so does current code
        self.tasks = self._build_tasks_for_state(new_state)

    def _task_battery_check(self):
        try:
            vbatt = cubesat.battery_voltage
            print(f"[BATTERY] Voltage: {vbatt:.2f} V")

            if not self.temperature.is_safe():
                print("[BATTERY] Temperature unsafe — going idle.")
                self.transition(StateID.IDLE)
                return

            if vbatt <= self.low_level_threshold:
                print("[BATTERY] Low battery — going idle.")
                self.transition(StateID.IDLE)
        except Exception as e:
            print("[BATTERY] Check error:", e)

    def halt_transmission(self):
        # stop beacon and any outgoing radio tasks
        self.tasks = [t for t in self.tasks if t.name != "Beacon"]

    # lowkey shouldnt it always be turned on?
    # okie need to turn on solar panel
    # i think solar input is enabled by hardware and not software, so ill just check current for now
    def _task_enable_solar_panels(self):
        try:
            charging_current = cubesat.charging_current
            print(f"[COMMS] Charge current: {charging_current:.3f} A")
            if charging_current > 0:
                self.solar_panels_on = True
                self.equipment_check["solar_panel"] = True
                print("[COMMS] Solar panels confirmed charging.")
            else:
                self.solar_panels_on = False
                print("[COMMS] Warning: No charge current detected.")
        except Exception as e:
            print("[COMMS] Solar panel check error:", e)

    # burn wire clAss is already made -> just need to call it
    def _task_activate_burn_wire(self):
        try:
            burn = BurnWire()
            burn.cubesatBurn("1", 0.25, 30)  # burn wire 1, 25% duty cycle, 30 seconds
            self.solar_panels_on = True  # burn wire deploys panels
            self.equipment_check["burn_wire"] = True
            print(f"[DEPLOY] Burn wire status: {burn.burningCheck()}")
        except Exception as e:
            print("[DEPLOY] Burn wire error:", e)

    def _task_init_sd_card(self):
        try:
            self.log_file = cubesat.new_file("/data/mission", binary=False)
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
        except Exception as e:
            print("[DATA] Record error:", e)

    def _task_beacon(self):
        pass

    def _task_transition_check(self):
        pass

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

    def run(self):
        print("[FSM] Starting mission.")
        while True:
            try:
                now = time.monotonic()
                self.mission_time = now

                # run any tasks that are due
                for task in self.tasks:
                    if task.is_due(now):
                        task.run()

                # tick comms every loop iteration (handles RX/TX scheduling)
                if self.comms:
                    self.comms.update()

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
