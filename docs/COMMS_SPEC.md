# QubeSat Comms Spec (DRAFT, needs verification and decisions)

**Author:** Prajwal Agrawal (design). **Cleaned up with Claude:** the four exchanges below are Prajwal's proposal, unchanged in intent. Everything added around them is a constraint taken from the code or an **OPEN** question. Nothing marked OPEN has been decided, and no value in this document has been picked on anyone's behalf.
**Status:** DRAFT for review by Tyler (Comms owner). Not implemented.
**Companion document:** `docs/TINYGS_AND_RADIO_CONSTRAINTS.md` (link facts, TinyGS requirements, airtime, sources).

**How to read it**

| Tag | Meaning |
| :-- | :-- |
| **[proposal]** | Prajwal's design, as originally written |
| **[code]** | A fact read from `Comms.py` / `QubeSatFSM.py`, which the protocol must live with |
| **OPEN Pn** | A decision or answer nobody has given. Listed with an owner in section 9 |

Everything here is feasibility-untested: nothing in this spec has been sent over the air.

---

## 1. Link facts the protocol has to fit [code]

- **Uplink (ground to satellite):** FSK, 9.6 kbps, 25 kHz deviation, 1 to 63 bytes, from **our own ground station** only.
- **Downlink (satellite to ground):** LoRa SF7, 125 kHz, CR 4/5, up to about 255 bytes per packet, heard by TinyGS stations **and** (if built) our own station.
- **Half duplex, scheduled.** The satellite listens in FSK for about 10 s (50 loop iterations, Tyler's estimate), then sends up to 10 queued packets in LoRa (defaults, changeable with `SET_CONFIG`), then listens again. The ground can only be heard during listen windows.
- **A reply cannot come from TinyGS.** Every "ground station responds" message below must come from our own station, and it must **hear the satellite first**.
- **Dispatch today:** Comms reads byte 0 of an uplink packet. `0xC0` goes to the encrypted command handler; `0xA0` is queued as an amateur payload and re-sent (digipeater). **Any other first byte is silently ignored.**

## 2. Framing conventions

**Definitions (Prajwal, Nov 17):**

- **Header** = whatever every packet type shares at the front, saying what kind of message it is (a LoRa message, a TinyGS message, an FSK message).
- **Footer** = whatever every packet type shares at the end, such as a CRC.
- Between them comes the **type** and then the **body**.

```
[ header ][ type ][ body ... ][ footer ]
```

So in the messages below, `0xA0`, `0xAA`, `0xAB`, `0xB0`, `0xBB` and the rest are **type** values, not headers.

**What the code does today [code]:** there is no uniform frame. Byte 0 is the only marker, and it is both header and type.

| Byte 0 | Direction | After byte 0 today | Footer today |
| :-- | :-- | :-- | :-- |
| `0xC0` | up | One AES-128-ECB block. The command type (`0x01` state, `0x02` config, `0x03` modulation) is **inside** the encrypted block | CRC-8 and a complement byte, **inside** the encrypted block |
| `0xD0` | down | TinyGS beacon: callsign directly after `0xD0`, **no type byte** (the TinyGS decoder depends on that layout). Or the FSM status packet, whose first byte `0x03` acts as a type. Or free text | Beacon: CRC-8 at the end. Status packet and free text: none |
| `0xA0` | both | Amateur payload, any bytes, not interpreted | None |

**Type values in the proposal** (these would sit after the header):

| Type | Direction | Meaning | Note |
| :-- | :-- | :-- | :-- |
| `0xA0` | down | "STAC IS ALIVE!!!" (handshake) | Same byte value as today's amateur header, but a different field once header and type are separate. Confusing to read; renaming may be worth it |
| `0xB0` | up | "GO STAC" (handshake reply) | |
| `0xA1` to `0xA9` | down | Telemetry types | |
| `0xAA` / `0xAB` / `0xAC` | down | Science header / full chunk / tail chunk | |
| `0xBB` | up | Science acknowledgement | |
| `0xBC` | up | State command | Overlaps `CMD_SET_STATE` (`0x01` inside `0xC0`) |
| `0xAD` | down | State command acknowledgement ("ACK") | |

**What this definition settles, and what it leaves open:**

- **Open questions for this section: P1a to P5.** They are in section 9, sorted by who answers them.

## 3. Message 1: deployment handshake

**[proposal]** After the burn wire succeeds, the satellite sends `[<header> 0xA0 S T A C _ I S _ A L I V E ! ! !]`. The ground station replies `[<header> 0xB0 G O _ S T A C <footer>]`. This exchange is critical: if it does not succeed, the satellite assumes the burn wire failed and does not conduct any other tasks.

**What the code does today [code]:** after the burn, the FSM sends a free-text `HANDSHAKE,DEPLOY_COMPLETE,t=<seconds>` packet once (31 bytes, under `0xD0`), then goes to SCIENCE. "Ground contact" is any valid uplink command; it stops the antenna watchdog's re-burns. Nothing is gated on it.

**Why this needs more detail before it can be validated:**

- The reply can only arrive during a listen window, after our station heard the downlink. The first usable pass may be hours away, and the satellite cannot tell "burn failed" from "no pass yet".
- **Open questions for this section: P6 to P10.** They are in section 9, sorted by who answers them.

## 4. Message 2: telemetry

**[proposal]** Telemetry packet types `0xA1` to `0xA9` (the original draft left the contents open). The two formats that exist today [code]:

| Packet | Length | Layout (big-endian) |
| :-- | :-- | :-- |
| TinyGS beacon | 15 bytes (16 with the `0xD0` header) | callsign (6 ASCII, space padded), state (1), battery mV (u16, 0 = unknown), temperature (u8, °C + 40, `0xFF` = unknown), mission time (u32, seconds), CRC-8 over the first 14 bytes |
| FSM status v3 | 18 bytes (19 with the header), no CRC of its own | type `0x03`, state, flags, burn attempts, battery centivolts (u16), IMU temperature (i16, centi-°C), mission time (u32, seconds since the burn, 0 before it), crash count, sweeps completed (u16), next sweep point, payload error count, caught task exceptions |

Status flags: bit 0 locked, 1 deployed, 2 SD, 3 burn wire, 4 payload, 5 solar, 6 radio, 7 ground heard.

Beacon test vector (callsign `"STAC  "`, state 1, 7.4 V, 25 °C, 120 s): `d0 53 54 41 43 20 20 01 1c e8 41 00 00 00 78 81`.

- **Open questions for this section: P11 to P13.** They are in section 9, sorted by who answers them.

## 5. Message 3: science data

**[proposal]** The satellite sends one sweep, one packet at a time:

- **a. Header:** `[<header>, 0xAA, sweep_num (1), num_points (1)]`
- **b. Full chunk:** `[<header>, 0xAB, idx (1), 0x0A, (freq (2), pd (4), contrast (4)) x10]`
- **c. Tail chunk:** `[<header>, 0xAC, idx (1), <count>, (freq (2), pd (4), contrast (4)) x count]`

The ground station replies `[<header> 0xBB <num_packets_received (1)> <footer>]`. If the count differs from the number the satellite sent, the satellite treats the run as failed and sends the same data in the next transmit window.

**Size and time [my calculation, SF7/125 kHz]:** a 151-point sweep is 1 header packet, 15 full chunks (10 points each) and 1 tail chunk (1 point), 17 packets. A full chunk is 100 bytes of points plus index, count, header, type and footer (about 105 to 106 bytes with a 1-byte header and a 1- or 2-byte footer), so about 180 ms on air. The whole sweep is about 2.8 s of airtime. Chunk size (10 points) and the 1-byte `num_points` (max 255) both fit.

**Limits the code imposes [code]:**
- A TX window sends at most `tx_packet_count` packets, **10 by default**. A 17-packet sweep needs 2 windows unless `SET_CONFIG` raises it.
- The telemetry queue holds **16 packets**, the amateur queue 32. A push to a full queue is **refused and the packet is dropped**. 17 packets do not fit in the telemetry queue at once.
- Nothing is sent again by Comms; the ground cannot request a missing packet; there is no sequence number today.

**Questions the spec cannot answer yet:**
- **Open questions for this section: P14 to P22.** They are in section 9, sorted by who answers them.

## 6. Message 4: state transitions

**[proposal]** The ground sends `[<header> 0xBC <state_id (1)> <lock (1)> <footer>]`. The satellite replies `[<header> 0xAD A C K]`.

**Existing behaviour [code]:** `CMD_SET_STATE` (`0x01`) inside the encrypted `0xC0` carries the state and the lock in one byte (bit 7 = lock), with the complement byte and CRC-8. The satellite already acts on it; there is no reply. A command for the state the satellite is already in changes nothing (the lock bit is still applied).

- **Open questions for this section: P23 to P25.** They are in section 9, sorted by who answers them.

## 7. Everything else the satellite receives or sends

- **Open questions for this section: P26 to P29.** They are in section 9, sorted by who answers them.

## 8. Packet budget summary [my calculation]

| Item | Packets | Airtime |
| :-- | :-- | :-- |
| One 151-point sweep | 17 (1 + 15 + 1) | about 2.8 s |
| Default TX window | 10 packets max | about 1.8 s for 104-byte packets |
| Sweeps per pass | depends on how many TX windows fall inside a TinyGS or own-station pass | not estimated here |

## 9. Open questions by owner

Owners are a proposal from the roles in this repo (Tyler owns Comms, the TinyGS decoder and the ground-station software; Prajwal owns the FSM, the payload UART and this spec; Chandrark is team lead and licence contact; the ground-station software is Tyler's per FSM spec Q-G2). **Correct any that are wrong.** Each question appears once, under the person who has to decide or answer it, with who else must help. The section it came from is in brackets.

The FSM spec (Q-G2) puts the ground-station software under Tyler, who also owns the Comms code, so its questions are listed under him. It is not built yet.

### Tyler (Comms code, TinyGS decoder, ground-station software) (17)

- **OPEN P1a: header values.** Which header values exist, and what does each one mean? Today's three (`0xC0` command up, `0xD0` telemetry down, `0xA0` amateur) are by purpose and direction. Does the header instead say which radio or audience the packet is for (FSK uplink, LoRa to our own station, LoRa for TinyGS to decode)? A LoRa downlink is heard by TinyGS stations and by our own station alike, so the header could not tell them apart unless the satellite sends two different packets. *[section 2; needs input from: Prajwal]*
- **OPEN P1b: does every packet get a type byte?** Today the TinyGS beacon has none (callsign right after `0xD0`), and amateur payloads have none. A uniform `[header][type]` frame means either adding a type byte to the beacon, which changes the layout a TinyGS `.ksy` decoder will describe (TODO H14), or keeping the beacon as its own header value with its present layout. *[section 2; needs input from: Prajwal]*
- **OPEN P1c: how long is the header** (1 byte, as today, or more, for example a version as well, see P5)? *[section 2]*
- **OPEN P3a: what does the footer contain** (a CRC-8 with poly 0x07 and init 0xFF as the beacon and commands use, a CRC-16, a length, a sequence number), and **which bytes does it cover** (header and type and body, or body only)? For encrypted uplinks a common footer sits outside the AES block, so decide whether the existing inner CRC and complement byte stay. *[section 2; needs input from: Prajwal]*
- **OPEN P3b: does a TinyGS decoder verify the footer?** I believe a Kaitai `.ksy` cannot compute a CRC itself, so the field would only be displayed [unverified]. The radio already has its own CRC (LoRa CRC on, FSK CCITT), so the software footer mainly protects what happens after the radio. Is it needed on every packet, including amateur payloads? *[section 2]*
- **OPEN P3c: size cost.** Header, type and footer are 3 or 4 bytes on every packet. That is small against a 104-byte science chunk and large against the 18-byte status packet, and the FSK uplink limit is 63 bytes in total. *[section 2; needs input from: Prajwal]*
- **OPEN P4: byte order and units.** Comms integers are big-endian; the payload UART ICD uses little-endian floats. `freq` is 2 bytes (MHz, 2800 to 2950). Is `pd` a float32 (amps) and `contrast` a float32 (ratio)? Which byte order? *[section 2; needs input from: Prajwal, payload team (units)]*
- **OPEN P5: reserve a way to evolve.** Is there a version byte (perhaps part of the header), so a format can change later without breaking old ground software? *[section 2; needs input from: Prajwal]*
- **OPEN P11: do these keep their current first bytes?** The beacon's `0xD0` header and field layout are what a TinyGS `.ksy` decoder will describe. Moving them to `0xA1` and so on is possible but changes Tyler's decoder and any registration made against it. *[section 4; needs input from: Chandrark (TinyGS registration)]*
- **OPEN P14: which queue and which first byte carries science** (it must not be the telemetry queue as it stands, or queued sweeps beyond 16 packets are lost). Does the FSM feed packets in as windows open instead of queueing all 17 at once? *[section 5; needs input from: Prajwal]*
- **OPEN P17: does a packet carry its own CRC or is the radio's CRC enough?** And is `0xAC` the only variable-length packet? *[section 5; needs input from: Prajwal]*
- **OPEN P23: does `0xBC` replace `0x01`, or is `0x01` kept?** Two ways to set a state are two things to test, and an unencrypted one is a security difference (P2). *[section 6; needs input from: Prajwal]*
- **OPEN P27: the amateur (`0xA0`) digipeater path** must keep working alongside this. The handshake's type value `0xA0` is a different field from the amateur header `0xA0` (P1a), but the satellite re-sends anything it receives with the amateur header, so no uplink must start with it by accident. *[section 7]*
- **OPEN P28: `SET_CONFIG` and `SET_MODULATION`** exist today and are not mentioned in this proposal. Kept as they are? *[section 7; needs input from: Prajwal]*
- **OPEN P29: replay protection.** None today. A recorded valid `0xBB` or `0xBC` could be replayed. Is a sequence number or time stamp needed? *[section 7; needs input from: Chandrark]*

- **OPEN P19: whose count?** The ack can only reflect what **our own station** received. Packets heard only by TinyGS stations do not count. Is that intended, and how reliable must our own receive be? *[section 5; needs input from: Prajwal]*
- **OPEN P30: who builds the rest of the ground station?** FSM spec Q-G2 puts it under Tyler, and on 2026-11-18 his `tinygs` branch gained `groundstation/`: an **uplink-only** tool (a PlutoSky SDR transmits FSK commands; `commands.py` builds the three existing command types with desktop AES, `fsk.py` frames and modulates them, `pluto_uplink.py` is the command line). It has **no receiver, decoder, storage, handshake reply or acknowledgement**; the downlink is received separately by the TinyGS station `STAC1`. What is still unbuilt: receiving and decoding the downlink, the new uplink messages (handshake reply, acknowledgements), storing the data. The handshake (P6, P7) and acknowledgement (P18, P19) designs depend on it. *[section 1; needs input from: Prajwal, Chandrark]*

### Prajwal (FSM, payload UART, this spec) (16)

- **OPEN P6: how long does the satellite wait?** Timeout, retry interval and maximum attempts are all undefined. *[section 3; needs input from: Tyler (listen-window timing, ground station)]*
- **OPEN P7: what exactly does "will not conduct any other tasks" mean?** Does it stop science only, or also the beacon, the battery check, the antenna watchdog, even COMMS? What does the satellite do while waiting: keep repeating the "alive" message? how often? Does it re-burn? *[section 3; needs input from: Chandrark; burn wire team if it affects re-burns (TODO H13)]*
- **OPEN P8: after it gives up or is later contacted**, does it resume normally? Does a successful handshake set the existing "ground heard" flag (stopping the watchdog's re-burns)? *[section 3]*
- **OPEN P9: does the mission clock still start at the burn**, or at the handshake? *[section 3]*
- **OPEN P10: the free-text `HANDSHAKE` message** above: replaced by this, or kept? *[section 3; needs input from: Tyler]*
- **OPEN P12: which types are sent in which states, and how often?** Today the Beacon task runs in IDLE, DEPLOY and COMMS but **not** in SCIENCE, and the TX-window hook sends the status packet in every state. TinyGS cannot decode the status packet. *[section 4; needs input from: Tyler]*
- **OPEN P13: what else belongs in telemetry** (payload RTD temperatures, heater states; both wait on payload TODO D2)? *[section 4; needs input from: payload team]*
- **OPEN P15: how is a sweep identified?** `sweep_num` is one byte, so it wraps at 256, and the FSM **restarts sweep ids at 0 after every reboot**. Needs a boot counter, a mission-time stamp, or a persistent sweep counter. (Science is now one file per sweep, so a file name could carry it.) *[section 5]*
- **OPEN P16: is the order of fields `freq, pd, contrast` as written, or the CSV order `freq, contrast, pd`?** Is an `ERR` point (payload gave nothing) representable (a reserved value)? *[section 5; needs input from: payload team]*
- **OPEN P18: the acknowledgement as proposed is a count.** One lost packet of 17 makes the whole sweep "failed" and everything is re-sent. Alternatives to be decided: a received-bitmap, or a list of missing indices (fits easily in the 63-byte uplink), so only missing packets are re-sent. Either way the ack should name the **sweep**, or an ack can be matched to the wrong one. *[section 5; needs input from: Tyler (ground station)]*
- **OPEN P20: retries.** After a failed ack the data is "sent again next window". Maximum retries? What happens when the next sweep finishes while an older one is still unacknowledged (backlog length, and which is dropped when storage runs out)? *[section 5; needs input from: Tyler]*
- **OPEN P21: what does an acknowledgement let the satellite do?** Mark the sweep as delivered (so it is not sent again), or also delete it? The existing decision (TODO B3) is: never delete unless the card is nearly full. If "delivered" is remembered, where (NVM, filename)? A reboot would otherwise resend everything. *[section 5]*
- **OPEN P22: when does a sweep become eligible?** Is only a **complete** sweep (151 points) sent? And what about a sweep cut short by a reboot? *[section 5]*
- **OPEN P24: what does the ACK contain?** Just the word, or the state and lock actually applied (so the ground can tell what happened if the command was rejected, for example a safety override to IDLE)? Is it sent immediately or in the next TX window? *[section 6; needs input from: Tyler]*
- **OPEN P25: what if the command is invalid or ignored** (an unknown state code, a locked DEPLOY, low battery)? Is there a negative reply? *[section 6; needs input from: Tyler]*
- **OPEN P26: unknown or invalid packets**: still silently ignored (as now), or counted and reported in telemetry? *[section 7; needs input from: Tyler]*

### Chandrark (team lead: licence) (1)

- **OPEN P2: is each uplink message encrypted?** Existing commands are AES-128-ECB inside `0xC0`, so the type is hidden inside the block. If `0xB0`, `0xBB` and `0xBC` follow the same rule they are new command types (`0x04...`) inside it. If they are plain, anyone can send them. The licence question about encrypting commands is open (TODO C5). *[section 2; needs input from: Tyler (implements it)]*


## 10. What Tyler is being asked to validate

1. Can `Comms._rx_tick` dispatch on header and then type, without disturbing `0xC0` (encrypted commands) and `0xA0` (digipeater)?
2. Can a TX window send a 17-packet sweep without the 16-packet telemetry queue dropping packets?
3. Is the 63-byte FSK limit enough for every uplink message here?
4. Is the handshake timing (about 10 s listen windows) workable for our own ground station, and what retry rate is realistic?
5. Which of P1a to P30 does the Comms code already settle?
