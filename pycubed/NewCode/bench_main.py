"""
Bench-only entry point for the FSM. This is NOT flight code.

The flight main.py waits on the team's answer to Q-X1 (what else belongs at startup), and on
the burn wire numbers (Q-D1). This file exists so the FSM can be run on the real board now,
with the burn wire disabled, to start on-hardware testing (Q-V1).

On the board:   copy the NewCode files and lib/ to the board, then either copy this file to
code.py, or from the REPL:   import bench_main; bench_main.main()

Edit the switches below; nothing else needs to change.
"""

import Comms
import QubeSatFSM as fsm_module
from hardware import cubesat  # noqa: F401  (same hardware object everywhere, see hardware.py)

# ---- bench switches -----------------------------------------------------------------------
# False = the burn wire is only printed, nothing is energised. Leave False until Q-D1 is answered.
BURN_REALLY = False
# Seconds in IDLE before DEPLOY. The real value is 3600; use a short one on the bench.
DEPLOY_AFTER_S = 60
# Comms treats fresh or corrupt NVM as STOP (radio silent, listening only). On the bench that
# hides the beacon, so start in IDLE instead. Never do this in flight without asking the Comms owner.
FORCE_RADIO_ON = True
# Seconds per science/comms slot. The real value is 600; a short one shows the 7/3 cycle quickly.
# (The first 14 days of mission time are all science, so also shorten SCIENCE_ONLY_S to see it.)
SLOT_S = None
SCIENCE_ONLY_S = None
# -------------------------------------------------------------------------------------------


class _DryBurn:
    """Stands in for BurnWire on the bench: same calls, nothing is driven."""

    def cubesatBurn(self, burn_num, dutycycle, duration):
        print(f"[BENCH] would burn wire {burn_num}: duty={dutycycle}, duration={duration}")

    def burningCheck(self):
        return "dry run (burn wire disabled)"


def build():
    """Create the FSM and Comms and wire them together, without starting the loop."""
    if not BURN_REALLY:
        fsm_module.BurnWire = _DryBurn
        print("[BENCH] Burn wire DISABLED (BURN_REALLY = False)")
    cls = fsm_module.QubeSatFSM
    cls.DEPLOY_AFTER_IDLE_S = DEPLOY_AFTER_S
    if SLOT_S is not None:
        cls.SLOT_S = SLOT_S
    if SCIENCE_ONLY_S is not None:
        cls.SCIENCE_ONLY_S = SCIENCE_ONLY_S

    fsm = cls()
    radio = Comms.configure_radio()
    comms = Comms.CommsManager(radio)
    if FORCE_RADIO_ON and comms.state_code == Comms.STATE_STOP:
        print("[BENCH] NVM says STOP; forcing IDLE so the radio transmits (FORCE_RADIO_ON)")
        comms.state_code = Comms.STATE_IDLE
    fsm.attach_comms(comms)
    return fsm, comms


def main():
    fsm, _ = build()
    fsm.run()


if __name__ == "__main__":
    main()
