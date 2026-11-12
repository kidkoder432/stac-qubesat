# FSM / PyCubed TODO

Built from the team's answers in `FSM_SPEC.md`. Update this as answers come in.

Key: `[ ]` to do, `[?]` needs a decision or answer first (blocker named), `[x]` done.
"Source" is the spec question the item comes from. Every code change also gets a test in
`pycubed/NewCode/test_fsm.py` and a spec update (ASSUMED becomes DECIDED).

## A. Ready now (answer exists)

- [x] **A1. Radio frequency 433.720 MHz** (Q-C2). `Comms.py` currently has 433.0. Callsign is still a placeholder (see C2). **Done:** `FREQ_MHZ = 433.72` (commit fc17ce6).
- [x] **A2. Burn both wires** (Q-D3). Each wire releases one half of the dipole. FSM uses wire 1 only. Sequence both, track success per wire, and make the retry watchdog handle either one failing. **Done:** wire 1 then wire 2, per-wire tracking, wire-2 retry fires only wire 2, watchdog re-burns both (84443bf). The burn duty/duration are still the old placeholders (C1).
- [x] **A3. Mission time counts from the burn-wire firing** (Q-M3). Before the burn there is no mission time. Persistence across reboots: see B2. **Done:** `mission_time` counts from the burn and is saved to NVM every 15 min (8-slot ring, torn-write safe); `uptime` is the boot clock (84443bf).
- [x] **A4. Replace the science/comms weighting** (Q-S6): 100% science for the first 14 days, then 70% COMMS / 30% science. Remove the 90-day linear ramp. How the split is enforced: see B1. **Done:** 14 days science, then 7 COMMS / 3 SCIENCE slots, a pure function of mission time (bb2baa4).
- [x] **A5. SCIENCE runs a full ODMR sweep** (Q-H4, Q-S1), one point per payload request, then stores `frequency:photodiode` with mission time (Q-S3). Add a "sweep complete" notion (the W plot needs all points). Contrast vs raw photodiode: payload team to confirm (C4). **Done:** sweeps one point per run, counts completed sweeps, CSV record with header (4d44fe3). Contrast vs raw is still C4. A full sweep is 151 points, about 25 min at 10 s per point, and a science slot is 30 min.
- [ ] **A6. Science data downlink in COMMS** (Q-H4, Q-G1): read the stored sweep from the SD card and send it. Framing is blocked: see C3.
- [x] **A7. Uplink command scheme** (Q-H8, Q-G5, Q-C5, Q-C8): ground repeats a binary state code, a code for the state you're already in changes nothing, code 0 stops transmitting but keeps listening. Check the existing same-state behavior and the 60 s dedup window against this. Encryption: see C5. **Done:** every copy reaches the FSM, a command for the current state is a no-op, DEPLOY while in DEPLOY does not re-arm the burn, NVM written only on change (fc17ce6). Encryption is still C5.
- [x] **A8. IMU is not needed for science** (Q-S4, Q-H6). Leave IMU recording out. Keep the IMU temperature for the overheat check (Q-P2) unless something better exists. **Done:** nothing to remove: the FSM never recorded the IMU. The IMU temperature stays for the overheat check.
- [x] **A9. Remove the 90-day end-of-life weighting** (Q-M2). One good plot is success, so nothing special happens at end of life. **Done:** removed with the weighting (bb2baa4).
- [x] **A10. SD card full or corrupt** (Q-R2): overwrite old data. Deleting data after downlink needs B3 first. **Done:** oldest science file deleted only when the card is nearly full (207e140).
- [x] **A11. Radio failure recovery without ground help** (Q-R1): detect a dead radio and re-initialize it. Other failures: see B5. **Done:** radio errors counted in Comms, settings re-applied after 3, an unrecovering radio is a fault (57aedd9). Not tried on real hardware: a hung radio may not raise exceptions.
- [x] **A12. Keep the TinyGS beacon as the canonical beacon** (Q-C11). Keep the 13-byte status packet unless you decide otherwise (B4). **Done:** no change needed; the status packet now has more fields (B4).
- [ ] **A13. Burn-wire driver fix** (Q-D1 is the blocker for the numbers, but the structure can change now): `duty cycle` and `duration` must mean what the FSM thinks they mean, and a burn must not block the FSM and radio for about 6 minutes. Two wires doubles that time.
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

- [ ] **D1. Fix the possible boot hang**: `while (!Serial) {}` in `setup()`. Test with no USB host first.
- [ ] **D2. Thermostat in `loop()`** (Q-P4, Q-P7): time-gated check, one RTD read then one heater decision, then return. Needs the RTD-to-heater mapping, thresholds and a battery cutoff.
- [ ] **D3. Measure time per contrast request and per RTD read** (your photodiode test today). Confirm RTD reads between photodiode reads don't disturb the photodiode values.
- [ ] **D4. Raw photodiode request** if C4 says so.
- [ ] **D5. Decide whether the FSM may command heaters at all** (Q-P7 ownership). If the thermostat owns them, the FSM only reads state.

## E. Process

- [ ] **E1. Tell the Comms owner (Tyler) about the changes to `Comms.py`**: the lock bit, the dedup window, and the callback now taking `(code, lock)`.
- [ ] **E2. Keep `FSM_SPEC.md` in sync with each change.** Copy updates to the Google Doc.
- [ ] **E3. Commit in small pieces**, one per item above.

## F. New items found while working

- [ ] **F1. Comms treats fresh or corrupt NVM as STOP**, so a satellite launched with erased NVM would not transmit until commanded. Comms owner (Tyler) to confirm that is intended. `bench_main.py` forces IDLE.
- [ ] **F2. Check on the board:** `len(microcontroller.nvm)` and the SAMD51 NVM endurance, and that the shared `hardware.py` import works (the FSM and BurnWire used `lib.pycubed`, Comms used `pycubed`).
- [ ] **F3. Hardware watchdog.** The SAMD51 watchdog timeout is short (check the limit); a burn blocks for about 6 minutes per wire, so `BurnWire` would have to feed it. Decide with the burn wire team (R3).
- [ ] **F4. Two wires block the FSM and radio for about 12 minutes.** Waits on C1 and the `BurnWire` structure (A13).
- [ ] **F5. Payload with `TESTING = 0`:** the `Serial.print` calls are still in the command handlers. Test with no USB host that nothing stalls.
- [ ] **F6. Sweep timing.** One point per 10 s makes a 25-minute sweep in a 30-minute slot. D3 (your measurements) decides the period. A sweep interrupted by COMMS resumes in the next SCIENCE slot with the same sweep number.
- [ ] **F7. Heads-up to Tyler (E1)** now also covers: 433.72 MHz, no dedup window, a radio error counter in `CommsManager`, and the shared `hardware.py` import.

## Suggested order

1. B1 to B7 (your decisions), D3 (your measurements today).
2. A1, A2, A3, A8, A9, A13 (small and independent).
3. A4, A5, A7.
4. A14 so the on-hardware tests can start.
5. A6, A10, A11, then the C items as answers arrive.
