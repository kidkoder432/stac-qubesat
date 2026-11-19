# FSM / PyCubed TODO

Built from the team's answers in `FSM_SPEC.md`. Update this as answers come in.

Key: `[ ]` to do, `[?]` needs a decision or answer first (blocker named), `[x]` done.
"Source" is the spec question the item comes from. Every code change also gets a test in
`pycubed/NewCode/test_fsm.py` and a spec update (ASSUMED becomes DECIDED).

## A. Ready now (answer exists)

- [x] **A1. Radio frequency** (Q-C2). **Done:** the frequency is now **437.42 MHz** (changed from 433.72 on Nov 11); `FREQ_MHZ = 437.42` in the merged Comms. Callsign is still a placeholder (see C2).
- [x] **A2. Burn both wires** (Q-D3). Each wire releases one half of the dipole. FSM uses wire 1 only. Sequence both, track success per wire, and make the retry watchdog handle either one failing. **Done:** wire 1 then wire 2, per-wire tracking, wire-2 retry fires only wire 2, watchdog re-burns both (84443bf). The burn duty/duration are still the old placeholders (C1).
- [x] **A3. Mission time counts from the burn-wire firing** (Q-M3). Before the burn there is no mission time. Persistence across reboots: see B2. **Done:** `mission_time` counts from the burn and is saved to NVM every 15 min (8-slot ring, torn-write safe); `uptime` is the boot clock (84443bf).
- [x] **A4. Replace the science/comms weighting** (Q-S6): 100% science for the first 14 days, then 70% COMMS / 30% science. Remove the 90-day linear ramp. How the split is enforced: see B1. **Done:** 14 days science, then 7 COMMS / 3 SCIENCE slots, a pure function of mission time (bb2baa4).
- [x] **A5. SCIENCE runs a full ODMR sweep** (Q-H4, Q-S1), one point per payload request, then stores `frequency:photodiode` with mission time (Q-S3). Add a "sweep complete" notion (the W plot needs all points). Contrast vs raw photodiode: payload team to confirm (C4). **Done:** sweeps one point per run, counts completed sweeps, CSV record with header (4d44fe3). Contrast vs raw is still C4. A full sweep is 151 points, about 25 min at 10 s per point, and a science slot is 30 min. Measured: one single-point contrast measurement takes about 1 s, so the 10 s period sets the sweep time, not the measurement.
- [ ] **A6. Science data downlink in COMMS** (Q-H4, Q-G1): read the stored sweep from the SD card and send it. Framing is blocked: see C3.
- [x] **A7. Uplink command scheme** (Q-H8, Q-G5, Q-C5, Q-C8): ground repeats a binary state code, a code for the state you're already in changes nothing, code 0 stops transmitting but keeps listening. Check the existing same-state behavior and the 60 s dedup window against this. Encryption: see C5. **Done:** every copy reaches the FSM, a command for the current state is a no-op, DEPLOY while in DEPLOY does not re-arm the burn, NVM written only on change (fc17ce6). Encryption is still C5.
- [x] **A8. IMU is not needed for science** (Q-S4, Q-H6). Leave IMU recording out. Keep the IMU temperature for the overheat check (Q-P2) unless something better exists. **Done:** nothing to remove: the FSM never recorded the IMU. The IMU temperature stays for the overheat check.
- [x] **A9. Remove the 90-day end-of-life weighting** (Q-M2). One good plot is success, so nothing special happens at end of life. **Done:** removed with the weighting (bb2baa4).
- [x] **A10. SD card full or corrupt** (Q-R2): overwrite old data. Deleting data after downlink needs B3 first. **Done:** oldest science file deleted only when the card is nearly full (207e140).
- [x] **A11. Radio failure recovery without ground help** (Q-R1): detect a dead radio and re-initialize it. Other failures: see B5. **Done:** radio errors counted in Comms, settings re-applied after 3, an unrecovering radio is a fault (57aedd9). Not tried on real hardware: a hung radio may not raise exceptions.
- [x] **A12. Keep the TinyGS beacon as the canonical beacon** (Q-C11). Keep the 13-byte status packet unless you decide otherwise (B4). **Done:** no change needed; the status packet now has more fields (B4).
- [x] **A13. Burn-wire driver fix.** **Done** (Ben's input, Nov 17): the ramp and the 300 s hold are gone; `BurnWire` drives a wire at `dutycycle` percent (0 to 100) for `duration` seconds, so a burn no longer blocks for minutes. The FSM now calls `setup()` before every wire and treats a `False` return as a failed burn (see H9). The duty and duration values are still C1.
- [x] **A14. Bench-only entry point** (`bench_main.py`, burn wire disabled): lets on-hardware tests start now. Not the flight `main.py` (Q-X1 still open). **Done:** `bench_main.py`, burn wire dry-run, short timings (6e5508e).

## B. Decisions for you (small, not blocked on the team)

- [x] **B1. How to enforce 70/30.** Fixed cycle, say 7x10 mins comms, 3x10 mins science **Done:** 7 COMMS then 3 SCIENCE slots of 10 min.
- [x] **B2. How mission time survives reboots.** Can this be written and read off SD card, or is it too fragile? Otherwise let's use NVM. Help me figure out the nvm stats of pycubed mainboard v5 **Done:** NVM ring (see A3). The SD card is not used for this: it is not guaranteed to be mounted at boot and a power cut mid-write can corrupt it. Size and endurance of the SAMD51 NVM are not yet checked on the board (F2).
- [x] **B3. Deleting data after downlink.** Never delete unless theres not enough room. In comms mode, continue sending the last few sweep data (if we have the baandiwdth and power for constant sending). I don't know what schedule the satellite runs uplink/downlink on (continous polling or timed intervals?) **Done:** nothing is deleted unless the card is nearly full (A10). Re-sending the last few sweeps in COMMS waits for A6 and C3. Comms alternates RX windows (50 ticks) and TX windows (up to 10 packets), `SET_CONFIG` changes both; it is a timed schedule, not continuous polling.
- [x] **B4. Keep or drop the 13-byte status packet.** Keep and add a couple more feidls for current state, payload diagnostics, etc if not present **Done:** status packet v3 (18 bytes): adds sweeps completed, sweep point, payload error count, caught exceptions. Payload RTD temperatures wait for D2.
- [x] **B5. Which other failures the FSM handles itself** (payload hang, SD fail, stuck loop). Chandrark said "up to us". We need some kind of overarching watcher that has error handling for all forms of erros and can reset the system if needed. **Done:** software watcher v1 (57aedd9). A hardware watchdog is not done: see F3.
- [x] **B6. Lock persistence and post-reboot state** (Q-C7, Q-M5): should a lock or the previous state survive a reboot? Yes **Done:** a ground lock is restored after a reboot; a locked DEPLOY is not (0e59460).
- [x] **B7. Q-C10: is the 60 s command dedup window still right** with the new command scheme? I think we can remove it. i think it might cause confusion **Done:** the dedup window is gone (fc17ce6).

## C. Blocked on answers from others

- [?] **C1. Burn duty cycle and duration** (Q-D1): burn-wire team (names in the spec).
- [?] **C2. Callsign** (Q-C2) and licensing details (Q-H11).
- [?] **C3. Science downlink framing** (Q-G3): payload and comms teams.
- [?] **C4. Contrast vs raw photodiode** (Q-S3): payload team.
- [?] **C5. AES key and whether commands are encrypted** (Q-C3). Key not made yet. Check with licensing whether encrypting commands is allowed.
- [?] **C6. What the digipeater does** (new Q-C14): packet format to repeat, who writes it. COMMS state work depends on it.
- [?] **C7. Experiment run conditions** (Q-H5): payload team (temperature settling, rails, how long to stay in a mode).
- [?] **C8. Battery thresholds** (Q-P1): read the BOM. 2S3P Panasonic 18650s span roughly 6.0 to 8.4 V. Current thresholds are 6.0 V (go to IDLE) and 8.0 V (leave IDLE), which need checking.
- [?] **C9. Overheat limit and temperature sources** (Q-P2): BOM.
- [?] **C10. Deploy wait** (Q-M1, Q-H11): clock starts when the satellite powers on. The 60 min wait is a placeholder. Launch provider rules unknown.
- [?] **C11. Power budget** (Q-H10, Q-P5): whether heaters, comms and the payload can run at once.
- [?] **C12. On-hardware test plan and acceptance criteria** (Q-V1 to V3, Q-X8).

## D. Payload firmware (yours, `payload/src`)

- [ ] **D1. Remove the serial wait before handoff**: `while (!Serial) {}` in `setup()` is for testing only; Prajwal removes it. Then test boot with no USB host.
- [ ] **D2. Thermostat in `loop()`** (Q-P4, Q-P7): time-gated check, one RTD read then one heater decision, then return. Needs the RTD-to-heater mapping, thresholds and a battery cutoff.
- [ ] **D3. Measure time per contrast request and per RTD read** (your photodiode test today). Confirm RTD reads between photodiode reads don't disturb the photodiode values.
- [ ] **D4. Raw photodiode request** if C4 says so.
- [ ] **D5. Decide whether the FSM may command heaters at all** (Q-P7 ownership). If the thermostat owns them, the FSM only reads state.

## E. Process

- [ ] **E1. Tell the Comms owner (Tyler) about the changes to `Comms.py`**: the lock bit, the dedup window, and the callback now taking `(code, lock)`.
- [ ] **E2. Keep `FSM_SPEC.md` in sync with each change.** Copy updates to the Google Doc.
- [x] **E3. Commit in small pieces.** **Done** for the work so far, grouped by topic (new BurnWire, dropping `hardware.py`, docs move, `test_payload.py` fixes, deploy script, `NewCode/lib`).

## F. New items found while working

- [ ] **F1. Comms treats fresh or corrupt NVM as STOP**, so a satellite launched with erased NVM would not transmit until commanded. Comms owner (Tyler) to confirm that is intended. `bench_main.py` forces IDLE.
- [ ] **F2. Check on the board:** `len(microcontroller.nvm)` and the SAMD51 NVM endurance, and that the single `pycubed` import works for every module (the FSM and BurnWire used to import `lib.pycubed`, Comms `pycubed`; `hardware.py` was removed).
- [ ] **F3. Hardware watchdog.** The SAMD51 watchdog timeout is short (check the limit); a burn now blocks for `duration` seconds per wire (30 s at the placeholder), which may fit inside the limit; check it. Decide with the burn wire team (R3).
- [x] **F4. Two wires block the FSM and radio** for `duration` each (about a minute at the 30 s placeholder), no longer about 12 minutes. Still depends on the real value from C1.
- [ ] **F5. Payload with `TESTING = 0` (and the serial wait removed, D1):** the `Serial.print` calls are still in the command handlers. Test with no USB host that nothing stalls.
- [ ] **F6. Sweep timing.** Measured: a single-point contrast takes about 1 s (20 photodiode reads), so the 10 s "Receive Data" period is what makes a sweep take about 25 min in a 30 min slot. **New measurement (Nov 16):** a full 151-point sweep over UART (contrast plus photodiode per point) took about 3.5 minutes, about 1.4 s per point, so the payload can do a sweep about 7 times faster than the FSM's 10 s period allows. The period is Prajwal's call (laser and microwave on-time). A sweep interrupted by COMMS resumes in the next SCIENCE slot with the same sweep number. The UART photodiode command (`P`) was also timed at about 1 s, which does not fit 50 ms per internal read. The 3.5 minute sweep (1.4 s per point, about 1 s of it contrast) suggests a photodiode read is well under 1 s once the rail is on, so the earlier 1 s probably included the 5 V rail delay. Still worth timing `P` alone with the rail already on.
- [ ] **F7. Heads-up to Tyler (E1)** now also covers: 437.42 MHz, no dedup window, a radio error counter in `CommsManager`, and the single `pycubed` import (`hardware.py` removed).

## G. Comms merge (Tyler's `tinygs` branch + the lock bit), not committed, for review

- [x] **G1.** `Comms.py` is Tyler's file (FSK uplink, LoRa downlink, `send_raw`, sync-word fix, beacon with unknown values) plus our changes: lock bit, `on_state_command(code, lock)`, no dedup in Comms, `radio_errors`, `reconfigure()`, 437.42 MHz. `DualModeRadio.py`, `tinygs_decoder.py`, `RADIO-MODES.md` and his `CHANGES-2026-09-30.md` are copied in unchanged apart from the frequency note.
- [x] **G2.** FSM: radio health calls `comms.reconfigure()`; the beacon passes `None` for a missing sensor instead of 0.
- [x] **G3.** Tests: his 17 comms tests ported (`test_comms.py`, `test_dual_mode_radio.py`) plus new ones for the merge; `test_fsm.py` uses a stand-in `DualModeRadio` so it tests the FSM <-> Comms interface.
- [ ] **G4. Tell Tyler** what changed in his file and why (the PR route you suggested): (a) dedup removed: a command equal to the stored code was dropped, so the first ground contact after boot never reached the FSM and the antenna watchdog kept re-burning; (b) lock bit and the two-argument callback; (c) `radio_errors` and `reconfigure()`; (d) 437.42 MHz, and the TinyGS station tuning must match.
- [ ] **G5. Ask Tyler:** should fresh or corrupt NVM mean STOP (silent radio)? Beacon mission time: since boot, or since the burn?
- [ ] **G6. Bench-test over the air** before relying on any of it: both directions, early and timed FSK return, TinyGS decoding of a beacon. Burn wires disconnected (Tyler's warning applies to the ArcticaNova BurnWire, not ours, which has a `__main__` guard).
- [ ] **G7. Ground side:** a ground station using `pycubed_rfm9x` must use `Comms.send_raw()` and the same `build_state_command(state, lock)`.

## H. Found on the board (Nov 12 to 16)

- [x] **H1. CircuitPython f-strings do not support `!r`.** `{e!r}` in two FSM prints raised a syntax error at import. Now `{repr(e)}`. Other conversions (`!s`, `!a`) and f-string `=` are not used anywhere.
- [x] **H2. SD card:** `[Errno 19] No such device` at startup was the card not being detected (reseat, FAT32, 32 GB or less); the FSM already retries and prints `[SD] Init failed`.
- [x] **H3. `test_payload.py` sweep logging.** The sweep log wrote only the header: the row line used `format()`, which CircuitPython does not have, and the surrounding `except` hid the error. Fixed with an f-string; write errors and the SD-unavailable reason are now printed.
- [x] **H4. `test_payload.py` memory.** A 151-point sweep hit `memory allocation failed, allocating 1024 bytes` (growing lists on a small, fragmented heap). The sweep now preallocates its rows, drops the latency list and calls `gc.collect()` every 10 points. Precompiling the test to `.mpy` would free more heap.
- [x] **H5. Payload console sweep logging to the SD card works on the board** (Prajwal tested after H3 and H4).
- [ ] **H6. The FSM writing science data to the SD card is not tested yet.** Data rows are only written in SCIENCE, so first confirm the FSM reaches SCIENCE (battery, burn wire marked done, no saved lock).

- [x] **H7. Measuring and recording are one task.** The separate "Record to Memory" task is gone: `_task_receive_data` writes each point to the SD card as soon as it is measured (`_record_point`), so a sample can no longer be overwritten before it is written. The period of that one task is still the open question in F6 (a whole sweep per run, or a short period so the loop keeps servicing comms and the battery check between points).

- [x] **H8. Tools for working without hardware.** `sim/` runs the real FSM and Comms against a fake world (virtual clock, synthetic ODMR spectrum, fake radio and ground station, SD card and fault injection): `python3 sim/cli.py` (prints events as they happen during `run` and `until`), scenario tests in `python3 sim/test_sim.py`; it now runs the real `BurnWire.py` over fake pwmio/board modules; see `sim/README.md` for what it does and does not model. `python3 tools/check_circuitpython.py --download` compiles every board file with the CircuitPython 8.2.10 compiler and catches syntax the board rejects (`!r`, an f-string inside an f-string expression, two f-strings next to each other; join those with `+`).

- [x] **H9. The FSM ignored the new BurnWire contract.** The updated `BurnWire` needs `setup()` before each burn and returns `False` (no exception) when nothing was driven. The FSM did neither: it would have marked both wires done, set `deployed`, saved it to NVM and started the mission clock with no burn having happened. Fixed (`setup()` per wire, `False` raises); `bench_main._DryBurn`, `test_fsm.py` and the simulator now follow the same contract, and a test pins the case.
- [ ] **H10. A burn status string is misleading.** After a successful burn `burningCheck()` returns "Burn wire not ready to fire. Call setup() first." (the ready flag is cleared after each burn), and the FSM prints it as `[DEPLOY] Burn wire status`. Cosmetic; for the BurnWire owner.
- [ ] **H11. The SD card is never remounted while running.** `lib/pycubed.py` mounts `/sd` once in `__init__`. A card missing at boot, or pulled and put back later, stays unusable until the next boot; `new_file()` returns `None` or writes fail, and the FSM only retries `new_file()` (the simulator reproduces this). Decide what the FSM should do when SD writes keep failing (for example, a controlled reboot after N failures) and whether that is acceptable in flight. This is a design call; not changed.

- [x] **H12. One science file per sweep.** The FSM only created a science file when DEPLOY started or after a reboot, so a run produced one ever-growing file (about 260 KB a day, one file for 14 days in the simulator) that nothing could send or delete. `_record_point` now starts a new file, with its own header, when a point belongs to a new sweep (`SWEEPS_PER_FILE = 1`, change the constant for several sweeps per file). A reboot still starts a new file, and a half sweep stays in the old one. Not measured on the board: `cubesat.new_file()` scans file numbers from 0 with `stat()`, so with hundreds of files each new file may block for a noticeable time.

- [ ] **H13. Re-burn policy is undecided.** The antenna watchdog re-fires both wires every 12 h (up to 20 burns per boot) while no uplink command has been heard; with no ground contact that is 10 burns per wire in 14 days. Prajwal has not chosen a policy yet (options discussed: never re-burn after a good burn; re-burn rarely with a small cap; keep as is). Needs the burn team's view on whether a second burn can help at all, and how long the ground station may take to make first contact. Not changed.
- [ ] **H14. Satellite-to-ground protocol and a simulated ground station.** Every open question, grouped by owner, is in `docs/OPEN_QUESTIONS.md`. Prajwal's draft protocol is `docs/COMMS_SPEC.md` (open questions P1a to P30, sorted by owner, for him and Tyler), written from `docs/TINYGS_AND_RADIO_CONSTRAINTS.md`; the simulator's ground station then implements it. Findings in that document: TinyGS now wants a Kaitai `.ksy` decoder sent by email (our `tinygs_decoder.py` still says Telegram bot); TinyGS forwards only publicly documented payloads; no documented packet-size limit or uplink; our 18-byte status packet and any science packet need their own `.ksy`; SCIENCE sends no TinyGS beacon.

- [x] **H15. Tyler's `tinygs` branch, new since the merge** (checked Nov 18, `og-qubesat`, commits 6c7cf1a and 0c7e9b1): (a) `6c7cf1a` fixes a **CircuitPython crash in the beacon** (`str.ljust` does not exist there) and rounds the battery value; ported into our `Comms.py` with two tests (the compile check and the simulator cannot see this kind of runtime error); (b) `0c7e9b1` adds `groundstation/` (uplink only, see H14 and `docs/OPEN_QUESTIONS.md`). Not copied into this repo: Tyler can open a PR for it.
- [ ] **H16. Ground-side changes needed** (for Tyler): frequency 433.0 to 437.42 MHz, a lock option for state commands, and the missing receive side (downlink decoder, storage, handshake reply, acknowledgements).

## Suggested order

1. B1 to B7 (your decisions), D3 (your measurements today).
2. A1, A2, A3, A8, A9, A13 (small and independent).
3. A4, A5, A7.
4. A14 so the on-hardware tests can start.
5. A6, A10, A11, then the C items as answers arrive.
