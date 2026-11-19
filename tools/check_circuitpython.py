#!/usr/bin/env python3
"""
Compile every file that goes on the board with the CircuitPython 8.2.10 compiler (mpy-cross),
so syntax CircuitPython rejects shows up on the desktop instead of on the board.

  python3 tools/check_circuitpython.py              check pycubed/NewCode (and its lib/)
  python3 tools/check_circuitpython.py --download   fetch the matching mpy-cross first
  python3 tools/check_circuitpython.py FILE...      check only these files

mpy-cross is looked for in: $MPY_CROSS, tools/.bin/mpy-cross, then PATH. Its version must match the
board (boot_out.txt says 8.2.10); a different version can accept or reject different code.

Things this has caught so far: `{e!r}` in an f-string, an f-string inside an f-string expression,
and two f-strings written next to each other (implicit concatenation; join them with + instead).
It checks syntax only. It does not run anything, and it cannot see memory limits.
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request

VERSION = "8.2.10"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "tools", ".bin", "mpy-cross")
BOARD_DIR = os.path.join(ROOT, "pycubed", "NewCode")
# Run on the desktop only; they are never copied to the board, so they may use full Python.
DESKTOP_ONLY = {"test_fsm.py", "test_comms.py", "test_dual_mode_radio.py"}
BASE = "https://adafruit-circuit-python.s3.amazonaws.com/bin/mpy-cross/"


def download_url():
    system, machine = platform.system(), platform.machine().lower()
    if system == "Darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
        return f"{BASE}macos-11/mpy-cross-macos-11-{VERSION}-{arch}"
    if system == "Linux" and machine in ("x86_64", "amd64"):
        return f"{BASE}linux-amd64/mpy-cross-linux-amd64-{VERSION}"
    return None


def find_mpy_cross():
    for cand in (os.environ.get("MPY_CROSS"), BIN, shutil.which("mpy-cross")):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def download():
    url = download_url()
    if not url:
        print("No download known for this platform; get mpy-cross", VERSION,
              "from https://adafruit-circuit-python.s3.amazonaws.com/index.html?prefix=bin/mpy-cross/")
        return False
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    print("Downloading", url)
    urllib.request.urlretrieve(url, BIN)
    os.chmod(BIN, 0o755)
    return True


def board_files():
    files = []
    for folder, _dirs, names in os.walk(BOARD_DIR):
        if "__pycache__" in folder:
            continue
        for n in sorted(names):
            if n.endswith(".py") and not (folder == BOARD_DIR and n in DESKTOP_ONLY):
                files.append(os.path.join(folder, n))
    return sorted(files)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    exe = find_mpy_cross()
    if exe is None and "--download" in argv:
        if download():
            exe = find_mpy_cross()
    if exe is None:
        print("mpy-cross not found. Run with --download, or set MPY_CROSS.")
        return 2
    version = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip()
    print(version)
    if VERSION not in version:
        print(f"Warning: the board runs {VERSION}; results may differ.")

    files = args or board_files()
    out = tempfile.mkdtemp()
    failed = 0
    for path in files:
        r = subprocess.run([exe, "-o", os.path.join(out, "x.mpy"), path], capture_output=True, text=True)
        if r.returncode != 0:
            failed += 1
            print(f"FAIL {os.path.relpath(path, ROOT)}")
            print("     " + (r.stdout + r.stderr).strip().replace("\n", "\n     "))
    shutil.rmtree(out, ignore_errors=True)
    print(f"{len(files) - failed}/{len(files)} files compile" + ("" if not failed else f", {failed} FAILED"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
