# Open questions, by owner

**Date:** 2026-11-17. One place for every question that is still open, grouped by who has to answer it. It is built from: the FSM spec's part 7 (`Q-` numbers), the TODO list (`C`, `D`, `F`, `G`, `H` items), the comms spec (`P` numbers, `docs/COMMS_SPEC.md`) and the TinyGS notes (`docs/TINYGS_AND_RADIO_CONSTRAINTS.md`). It adds no answers and picks no values.

**What counts as open.** A question is listed if its answer cell in the FSM spec is empty, only names people (still waiting on them), says *idk / unsure / not decided / in progress*, or answers only part of it. Questions that have a real answer are not repeated here (see the FSM spec part 7 and 7.4). Where the spec's answer cell names a person or team, that owner is used as written. Everywhere else the owner is **my suggestion from the person's role**, and each group's note says which is which. Please correct any that are wrong.

**Where the detail is.** The comms spec items (`P…`) are only named here; the full question, context and who else must help are in `docs/COMMS_SPEC.md`, section 9.

| Owner | Open items |
| :-- | :-- |
| Chandrark Muddana | 14 |
| Tyler Minjung Lee | 28 |
| Burn wire team: Ben Woo, Gabriel Johann Moeller, Rohak Singh Gulia, Keen Haidang Nguyen | 4 |
| Payload and experiment team: Vedant Birla, Alexander Ma, Leo Li | 6 |
| Prajwal Agrawal | 31 |

## Chandrark Muddana (team lead; licence, launch, test plan)

Named in the spec only in general terms (team lead; Q-H15 and Q-X9). Every item below is a suggestion based on the team-lead, licence and launch role.

| ID | Question | Status | Where |
| :-- | :-- | :-- | :-- |
| Q-C2 | The real **callsign** (the frequency, 437.42 MHz, is answered). The code still has the placeholder `"STAC  "`. | No answer ("idk") | FSM spec 7.0 |
| Q-C3 | The real **AES key**, how it is stored and shared. Still all zeros in the code. (With Tyler.) | Not made yet | FSM spec 7.0, TODO C5 |
| C5 / P2 | Is **encrypting the uplink commands allowed** under our licence, and is each new uplink message (handshake reply, ack, state) to be encrypted? (The US rule 47 CFR 97.211(b) appears to allow it; which administration licenses us is not known.) | No answer | TODO C5; COMMS_SPEC P2; TINYGS doc section 6 |
| Q-C13 | The IARU **"frequency for our own"** and the **"Sean Cooman protocol"** in the original PDF. Also the **IARU coordination** status of 437.42 MHz. | Partly answered ("the IARU frequency, idk what the protocol is") | FSM spec 7.2; TINYGS doc section 6 |
| Q-C1 / C6 | What exactly the **digipeater** must do (the IARU requirement): which packets, what format, who writes it. (With Tyler.) | Partly answered ("IARU required digipeater") | FSM spec 7.2, TODO C6 |
| Q-H11 | **Launch provider and regulatory requirements**: deployment switch rules, wait-time rules. | No answer ("we need to figure it out") | FSM spec 7.2 |
| Q-M1 | How long the **deploy wait** is (the trigger is answered: power-on after the inhibit switches). The code uses a 60 minute placeholder. | Partly answered | FSM spec 7.2, TODO C10 |
| Q-H3 | The intended **operating loop**: the day schedule, and the battery level at which the satellite should charge. (The answer says "idk the day by day schedule".) | Partly answered | FSM spec 7.0 |
| Q-V1 / V2 / V3 / X8 | The **on-hardware test plan**, whether the full loop can be tested before flight, how long the FSM must run without a reset to count as stable, and the **acceptance criteria** for "flight ready". (With Prajwal.) | No answer (X8: in progress) | FSM spec 7.1, 7.2, TODO C12 |
| Q-H13 | What **hardware exists and what state it is in** (payload hardware complete; the rest unsure; is there a flatsat?). | Partly answered ("UNSURE") | FSM spec 7.4 |
| Q-H10 / C9 / C11 | The **system budgets**: orbit-average power, thermal limits, the overheat limit, whether heaters, comms and payload can run at once. The answer points at the BOM; no numbers have been extracted. | No answer ("check the BOM") | FSM spec 7.2, TODO C9, C11 |
| Q-M4 | When **ground passes** happen and how many per day (a rough estimate of 4 per day, "need to do the math"). | Partly answered | FSM spec 7.2 |
| Q-P1 / C8 | Check the **battery thresholds** against the Panasonic 18650B 2S3P pack (the code uses 6.0 V to IDLE, 8.0 V to leave IDLE). Needs someone to read the BOM. | Partly answered | FSM spec 7.0, TODO C8 |
| P2 | is each uplink message encrypted | Open (details in the comms spec) | COMMS_SPEC |

