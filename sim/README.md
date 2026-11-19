# Flight-software simulator

Runs the **real** `QubeSatFSM.py`, `Comms.py`, `Task.py` and `StateCodeGenerator.py` against a fake
world: fake board library, burn wire, payload, radio chip and clock. No hardware needed.

    python3 sim/cli.py                        interactive prompt (`help` lists commands)
    python3 sim/cli.py -c "until sweep 1; sweep"
    python3 sim/cli.py --dt 10                coarser loop step: faster, see below
    python3 sim/test_sim.py                   scenario tests (about 3 s)

Example session:

    sim> until deployed          # an hour in IDLE, then both burns
    sim> until sweep 1           # one full 151-point sweep
    sim> sweep                   # the spectrum as text, and where the dip is
    sim> cmd science lock        # ground command; heard at the next RX window
    sim> sd pull                 # now see what the FSM does
    sim> reboot                  # power cycle: same NVM
    sim> events 20               # the last 20 events (they also print during run/until; `events off` silences them)
    sim> log 30                  # everything the flight code printed

## What is simulated, and how closely

| Thing | Model |
| :-- | :-- |
| Clock | Virtual. A loop step is `--dt` seconds (default 1). Blocking calls advance it: a burn by its `duration` (the real driver sleeps), a contrast measurement by 1.0 s, a photodiode read by 0.4 s (inferred), a dead payload by its timeout. |
| Payload | Synthetic ODMR spectrum: two dips around 2870 MHz plus noise (`Settings.odmr_*`). Can be turned off. |
| Burn wire | The **real `BurnWire.py`** runs over fake `board`, `pwmio` and `digitalio`. Each wire's real on-time and duty are logged, so the `setup()` contract and `duration` blocking are exercised, not copied. A driver fault can be injected (either wire, or one). |
| Radio | A fake SX127x. `cmd ...` queues a real encrypted state command; beacons the satellite sends are decoded with `tinygs_decoder`. Can be made to hang. |
| SD card | A temp directory. Pulling it makes writes fail; inserting it does nothing until `reboot`, because `lib/pycubed.py` only mounts the card at boot. Can be given a small capacity to exercise delete-oldest. |
| NVM | The flight code's own desktop fallback arrays, kept across `reboot`, cleared by `factory`. |
| Hard reset | `FatalFault` and `micro.reset()` become a reboot, as `QubeSatFSM.run()` does (10 s wait, crash streak counted). That handler is copied into `world.py`; keep the two in sync. |

## What it does not tell you

- **Comms timing.** Comms counts loop *iterations* (50 RX ticks, and so on), not seconds. The real
  loop sleeps 0.1 s per iteration; the default `--dt 1` makes an RX window ten times longer than on
  the board, and `--dt 10` a hundred times. Use `--dt 0.1` when comms timing matters (slow).
- Real SPI/RF behaviour, SD card quirks, heap fragmentation and memory limits, electrical behaviour
  (burn wire current, battery sag), and the real `DualModeRadio` (stubbed; it has its own tests).
- The payload's timing numbers are measurements from one bench session, not guarantees.
- Syntax CircuitPython rejects: use `python3 tools/check_circuitpython.py` for that.

## Layout

- `world.py` the fake hardware and the `World` that wires it to the flight code
- `cli.py` the interactive prompt
- `test_sim.py` scenario tests
