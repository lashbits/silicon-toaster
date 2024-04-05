#!/usr/bin/python3

import matplotlib.pyplot as plt
import numpy as np
import re

x = []
y = []

with open("calibration-800.log", "r") as f:
    calibration_data = f.read()
for line in calibration_data.split('\n'):
    result = re.match(
        r"{\"value\"\: (?P<value>.*), \"voltage\"\: (?P<voltage>.+)}", line)
    if result:
        x.append(float(result.group('value')))
        y.append(float(result.group('voltage')))

# plot the original data from the silicontoaster
plt.figure()
plt.plot(x, y)

# fit the x to y using a 4 degree polynomial
coefs = np.polyfit(x, y, 4)
poly = np.poly1d(coefs)
print("Raw->Volt", coefs)

# fir the y to x using a 4 degree polynomial
coefs_inv = np.polyfit(y, x, 4)
poly_inv = np.poly1d(coefs_inv)
print("Volt->Raw", coefs_inv)

# test the x to y polynomial
# generate a new x with 100 linearly spaced points
x = np.linspace(0, max(x), 100)
# calculate the associated y for each x point
y = []
for xx in x:
    v = 0
    for i, c in enumerate(coefs):
        v += c * xx**(len(coefs) - i - 1)
    y.append(v)

# plot the new data, which should be identical to the original plot
plt.figure()
plt.plot(x, y)

# test the y to x polynomial
# generate a new y with 100 linearly spaced points
y = np.linspace(0, max(y), 100)
# calculate the associated x for each y point
x = []
for yy in y:
    v = 0
    for i, c in enumerate(coefs_inv):
        v += c * yy**(len(coefs_inv) - i - 1)
    x.append(v)

# plot the new data, which should be identical to the original plot
plt.figure()
plt.plot(x, y)

plt.show()
