import sys

from silicontoaster import SiliconToaster
from time import sleep


def calibrate(toaster, log):
    print("Turning on the device")
    toaster.on_off(True)

    avg_count = 100
    for width in range(1, 40):
        toaster.set_pwm_settings(800, width)

        input("Waiting for the DMM reading to stabilize...")
        print("Measuring...")

        # Average the raw voltage over avg_count readings
        acc = 0
        for i in range(avg_count):
            acc += toaster._read_voltage_raw()
            sleep(0.05)
        avg = acc / avg_count

        print(f"Measured average: {avg}")

        v = float(input("DMM voltage reading: "))
        log.write(f'{{"value": {avg}, "voltage": {v}}}\n')


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [path to /dev/ttyXXX]")
        return

    toaster = SiliconToaster(sys.argv[1], adc_control=False)

    # Display the current settings.
    period, width = toaster.get_pwm_settings()
    print(f"PWM period {period}, width {width}")

    if period != 800:
        print("PWM period is different than 800 (default value)")

    if width != 0:
        print("Setting PWM width to 0")
        toaster.set_pwm_settings(period, 0)

    with open(f"calibration-{period}.log", "w") as log:
        calibrate(toaster, log)


if __name__ == "__main__":
    main()
