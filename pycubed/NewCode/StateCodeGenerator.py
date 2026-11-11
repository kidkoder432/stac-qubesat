# State codes shared by the FSM and Comms.
#
# Plain integer constants, no `enum` (CircuitPython has no enum module). These MUST match
# the STATE_* constants in Comms.py (tests/test_fsm.py checks this).
#
# Each state has the minimum number of bits (3). 0 is reserved: STOP = halt all
# transmission (Comms keeps listening so the ground can wake it with a non-zero state).
# Comms is not a separate number; the COMMS *state* is the downlink / ground-contact window.


class StateID:
    STOP = 0  # not an FSM state; a Comms command that halts transmission
    IDLE = 1  # 0b001
    DEPLOY = 2  # 0b010
    SCIENCE = 3  # 0b011
    COMMS = 4  # 0b100

    _NAMES = {0: "STOP", 1: "IDLE", 2: "DEPLOY", 3: "SCIENCE", 4: "COMMS"}

    @classmethod
    def name(cls, code):
        return cls._NAMES.get(code, "UNKNOWN(%s)" % code)

    @classmethod
    def is_valid(cls, code):
        return code in cls._NAMES


class StateCodec:
    """Kept for compatibility with older code. Codes are now the state values themselves."""

    STOP = StateID.STOP

    @classmethod
    def encode(cls, state):
        if not StateID.is_valid(state):
            raise ValueError("Unknown state: " + str(state))
        return state

    @classmethod
    def decode(cls, code):
        if code == cls.STOP:
            return None  # caller should halt transmission
        if not StateID.is_valid(code):
            raise ValueError("Unknown code: " + str(code))
        return code

    @classmethod
    def is_valid(cls, code):
        return StateID.is_valid(code)