## Tyler Minjung Lee (Comms code, TinyGS decoder, ground-station software)

Named in the spec for Q-G2 (ground-station software). The other items are suggestions from his ownership of Comms.

| ID | Question | Status | Where |
| :-- | :-- | :-- | :-- |
| Q-G2 | The **ground-station software**. Update (Nov 18): the **uplink half exists** in his `groundstation/` (PlutoSky transmitter, command builders, FSK modulator). Still unbuilt: **receiving and decoding** the downlink, storing data, the handshake reply and acknowledgements. | Partly done | FSM spec 7.1; og-qubesat `tinygs` branch |
| Q-G3 / C3 | How **science data is framed** for the radio (packet size, splitting over packets, acknowledgements). The answer says it should be decided between the payload and comms teams. (With Prajwal and the payload team.) | No answer; Prajwal's draft is `docs/COMMS_SPEC.md` | FSM spec 7.1, TODO C3 |
| Q-G5 / P29 | **Replay protection** for uplink commands (none today; AES-ECB, no counter). The answer only covers the repeated-code scheme. | Partly answered | FSM spec 7.1; COMMS_SPEC P29 |
| Q-C3 | Generate the **AES key** (with Chandrark; see above). | Not made yet | FSM spec 7.0 |
| (new) | **Ground station is still on 433.0 MHz** (`pluto_uplink.py` `FREQ_HZ`, `fsk.py`, README); the team's answer is 437.42 MHz, which our Comms uses. The uplink would miss the satellite as it stands. Its README also says transmitting on 433 MHz needs a licensed amateur operator. | Found Nov 18 | `groundstation/` in `og-qubesat` |
| (new) | **The ground command builder has no lock bit.** `build_state_command(state)` can only send an unlocked state (bit 7 = 0), and `pluto_uplink.py state` has no `--lock`. The satellite already supports lock. | Found Nov 18 | `groundstation/commands.py` |
| G4 | Review of the **changes to his `Comms.py`**: dedup removed, lock bit, two-argument callback, `radio_errors` and `reconfigure()`, 437.42 MHz. He has been told he can open PRs on the team repo for changes he wants, but TODO G4 (telling him about ours) is still unchecked. | Not sent yet | TODO G4, E1 |
| G5 / F1 | Should **fresh or corrupt NVM mean STOP** (silent radio)? Is the beacon's **mission time since boot** (his doc) or **since the burn** (the FSM)? | Not asked yet | TODO G5, F1 |
| G6 | **Over-the-air test**: both directions, early and timed FSK return, TinyGS decoding of a beacon, with the burn wires disconnected. | Not done | TODO G6 |
| G7 | The **ground side must use `Comms.send_raw()`** and `build_state_command(state, lock)`. | For the ground software | TODO G7 |
| TinyGS | The **TinyGS submission**: a `.ksy` decoder per packet type, the validated test reception from `STAC1`, photos and descriptions, sent by email to missioncontrol@tinygs.com. `tinygs_decoder.py` still says to use a Telegram bot. Also: does the T3 433 MHz board receive at 437.42 MHz? | Not started | TINYGS doc sections 2 and 8 |
| P1a | header values | Open (details in the comms spec) | COMMS_SPEC |
| P1b | does every packet get a type byte | Open (details in the comms spec) | COMMS_SPEC |
| P1c | how long is the header | Open (details in the comms spec) | COMMS_SPEC |
| P3a | what does the footer contain | Open (details in the comms spec) | COMMS_SPEC |
| P3b | does a TinyGS decoder verify the footer | Open (details in the comms spec) | COMMS_SPEC |
| P3c | size cost | Open (details in the comms spec) | COMMS_SPEC |
| P4 | byte order and units | Open (details in the comms spec) | COMMS_SPEC |
| P5 | reserve a way to evolve | Open (details in the comms spec) | COMMS_SPEC |
| P11 | do these keep their current first bytes | Open (details in the comms spec) | COMMS_SPEC |
| P14 | which queue and which first byte carries science | Open (details in the comms spec) | COMMS_SPEC |
| P17 | does a packet carry its own CRC or is the radio's CRC enough | Open (details in the comms spec) | COMMS_SPEC |
| P19 | whose count | Open (details in the comms spec) | COMMS_SPEC |
| P23 | does `0xBC` replace `0x01`, or is `0x01` kept | Open (details in the comms spec) | COMMS_SPEC |
| P27 | the amateur (`0xA0`) digipeater path | Open (details in the comms spec) | COMMS_SPEC |
| P28 | `SET_CONFIG` and `SET_MODULATION` | Open (details in the comms spec) | COMMS_SPEC |
| P29 | replay protection | Open (details in the comms spec) | COMMS_SPEC |
| P30 | does Tyler own the ground-station software, and does he accept that | Open (details in the comms spec) | COMMS_SPEC |

