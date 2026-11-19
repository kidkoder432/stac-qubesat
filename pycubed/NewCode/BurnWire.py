import time
import board
import pycubed
import digitalio
import pwmio
import microcontroller

print(
    "Reset reason:", microcontroller.cpu.reset_reason
)  # tells us the reason for previous failure if necessary
class BurnWire:
    freq = 1000
    duration = 0
    ready = False
    isBurning = False  # turn to not isBurning once started and then not isBurning after the necessary time runs (30 min i think

    def __init__(self):
        self.isBurning = False

    def setup(self):
        pycubed.cubesat._relayA.drive_mode = digitalio.DriveMode.PUSH_PULL
        pycubed.cubesat._relayA.value = True
        self.ready = True

    def burningCheck(self):

        if not self.ready:
            return "Burn wire not ready to fire. Call setup() first."

        if self.isBurning == False:
            return "The burn wires are currently not burning."
        return "The burn wires are currently burning."

    def cubesatBurn(self, burn_num, dutycycle, duration):
        if duration == 0 or dutycycle == 0:
            self.isBurning = False
            return True

        if not self.ready:
            self.isBurning = False
            return False

        self.isBurning = True
        if burn_num == "1":
            burnwire = pwmio.PWMOut(board.BURN1, frequency=self.freq, duty_cycle=0)
        elif burn_num == "2":
            burnwire = pwmio.PWMOut(board.BURN2, frequency=self.freq, duty_cycle=0)

        burnwire.duty_cycle = int((dutycycle / 100) * (0xFFFF))
        print(f"Wire {burn_num} has started burning")
        targetDutyCycle = int((dutycycle / 100) * (0xFFFF))
        burnwire.duty_cycle = int(targetDutyCycle)
        # print(microcontroller.cpu.reset_reason)

        time.sleep(duration)
        print(f"Wire {burn_num} has finished burning")

        self.isBurning = False
        burnwire.duty_cycle = 0
        burnwire.deinit()
        pycubed.cubesat._relayA.drive_mode = digitalio.DriveMode.OPEN_DRAIN
        self.ready = False
        return True

    def turnOff(self, burn_num):
        return self.cubesatBurn(burn_num, 0, 0)


def BurnWireObject():
    e = BurnWire()
    e.setup()
    if not e.cubesatBurn("2", 2, 30):
        raise RuntimeError("Burn wire was not ready. Call setup() first. ")


if __name__ == "__main__":
    BurnWireObject()
