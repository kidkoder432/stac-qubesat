# FSM / PyCubed TODO

Built from the team's answers in `FSM_SPEC.md`. Update this as answers come in.

Key: `[ ]` to do, `[?]` needs a decision or answer first (blocker named), `[x]` done.
"Source" is the spec question the item comes from. Every code change also gets a test in
`pycubed/NewCode/test_fsm.py` and a spec update (ASSUMED becomes DECIDED).

## A. Ready now (answer exists)

- [ ] **A1. Radio frequency 433.720 MHz** (Q-C2). `Comms.py` currently has 433.0. Callsign is still a placeholder (see C2).
- [ ] **A2. Burn both wires** (Q-D3). Each wire releases one half of the dipole. FSM uses wire 1 only. Sequence both, track success per wire, and make the retry watchdog handle either one failing.
- [ ] **A3. Mission time counts from the burn-wire firing** (Q-M3). Before the burn there is no mission time. Persistence across reboots: see B2.
- [ ] **A4. Replace the science/comms weighting** (Q-S6): 100% science for the first 14 days, then 70% COMMS / 30% science. Remove the 90-day linear ramp. How the split is enforced: see B1.
- [ ] **A5. SCIENCE runs a full ODMR sweep** (Q-H4, Q-S1), one point per payload request, then stores `frequency:photodiode` with mission time (Q-S3). Add a "sweep complete" notion (the W plot needs all points). Contrast vs raw photodiode: payload team to confirm (C4).
- [ ] **A6. Science data downlink in COMMS** (Q-H4, Q-G1): read the stored sweep from the SD card and send it. Framing is blocked: see C3.
- [ ] **A7. Uplink command scheme** (Q-H8, Q-G5, Q-C5, Q-C8): ground repeats a binary state code, a code for the state you're already in changes nothing, code 0 stops transmitting but keeps listening. Check the existing same-state behavior and the 60 s dedup window against this. Encryption: see C5.
- [ ] **A8. IMU is not needed for science** (Q-S4, Q-H6). Leave IMU recording out. Keep the IMU temperature for the overheat check (Q-P2) unless something better exists.
- [ ] **A9. Remove the 90-day end-of-life weighting** (Q-M2). One good plot is success, so nothing special happens at end of life.
- [ ] **A10. SD card full or corrupt** (Q-R2): overwrite old data. Deleting data after downlink needs B3 first.
- [ ] **A11. Radio failure recovery without ground help** (Q-R1): detect a dead radio and re-initialize it. Other failures: see B5.
- [ ] **A12. Keep the TinyGS beacon as the canonical beacon** (Q-C11). Keep the 13-byte status packet unless you decide otherwise (B4).
- [ ] **A13. Burn-wire driver fix** (Q-D1 is the blocker for the numbers, but the structure can change now): `duty cycle` and `duration` must mean what the FSM thinks they mean, and a burn must not block the FSM and radio for about 6 minutes. Two wires doubles that time.
- [ ] **A14. Bench-only entry point** (`bench_main.py`, burn wire disabled): lets on-hardware tests start now. Not the flight `main.py` (Q-X1 still open).

## B. Decisions for you (small, not blocked on the team)

- [ ] **B1. How to enforce 70/30.** Fixed cycle, say 7x10 mins comms, 3x10 mins science
- [ ] **B2. How mission time survives reboots.** Can this be written and read off SD card, or is it too fragile? Otherwise let's use NVM. Help me figure out the nvm stats of pycubed mainboard v5
- [ ] **B3. Deleting data after downlink.** Never delete unless theres not enough room. In comms mode, continue sending the last few sweep data (if we have the baandiwdth and power for constant sending). I don't know what schedule the satellite runs uplink/downlink on (continous polling or timed intervals?)
- [ ] **B4. Keep or drop the 13-byte status packet.** Keep and add a couple more feidls for current state, payload diagnostics, etc if not present
- [ ] **B5. Which other failures the FSM handles itself** (payload hang, SD fail, stuck loop). Chandrark said "up to us". We need some kind of overarching watcher that has error handling for all forms of erros and can reset the system if needed.
- [ ] **B6. Lock persistence and post-reboot state** (Q-C7, Q-M5): should a lock or the previous state survive a reboot? Yes
- [ ] **B7. Q-C10: is the 60 s command dedup window still right** with the new command scheme? I think we can remove it. i think it might cause confusion

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

## Suggested order

1. B1 to B7 (your decisions), D3 (your measurements today).
2. A1, A2, A3, A8, A9, A13 (small and independent).
3. A4, A5, A7.
4. A14 so the on-hardware tests can start.
5. A6, A10, A11, then the C items as answers arrive.