## Burn wire team: Ben Woo, Gabriel Johann Moeller, Rohak Singh Gulia, Keen Haidang Nguyen

Ben changed the driver (ramp and hold removed, a `duration` parameter added). The values below are still unanswered.

| ID | Question | Status | Where |
| :-- | :-- | :-- | :-- |
| Q-D1 | The **duty cycle and duration** that release the antenna for our nichrome and battery. The FSM passes the placeholder 0.25 (percent) and 30 s. | Assigned, waiting | FSM spec 7.0, TODO C1 |
| Q-D5 / H13 | The **retry policy**: how many burns are acceptable, thermal limits, whether to re-burn at all when no ground contact is made. The watchdog re-fires every 12 h up to 20 burns per boot. (With Prajwal.) | No answer | FSM spec 7.2, TODO H13 |
| Q-D7 / R3 | Does a **hardware watchdog** reset during a blocking 30 s burn, and may `BurnWire` feed it? | No answer ("don't know anything about the watchdogs") | FSM spec 7.2, TODO F3 |
| H10 | `burningCheck()` returns "not ready, call setup() first" after a successful burn; a bad wire number raises a `NameError`; duty or duration 0 returns True without burning. Intended? | Not told yet | TODO H10 |

## Payload and experiment team: Vedant Birla, Alexander Ma, Leo Li

The spec's answer cells name these three for Q-H5 and Q-H7; for the other rows they are a suggestion.

| ID | Question | Status | Where |
| :-- | :-- | :-- | :-- |
| Q-H5 | What must be true for the **experiment to work** (temperature stability and settling time, laser and rail power, magnetic environment, orientation). | Assigned, waiting | FSM spec 7.0, TODO C7 |
| Q-H7 | **How much science is enough**: how many runs or hours of data. | Assigned, waiting | FSM spec 7.2 |
| Q-S1 | Is one science run **a full sweep**, and what counts as a good result? The FSM's one-point-every-10-s sweep is an assumption copied from an old repository. | Assumption, needs sign-off | FSM spec 7.2 |
| Q-S3 / C4 | **Contrast vs raw photodiode**: which is recorded (the FSM records both), the units of the photodiode value, what an error point looks like. | Partly answered ("idk what contrast means") | FSM spec 7.2, TODO C4 |
| Q-P5 / C11 | **Power per state** for the payload 5 V and 10 V rails, and what may run together. | Unsure | FSM spec 7.2 |
| Q-P7 / D2 / D5 | The **RTD to heater mapping**, thresholds and battery cutoff for the thermostat, and whether the **FSM may command heaters at all** (or only the payload thermostat does). | No answer | FSM spec 7.2, TODO D2, D5 |

## Prajwal Agrawal (FSM, payload UART and firmware, this spec)

The `Q-P3` to `Q-X7` rows are listed in the spec under "FSM decisions (Prajwal)"; the rest are his as owner of the FSM, the payload UART and this spec.

