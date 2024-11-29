# Calibration scripts

1. Run the `calibrate.py` script

```sh
python calibrate.py /dev/tty.usbserial-...
```

This will create the `calibration-800.log` file based on the DMM and averaged ADC readings.

The current file was created with the jumper on on 3v3 (not that it should make a difference).

2. Run the `plot-calibration.py` to calculate the polynomial coefficients. These coefficients are then used in the
python package.

```sh
python plot-calibration.py
```

3. Use the `tool.py` script together with a DMM to check that things works as they should.

```sh
QT_QPA_PLATFORM=cocoa python tool.py /dev/tty.usbserial-...
```
