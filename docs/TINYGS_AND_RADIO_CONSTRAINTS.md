# TinyGS and radio constraints: input for the downlink and uplink protocol

**Purpose.** What the radio link and TinyGS require, allow and do not say, so the satellite-to-ground protocol (like the payload UART ICD) can be written without guessing. This document defines no protocol. It lists the limits the protocol has to live inside.

**Date:** 2026-11-17. **How to read the confidence tags:**

- **[code]**: read directly from `pycubed/NewCode/Comms.py`, `DualModeRadio.py`, `lib/pycubed_rfm9x.py` or `tinygs_decoder.py`.
- **[TinyGS docs]**: from a TinyGS page, linked in section 8. Two of the pages are dated (the radio tuning wiki was last edited Feb 2021).
- **[my calculation]**: derived here, formula shown.
- **[unverified]**: from memory or inference. Needs a person or a source to confirm.
- **[NOT DOCUMENTED]**: I looked and the source does not say. Treat as unknown, not as "allowed".

---

## 1. The two links are not symmetric

|                       | Uplink (ground to satellite)                                                                                                                                     | Downlink (satellite to ground)                                                   |
| :-------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------- |
| Who                   | **Our own ground station** (Chandrark's answer: "the uplink is the team's own ground station")                                                             | **TinyGS** network (third-party receivers)                                 |
| Modulation            | FSK, 9.6 kbps, 25 kHz deviation, sync `2D D4`, 1 to 63 bytes [code]                                                                                            | LoRa, 125 kHz, SF7, CR 4/5, sync word `0x12`, preamble 8, CRC on, 5 dBm [code] |
| Carrier               | 437.42 MHz [code]                                                                                                                                                | 437.42 MHz [code]                                                                |
| Can TinyGS take part? | **[NOT DOCUMENTED]** whether TinyGS stations transmit at all. The tutorial and tuning wiki are about receiving downlinks. Plan as if TinyGS cannot uplink. | Yes, this is its job                                                             |

Consequence: **anything the satellite must learn from the ground (commands, acknowledgements) has to come from our own station.** TinyGS can tell *us* what it heard, but only through its own channels (website, MQTT; a community note says public packet data is delayed by 48 hours [unverified], so it is not a real-time acknowledgement path).

## 2. What TinyGS needs before it will show our packets [TinyGS docs]

From the "How to add a new satellite" tutorial (page dated Jun 10, 2026). Submission is by **email to `missioncontrol@tinygs.com`** with:

1. Metadata: satellite name, photos or renderings, a one-sentence summary and a long description (mission goals, team).
2. A **validated radio configuration**, proven with a saved "test reception frame" link from a station in test mode (manual tuning, automatic tuning disabled). The page says to keep any test transmission duty cycle "within one minute" and to never use the name of an active satellite.
3. A **Kaitai Struct `.ksy` decoder** "valid for your payload formats". The Norbi decoder is the example.

**How the team plans to get the test frame** (Tyler's write-up, Nov 11): a LILYGO T3 V1.6.1 433 MHz board runs as TinyGS station `STAC1`. In test mode, with Automatic Tuning disabled, enter a temporary name (not an active satellite), LoRa, the frequency, 125 kHz, SF 7, CR 5, sync word 18, preamble 8, CRC on. Then send test beacons from the PyCubed (his test sends 20, 3 s apart, without the FSM) and compare the station page with the board's serial output byte for byte. **Two things to change for us:** his write-up says 433.0 MHz and our carrier is 437.42 MHz, so the manual tuning must use 437.42; and a 433 MHz board and antenna are built for 433, so whether it receives well at 437.42 is **[unverified]**. The burn wires must be disconnected for the satellite-side test while the ArcticaNova `BurnWire.py` is in use (ours is guarded, and no longer fires on import).

> **Out of date in our repo.** `tinygs_decoder.py` says to submit that Python file "via their Telegram bot (@tinygs_satadmin_bot)". The current tutorial asks for a Kaitai `.ksy` file by email instead. `tinygs_decoder.py` is only useful as our own desktop decoder, and a `.ksy` for each packet format still has to be written. (Whether the Telegram route still works: [NOT DOCUMENTED].)

**What TinyGS will not forward** [TinyGS docs]: "tinyGS only forwards packets with publicly known payloads according to the global tinyGS Manifest". That sentence sits in the webhook section, so its exact reach is unclear, but the safe reading is: **downlink payloads must be publicly documented and decodable, not encrypted.** This also matches amateur-radio practice (section 6).

**Modem parameters TinyGS asks for** (tuning wiki, [TinyGS docs]; field names as the wiki gives them):

| Our value [code]      | TinyGS LoRa field                              |
| :-------------------- | :--------------------------------------------- |
| LoRa                  | `mode`                                       |
| 437.42 MHz            | `freq`                                       |
| 125 kHz               | `bw`                                         |
| SF7                   | `sf`                                         |
| CR 4/5                | `cr` (the wiki's example uses `5` for 4/5) |
| `0x12` (decimal 18) | `sw`                                         |
| 8 symbols             | `pl`                                         |
| on                    | `crc`                                        |
| 5 dBm                 | `pwr` (labelled "Power (for TX)")            |

Other LoRa fields exist (`cl`, `gain`, `fldro`, `NORAD`, `reg`). The wiki has FSK fields too (`br`, `fd`, `bw`, `fsw`, `ook`), relevant only if we ever downlink in FSK.

## 3. What TinyGS does not document [NOT DOCUMENTED]

I read the tutorial and the tuning wiki and neither says:

- A **maximum or minimum packet length**.
- Whether a station can follow **two modulation profiles** from one satellite. The wiki describes one `modem_startup` configuration per station. Our scheme switches between FSK (listening) and LoRa (transmitting), so a station tuned to our LoRa profile hears us only while we are in LoRa.
- Header bytes, endianness, or checksums expected by the decoder. That is whatever our `.ksy` describes. **Open: does TinyGS pass the raw on-air bytes to the decoder, including our `0xD0`/`0xA0` first byte?** `tinygs_decoder.py` assumes it may or may not be present.
- Whether stations **transmit** (see section 1).

One anecdotal figure: a TinyGS newsletter mentions another satellite limited to 64-byte packets. That is that satellite's choice, not a TinyGS rule.

**The 15-byte limit is ours, not TinyGS's.** `tinygs_decoder.py` rejects anything that is not exactly 15 bytes because it was written for the beacon. TinyGS itself asks for a `.ksy` per payload format, and a `.ksy` can describe variable-length packets (for example a type byte, then a layout per type). Whether a station's firmware has a buffer limit, and how the network shows a packet with no matching `.ksy`, are not documented. The direct test is to send one packet of the intended size to a station in test mode (section 2) and see whether it appears.

## 4. What our Comms code can send and receive [code]

**Downlink packets** (all LoRa, in TX windows):

| First byte | Meaning                                                                                                               | Sent when                                                                           | Decodable by `tinygs_decoder.py`       |
| :--------- | :-------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------- | :--------------------------------------- |
| `0xD0`   | Telemetry: the 15-byte TinyGS beacon (callsign 6 B, state, battery mV, temperature, mission time, CRC-8), 16 B on air | By the FSM's Beacon task in IDLE, DEPLOY and COMMS, not in SCIENCE                  | Yes                                      |
| `0xD0`   | Telemetry: the FSM status packet, type `0x03`, 18 B (19 on air)                                                     | Every `telem_cadence`-th TX window, every state                                   | **No** (decoder only accepts 15 B) |
| `0xD0`   | Free text, e.g. `HANDSHAKE,DEPLOY_COMPLETE,t=71` (31 B)                                                             | Once, after deploying                                                               | No                                       |
| `0xA0`   | Amateur payload, any bytes                                                                                            | Anything received with `0xA0` over FSK is queued and re-sent: the digipeater path | n/a                                      |

**Uplink packets** (FSK, 63 B max): `0xC0` + AES-128-ECB encrypted command (set state with lock bit, set comms config, set modulation); `0xA0` + payload for the digipeater. Anything else is ignored. A command is accepted only if the decrypted complement byte and CRC-8 agree. There is no sequence number, no replay protection and no acknowledgement. The AES key is still all zeros (placeholder).

**Uplink command layouts** [code, `Comms.py`]. Plaintext before AES, all sent as `0xC0` + one AES-128-ECB block (PKCS7 padded to 16 bytes, so **17 bytes on air** on the board). CRC-8 is over every plaintext byte before it (poly 0x07, init 0xFF).

| Command        | Plaintext                                                                         |
| :------------- | :-------------------------------------------------------------------------------- |
| Set state      | `01` `[lock<<7 \| state]` `~that byte` `crc`                               |
| Set config     | `02` `rx_ticks` `tx_packet_count` `telem_cadence` `~rx_ticks` `crc`   |
| Set modulation | `03` `mode` `seconds` `~mode` `crc` (LoRa lease 1 to 255 s; FSK uses 0) |

State codes: 0 STOP, 1 IDLE, 2 DEPLOY, 3 SCIENCE, 4 COMMS. Bit 7 of the state byte is the lock bit (our addition; Tyler's write-up predates it).

**Beacon test vector** [code, checked against Tyler's example]: `build_beacon_packet(state=1, 7.4 V, 25 C, mission time 120 s)` with callsign `"STAC  "` gives, on air, `d0 53 54 41 43 20 20 01 1c e8 41 00 00 00 78 81` (16 bytes: header `d0`, callsign, state, battery 7400 mV = `1ce8`, temperature 25+40 = `41`, time `00000078`, CRC `81`). Useful for checking a `.ksy` decoder.

**Schedule** (defaults, changeable by `SET_CONFIG`): RX for 50 loop iterations (Tyler estimates about 10 s: each iteration is a 0.1 s sleep plus a receive of up to 0.1 s; not measured here), then a TX window of up to 10 packets, then back to RX. Telemetry queue holds 16 packets, amateur queue 32; a full queue refuses new packets. A LoRa window times out after at most 60 s by default (1 to 255 s by command). The satellite cannot hear FSK uplinks while it transmits LoRa.

**Size limits.** FSK packets: 63 B including the header byte. LoRa: `pycubed_rfm9x.send` accepts 252 bytes of data after the 4-byte RadioHead header that `send_raw` fills from our first 4 bytes, so up to 256 on air. The SX127x FIFO limit is 255, so **keep packets at 255 B or less** [unverified edge case]. Comms itself does no size check on LoRa packets.

## 5. Airtime and what fits [my calculation]

LoRa SF7, 125 kHz, CR 4/5, 8-symbol preamble, explicit header, CRC on (standard LoRa time-on-air formula; raw bit rate 7 x 125000/128 x 4/5 = 5.47 kbit/s):

| Packet length (bytes, on air) | Time on air |
| :---------------------------- | :---------- |
| 16                            | 51 ms       |
| 32                            | 72 ms       |
| 64                            | 118 ms      |
| 128                           | 215 ms      |
| 200                           | 318 ms      |
| 255                           | 400 ms      |

Example sizing (a sizing exercise, **not a proposed format**): one ODMR sweep is 151 points. At 10 bytes per point (2 B frequency, 4 B contrast, 4 B photodiode) that is 1510 B, about 8 packets of 200 B, about 2.5 s of airtime, which fits in one default TX window of 10 packets. Overhead (sequence number, CRC, sweep id) comes on top. Real throughput depends on how many TX windows fall inside a pass, and a TinyGS station only hears us while the satellite is above its horizon, so some packets will be lost with no retransmission mechanism today.

## 6. Rules outside the code [unverified, needs the licence holder]

- **Frequency.** 437.42 MHz is inside 435 to 438 MHz, the amateur-satellite segment. IARU coordination status for our carrier: unknown.
- **Uplink encryption.** US rule 47 CFR 97.211(b), as quoted by a copy of the regulation, allows a telecommand station to use special codes to hide the meaning of commands sent to a space station; 97.211(c) lists 435 to 438 MHz among the permitted bands. I could not open the current text of 97.113 (the general rule against obscured messages). **Which administration licenses this satellite, and whether the same exception applies there, is not known to me.** Ask the licence holder (open item C5).
- **Downlink content.** Plan on a public, unencrypted, documented format. Both TinyGS's "publicly known payloads" rule and amateur-radio practice point that way.
- **Identification.** The beacon carries the callsign, but it is still the placeholder `"STAC  "`.

## 7. What the protocol author needs to decide (none of this is decided)

1. **Message types** on each link. Downlink: beacon, status, science data, handshake/log, anything else. Uplink: state, config, modulation, and whatever new types an acknowledgement or a "send me sweep N" request would need.
2. **Framing for science data**: how a sweep is split across packets (sweep id, sequence number, total count, per-point layout, CRC), within the 255 B and airtime limits above. This is TODO item C3, blocked on the payload and comms teams.
3. **Acknowledgement**: there is none today. It would have to be a new uplink command from our own station, and the satellite would need a rule for what it does on receipt (it would not necessarily mean deleting data; that decision, B3, is separate).
4. **One decoder per format**: a `.ksy` for every downlink packet type we want shown, and the question of the leading header byte (section 3).
5. **Which packet types should exist in which FSM states.** Today SCIENCE sends no beacon, only the 19-byte status packet, which TinyGS cannot decode.
6. **Encryption scope**: uplink only (as now) or not at all, after the licence question in section 6 is answered.

## 8. Statements in Tyler's Nov 11 write-up that no longer match this repo

For whoever writes the protocol, so the two documents are not mixed up. All checked against the merged code.

| His write-up says                                                                                   | In this repo                                                                                                                  |
| :-------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------- |
| Frequency 433.0 MHz (LoRa and FSK)                                                                  | 437.42 MHz                                                                                                                    |
| "A repeated state command is ignored"                                                               | Comms passes every copy to the FSM, which ignores a command for the state it is already in                                    |
| State command is `01 state ~state crc`                                                            | Plus a lock bit in bit 7 of the state byte; callback is `(code, lock)`                                                      |
| Beacon mission time is "seconds since boot"                                                         | The FSM sends seconds since the burn, 0 before it (TODO G5: which is intended?)                                               |
| The FSM creates comms in its constructor and calls `configure_radio()`                            | `attach_comms()` wires it; radio health calls `CommsManager.reconfigure()`                                                |
| `BurnWire.py` fires burn wire 2 on import                                                         | The ArcticaNova file does; ours does not, and the FSM now calls `setup()` first                                             |
| Desktop tests 17 of 17                                                                              | 15 comms tests plus 11 dual-mode radio tests here (ported), 64 FSM tests                                                      |
| The FSM has a Beacon task every 30 minutes and queues a beacon every `telem_cadence`-th TX window | The Beacon task exists only in IDLE, DEPLOY and COMMS; the TX-window hook sends the 18-byte status packet instead (section 4) |

## 9. Sources

- TinyGS, "How to add a new satellite" (page dated Jun 10, 2026): https://tinygs.com/tutorials/how-to-add-new-satellite
- TinyGS wiki, Radio Tuning Guide (last edited Feb 17, 2021): https://github.com/tinygs/tinyGS/wiki/Radio-Tuning-Guide
- TinyGS decoder examples (Norbi): https://github.com/4m1g0/tinygs-decoders/blob/master/ksy/norbi.ksy
- 47 CFR 97.211, Space telecommand station: https://www.customsmobile.com/regulations/title47_chapterI-i4_part97_subpartC_section97.211 (verify against the current eCFR before relying on it)
- Repo: `pycubed/NewCode/Comms.py`, `DualModeRadio.py`, `tinygs_decoder.py`, `lib/pycubed_rfm9x.py`, `docs/RADIO-MODES.md`
