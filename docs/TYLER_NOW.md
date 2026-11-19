# Questions for Tyler: what I need first

**From:** Prajwal. **Date:** 2026-11-18. **Answer by:** [date, fill in].

Hi Tyler. I wrote a draft of the comms protocol (handshake, science downlink, acknowledgements) in `docs/COMMS_SPEC.md`, and a list of everything that is still open in `docs/OPEN_QUESTIONS.md`. Sorry this is late. **You do not need to read all of it.** These are the questions that decide the wire format. Everything else can wait.

I am **not blocked** while you answer. I plan to build the FSM side against my draft format from the spec, with all packet encoding in one small module, so your answers only change that module. A short reply per question ("yes", "no, because...", "I'd do it this way") is plenty.

I also read your new `groundstation/` code and the two commits after 8acfe8b. Thank you, the uplink tool is exactly what we needed.

---

## Needed now

**1. Can Comms handle a header and then a type?** (spec P1a, P1b, P11)
Today byte 0 is both: `0xC0` command, `0xD0` telemetry, `0xA0` amateur. My draft frame is `[header][type][body][footer]`. Can `Comms._rx_tick` dispatch on header, then type, without breaking the existing `0xC0` and `0xA0` paths? And does the TinyGS beacon keep exactly its current layout (callsign right after `0xD0`), or would you add a type byte to it?
*Why it matters:* every new message depends on it, and it changes what your TinyGS `.ksy` decoder has to describe.

**2. Can a 17-packet sweep go out without dropping packets?** (P14)
One sweep is 1 header packet, 15 full chunks of about 105 bytes and 1 tail chunk. The telemetry queue holds 16 and refuses new packets when full; a TX window sends 10 by default. Which queue should carry science data, and should the FSM feed packets as windows open, or raise `tx_packet_count` and the queue size?
*Why it matters:* a full queue silently drops the end of the sweep.

**3. Is any acknowledgement planned, and can we add new uplink message types?** (P18, P23)
I want the ground to tell the satellite which chunks of a sweep it received. Today there is no ack and no reply. New uplink types would be new command types inside `0xC0` (you already have `_command(body)` in `groundstation/commands.py`). Is that fine, and are there constraints I'm missing (the 63-byte FSK limit, the AES block)?
*Why it matters:* the retry and "delivered" logic depends on it.

**4. Ground station: the receive side, the frequency and the lock bit.** (Q-G2, P30, TODO H16)
- `pluto_uplink.py`, `fsk.py` and the README still use **433.0 MHz**; our carrier is **437.42 MHz**.
- `build_state_command` has no lock option; the satellite uses bit 7 of the state byte as the lock bit.
- Nothing receives or decodes the satellite's downlink, so a handshake reply cannot be automatic today. Is a receive path planned (the Pluto can receive), or is the plan a person watching TinyGS?

**5. Heads-up on changes to your `Comms.py`, and two questions.** (TODO G4, G5)
I merged your `tinygs` branch and changed: no dedup in Comms (the FSM ignores a command for the current state); the lock bit and `on_state_command(code, lock)`; `radio_errors` and `reconfigure()`; 437.42 MHz. I also ported your commit 6c7cf1a (the `ljust` crash and battery rounding). The details are in `docs/RADIO-MODES.md`. Please say if you object to any of it.
Questions: (a) should **fresh or corrupt NVM mean STOP** (silent radio)? Today it does. (b) is the beacon's **mission time seconds since boot** (your doc) or **since the burn** (the FSM sends this)?

---

## Soon, not urgent

**6. Footer and CRC.** (P3a, P3b) Which CRC and which bytes does it cover? For encrypted uplinks the CRC is inside the AES block today; does a common footer sit outside it? Can a TinyGS `.ksy` check a CRC, or does it only display the field?

**7. TinyGS submission.** Who sends the email to missioncontrol@tinygs.com, and where is the `.ksy`? Does the T3 433 MHz board receive well at 437.42 MHz? Also: `tinygs_decoder.py` still says to submit by Telegram bot; the current guide says email.

**8. An over-the-air test.** When can we test with the STAC1 station? I'd like to send one 100 to 200 byte packet and see whether it appears on the station page, and to try a short uplink burst.

---

## Not asking now
Everything else is in `docs/OPEN_QUESTIONS.md` and does not need an answer this week.

## What I plan to do in the meantime
- Write `protocol.py` with my draft format, shared by the FSM and a simulated ground station.
- Add packet loss, duplicate and reordering to the simulator's fake radio.
- Build the FSM's sweep-transfer logic (files, "sweep done", retries, backlog) on top of that, designed so a different ack format or frame layout is a one-file change.