| ID | Question | Status | Where |
| :-- | :-- | :-- | :-- |
| Q-P3 | Should a **low battery override a ground lock** on the state? (The code already clears the lock for safety; the question has no recorded answer.) | Awaiting his decision | FSM spec 7.3 |
| Q-S5 | What happens when the **payload does not answer**? (The code records an `ERR` row and counts errors.) | Awaiting his decision | FSM spec 7.3 |
| Q-X1 | How the FSM **starts on the board**: which file runs at boot, and what else belongs in `main.py` / `code.py`. Only the bench entry point exists. | Unsure | FSM spec 7.3 |
| Q-X3 | Which code is the **source of truth**, `pycubed/NewCode` or the board? (Chandrark said to trust GitHub over the drive.) | Not recorded | FSM spec 7.3 |
| Q-X4 | Which **task periods** to use: the spec's section 3 or the PDF sample code's. | Awaiting his decision | FSM spec 7.3 |
| Q-X6 | Who **allocates NVM bytes** (board library 0 to 16, Comms 20 to 26, FSM 19)? Also: the SAMD51 NVM size and endurance are unchecked. | Awaiting his decision | FSM spec 7.3, TODO F2 |
| Q-X7 | Is the crash recovery (wait 10 s, then reset; crash-loop guard) the desired behaviour? | Awaiting his decision | FSM spec 7.3 |
| Q-S7 | What **"equipment functional"** means and which self-tests count. | Open ("we can selftest???") | FSM spec 7.2 |
| Q-X2 | The **review rules** for each file (who must review changes to Comms, BurnWire, the payload UART). | Partly answered | FSM spec 7.2 |
| Q-R3 / F3 | Whether to build a **hardware watchdog** (a nice-to-have, no work done). | Not decided | FSM spec 7.1, TODO F3 |
| F6 | The **period of the science task**: 10 s makes a sweep take about 29 minutes; a sweep took 3.5 minutes over UART. His call (laser and microwave on-time). | His decision | TODO F6 |
| (new) | What SCIENCE does **after a sweep finishes** (stop until COMMS, or start the next sweep), and **how many sweeps per file** (`SWEEPS_PER_FILE`, now 1). Whether an acknowledgement may clear data (this reverses the earlier decision B3: never delete unless the card is nearly full). | His decision | this session; COMMS_SPEC P21 |
| H11 | What the FSM should do when **SD writes keep failing** (the library never remounts: a controlled reboot after N failures?). | His decision | TODO H11 |
| H13 | The **re-burn policy** (never; rarely with a small cap; keep as is). Needs the burn team's input (above). | Not chosen | TODO H13 |
| D1 / F5 | Remove the payload **serial wait** before handoff, then test boot with no USB host and `TESTING = 0`. | His task | TODO D1, F5 |
| P6 | how long does the satellite wait | Open (details in the comms spec) | COMMS_SPEC |
| P7 | what exactly does "will not conduct any other tasks" mean | Open (details in the comms spec) | COMMS_SPEC |
| P8 | after it gives up or is later contacted | Open (details in the comms spec) | COMMS_SPEC |
| P9 | does the mission clock still start at the burn | Open (details in the comms spec) | COMMS_SPEC |
| P10 | the free-text `HANDSHAKE` message | Open (details in the comms spec) | COMMS_SPEC |
| P12 | which types are sent in which states, and how often | Open (details in the comms spec) | COMMS_SPEC |
| P13 | what else belongs in telemetry | Open (details in the comms spec) | COMMS_SPEC |
| P15 | how is a sweep identified | Open (details in the comms spec) | COMMS_SPEC |
| P16 | is the order of fields `freq, pd, contrast` as written, or the CSV order `freq, contrast, pd` | Open (details in the comms spec) | COMMS_SPEC |
| P18 | the acknowledgement as proposed is a count | Open (details in the comms spec) | COMMS_SPEC |
| P20 | retries | Open (details in the comms spec) | COMMS_SPEC |
| P21 | what does an acknowledgement let the satellite do | Open (details in the comms spec) | COMMS_SPEC |
| P22 | when does a sweep become eligible | Open (details in the comms spec) | COMMS_SPEC |
| P24 | what does the ACK contain | Open (details in the comms spec) | COMMS_SPEC |
| P25 | what if the command is invalid or ignored | Open (details in the comms spec) | COMMS_SPEC |
| P26 | unknown or invalid packets | Open (details in the comms spec) | COMMS_SPEC |

## Not owned by anyone yet

- **The owner of each file's review** (Q-X2) and **who maintains this spec after sign-off** (Q-X9) depend on the team lead naming owners; the FSM spec says Prajwal maintains the document and that Chandrark and Tyler have to complete significant parts of it.
- A **system-level requirements owner** is listed in Q-H15 as a list of names, not one person ("Payload team, Comms team, Prajwal for UART and payload, Burnwire team, Chandrark, Tyler"), so conflicts between subsystems have no single decider.

## How to keep this file true

This is a snapshot. When a question is answered, it should be removed here and answered in the FSM spec (part 7) or the comms spec, which stay the source of truth. If you want, this list can be regenerated from them.
