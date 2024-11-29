import matplotlib.pyplot as plt
import numpy as np
import re


def read_calibration_data():
    with open("calibration-800.log", "r") as f:
        calibration_data = f.read()

    values = []
    voltages = []
    for line in calibration_data.split('\n'):
        if not line:
            continue

        result = re.match(
            r"{\"value\"\: (?P<value>.*), \"voltage\"\: (?P<voltage>.+)}",
            line)

        assert result is not None, f"Invalid line '{line}'"

        values.append(float(result.group('value')))
        voltages.append(float(result.group('voltage')))

    return values, voltages


def test_plots(values, voltages, coefs, coefs_inv):
    # Test the values to voltages polynomial
    # Generate 100 linearly spaced values
    values_test = np.linspace(0, max(values), 100)
    # Calculate the associated voltage for each value point
    voltages_test = []
    for value in values_test:
        v = 0
        for i, c in enumerate(coefs):
            v += c * pow(value, len(coefs) - i - 1)
        voltages_test.append(v)

    # Test the voltages to values polynomial
    # Generate 100 linearly spaced voltages
    voltages_inv_test = np.linspace(0, max(voltages), 100)
    # calculate the associated x for each y point
    values_inv_test = []
    for voltage in voltages_inv_test:
        v = 0
        for i, c in enumerate(coefs_inv):
            v += c * pow(voltage, len(coefs_inv) - i - 1)
        values_inv_test.append(v)

    # Plot the original data from the SiliconToaster
    plt.figure()
    plt.plot(values, voltages)

    # Plot the new data, which should be identical to the original plot
    plt.figure()
    plt.plot(values_test, voltages_test)
    plt.figure()
    plt.plot(values_inv_test, voltages_inv_test)

    # Show the matplotlib figures
    plt.show()


def main():
    values, voltages = read_calibration_data()

    # Fit the values to voltages using a 4 degree polynomial
    coefs = np.polyfit(values, voltages, 4)
    poly = np.poly1d(coefs)
    print("Raw->Volt", coefs)

    # Fit the voltages to values using a 4 degree polynomial
    coefs_inv = np.polyfit(voltages, values, 4)
    poly_inv = np.poly1d(coefs_inv)
    print("Volt->Raw", coefs_inv)

    #test_plots(values, voltages, coefs, coefs_inv)


if __name__ == "__main__":
    main()
