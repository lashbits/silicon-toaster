#!/usr/bin/python3

from silicontoaster import SiliconToaster
from time import sleep

toaster = SiliconToaster("/dev/ttyUSB0")
toaster.on_off(True)

avg_count = 100
log = open("calibration-1600.log", "w")

for width in range(1, 40):
    # set the pwm settings to 1600 period and specified width
    toaster.set_pwm_settings(1600, width)

    input("Waiting...")
    print("Measuring...")

    # average the raw voltage over avg_count readings
    acc = 0
    for i in range(avg_count):
        acc += toaster.read_voltage_raw()
        sleep(0.05)
    avg = acc / avg_count

    # input the voltage (presumably from a multimeter)
    v = float(input("Voltage: "))

    log.write(f"\{\"value\": {avg}, \"voltage\": {v}\}\n")

log.close()
