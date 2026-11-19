#!/usr/bin/env python3
"""
Interactive simulator for the flight software. Run from anywhere:

  python3 sim/cli.py                      interactive prompt
  python3 sim/cli.py -c "run 2h; status"  run commands and exit (separate with ;)
  python3 sim/cli.py --dt 10              coarser time step: much faster, comms windows stretch (see README)

Type `help` at the prompt.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world as W  # noqa: E402  (importing it installs the fake clock and fake hardware)

HELP = """\
run <time>            advance virtual time: 90s, 10m, 2h, 3d
until <what>          run until: deployed (burn done) | deploy (state) | science | comms | idle | sweep <n> | beacon   (stops after 30 days)
status                state, clocks, burns, sweeps, SD files, comms
events [on|off|N]     events printed during run/until (state changes, burns, faults, commands, packets); N lists the last N
log [on|off|N]        the full flight-code console: live on/off, or show the last N lines (default 30)
cmd <state> [lock]    ground command: idle|deploy|science|comms|stop, optionally 'lock'; 'unlock' sends the state unlocked
battery <volts>       set the battery voltage
temp <degC>           set the IMU temperature
sd pull|insert        remove or insert the SD card (an inserted card is only used after `reboot`)
sd size <bytes>|off   limit the card's capacity (to see the delete-oldest logic), or remove the limit
payload off|on        payload stops/starts answering
radio hang|ok         radio chip stops/starts answering
burn fail [1|2]|ok    make the burn driver (or one wire) fault, or make it work again
reboot                power-cycle: same NVM, FSM boots into IDLE
factory               blank NVM and an empty SD card, then boot (a never-flown board)
files                 list the science files and their row counts
sweep [file]          show a science file as a plot in text, and where the dip is
beacons [N]           last N decoded beacons the ground heard
dt <seconds>          change the loop step
quit
"""

STATES = {"stop": 0, "idle": 1, "deploy": 2, "science": 3, "comms": 4}


def out(*a):
    print(*a, file=W.console.real)


def spark(values):
    chars = " .:-=+*#%@"
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    return "".join(chars[int((v - lo) / span * (len(chars) - 1))] for v in values)


class Sim:
    def __init__(self, dt):
        self.w = W.World(dt=dt)
        self.show_events = True

    def run_cmd(self, line):
        parts = line.split()
        if not parts:
            return True
        cmd, args = parts[0].lower(), parts[1:]
        w = self.w
        try:
            if cmd in ("quit", "exit", "q"):
                return False
            elif cmd == "help":
                out(HELP)
            elif cmd == "run":
                ran = w.advance(W.parse_duration(args[0]), echo=self.show_events)
                out(f"ran {W.fmt_time(ran)} -> now {W.fmt_time(W.now())}; state {w.StateID.name(w.fsm.state)}")
            elif cmd == "until":
                self.until(args)
            elif cmd == "status":
                for k, v in w.status().items():
                    out(f"  {k:22s} {v}")
            elif cmd == "log":
                if args and args[0] in ("on", "off"):
                    W.console.live = args[0] == "on"
                    out("live log", args[0])
                else:
                    n = int(args[0]) if args else 30
                    for line in list(W.console.lines)[-n:]:
                        out(line)
            elif cmd == "events":
                if args and args[0] in ("on", "off"):
                    self.show_events = args[0] == "on"
                    out("events during run/until:", args[0])
                else:
                    n = int(args[0]) if args else 30
                    for t, text in w.events[-n:]:
                        out(f"  [{W.fmt_time(t)}] {text}")
            elif cmd == "cmd":
                self.ground(args)
            elif cmd == "battery":
                W.S.battery_v = float(args[0]); out("battery", W.S.battery_v, "V")
            elif cmd == "temp":
                W.S.temperature_c = float(args[0]); out("temperature", W.S.temperature_c, "C")
            elif cmd == "sd":
                self.sd(args)
            elif cmd == "payload":
                W.S.payload_online = args[0] == "on"; out("payload", args[0])
            elif cmd == "radio":
                W.S.radio_hung = args[0] == "hang"; out("radio", args[0])
            elif cmd == "burn":
                if args[0] == "ok":
                    W.S.burn_fail, W.S.burn_fail_wire = False, None
                else:
                    W.S.burn_fail, W.S.burn_fail_wire = (len(args) == 1), (args[1] if len(args) > 1 else None)
                out("burn", " ".join(args))
            elif cmd == "reboot":
                w.reboot(); out("rebooted")
            elif cmd == "factory":
                w.boot(clear_nvm=True); out("factory-fresh boot")
            elif cmd == "files":
                for n in w.science_files():
                    out(f"  {n}: {len(w.read_rows(n))} rows")
            elif cmd == "sweep":
                self.sweep(args)
            elif cmd == "beacons":
                n = int(args[0]) if args else 5
                for t, info in w.beacons[-n:]:
                    out(f"  [{W.fmt_time(t)}] {info}")
                out(f"  ({len(w.beacons)} beacons total, {len(w.other_tx)} other packets)")
            elif cmd == "dt":
                w.dt = float(args[0]); out("dt", w.dt)
            else:
                out("unknown command; try `help`")
        except (IndexError, ValueError) as e:
            out("bad arguments:", e, "(see `help`)")
        return True

    def until(self, args):
        w, what = self.w, args[0] if args else ""
        S = w.StateID
        conds = {
            "deployed": lambda: w.fsm.deployed,
            "deploy": lambda: w.fsm.state == S.DEPLOY,
            "science": lambda: w.fsm.state == S.SCIENCE,
            "comms": lambda: w.fsm.state == S.COMMS,
            "idle": lambda: w.fsm.state == S.IDLE,
            "beacon": (lambda n=len(w.beacons): len(w.beacons) > n),
        }
        if what == "sweep":
            target = int(args[1])
            stop = lambda: w.fsm.sweeps_completed >= target
        elif what in conds:
            stop = conds[what]
        else:
            out("until what? deployed | deploy | science | comms | idle | sweep <n> | beacon")
            return
        ran = w.advance(30 * 86400, stop=stop, echo=self.show_events)
        hit = "reached" if stop() else "NOT reached within 30 days"
        out(f"{what}: {hit} after {W.fmt_time(ran)} (now {W.fmt_time(W.now())})")

    def ground(self, args):
        w = self.w
        name = args[0].lower()
        if name not in STATES:
            out("states: stop idle deploy science comms")
            return
        lock = len(args) > 1 and args[1].lower() == "lock"
        w.ground_send(STATES[name], lock=lock, repeat=1)
        out(f"ground queued: {name}{' + lock' if lock else ''} (heard at the next RX window)")

    def sd(self, args):
        if args[0] == "pull":
            self.w.set_sd(False)
        elif args[0] == "insert":
            self.w.set_sd(True)
            out("(the board only mounts the card at boot: writes stay broken until `reboot`)")
        elif args[0] == "size":
            W.S.sd_capacity = None if args[1] == "off" else int(args[1])
        out("sd present:", W.S.sd_present, "capacity:", W.S.sd_capacity)

    def sweep(self, args):
        w = self.w
        names = [args[0]] if args else w.science_files()[-1:]
        if not names:
            out("no science files yet")
            return
        rows = w.read_rows(names[0])
        pts = [(int(r[2]), float(r[3])) for r in rows if r[3] != "ERR"]
        if not pts:
            out(f"{names[0]}: {len(rows)} rows, none with a contrast value")
            return
        out(f"{names[0]}: {len(rows)} rows, {pts[0][0]}..{pts[-1][0]} MHz")
        out("  [" + spark([c for _, c in pts]) + "]  (' ' lowest, '@' highest)")
        f, c = min(pts, key=lambda p: p[1])
        out(f"  lowest contrast {c:.4f} at {f} MHz")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-c", "--commands", help="commands separated by ;")
    ap.add_argument("--dt", type=float, default=1.0, help="virtual seconds per FSM loop (default 1)")
    ns = ap.parse_args()
    sim = Sim(ns.dt)
    if ns.commands:
        for line in ns.commands.split(";"):
            out(f"> {line.strip()}")
            if not sim.run_cmd(line.strip()):
                break
        return
    out("QubeSat flight-software simulator. `help` lists commands. Virtual time, real FSM and Comms code.")
    while True:
        try:
            line = input("sim> ")
        except (EOFError, KeyboardInterrupt):
            out()
            break
        if not sim.run_cmd(line.strip()):
            break


if __name__ == "__main__":
    main()
