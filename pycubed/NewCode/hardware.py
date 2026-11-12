"""
The one place the board's hardware object is imported from.

The pycubed library file is reachable under two names on the board (`pycubed` because /lib is
on the path, and `lib.pycubed`). Importing it under both loads it twice, and the second copy
fails or fights over pins (I2C, SPI, ...) because the first already owns them (TODO X5).
Every module imports `cubesat` from here so there is exactly one.
"""

try:
    from lib.pycubed import cubesat
except ImportError:
    from pycubed import cubesat  # desktop / a layout without a lib/ package
