#!/usr/bin/python3
import struct
from typing import Union
import serial
import serial.tools.list_ports


class SiliconToaster:
    def __init__(self, dev=None, sn=None):
        if dev is not None and sn is not None:
            raise ValueError("dev and sn cannot be set together")

        if dev is None:
            # Try to find automatically the device
            possible_ports = []
            for port in serial.tools.list_ports.comports():
                # USB description string is 'SiliconToaster'.
                if (
                    (port.product is not None)
                    and (port.product == "SiliconToaster")
                    and ((sn is None) or (port.serial_number == sn))
                ):
                    possible_ports.append(port)
            if len(possible_ports) > 1:
                raise RuntimeError(
                    "Multiple SiliconToaster devices found! I don't know which one to use."
                )
            elif len(possible_ports) == 1:
                dev = possible_ports[0].device
            else:
                raise RuntimeError("No SiliconToaster device found")

        self.ser = serial.Serial(dev, 9600)
        self.calibration_raw_to_v = [
            -4.02294398e-11,
            1.53492378e-07,
            -2.71166328e-04,
            7.66927146e-01,
            -1.12729564e00,
        ]
        self.calibration_v_to_raw = [
            5.59972560e-10,
            -1.02408301e-06,
            1.06453179e-03,
            1.24457162e00,
            2.57379247e00,
        ]
        self._software_limit = None
        self.set_adc_control_on_off(True)

    @staticmethod
    def convert(value: Union[float, int], calibration: list[float]) -> float:
        """Converts a value to another according to the calibration coefficients"""
        v = 0.0
        value = float(value)
        for i, c in enumerate(calibration):
            v += c * value ** (len(calibration) - i - 1)
        return v

    def to_raw(self, value: float) -> int:
        return int(round(self.convert(value, self.calibration_v_to_raw)))

    def to_volt(self, value: int) -> float:
        return self.convert(value, self.calibration_raw_to_v)

    def read_voltage_raw(self) -> int:
        """
        Retrieve raw ADC voltage measurement from the device.
        :return: ADC measurement.
        :rtype: int
        """
        self.ser.write(b"\x02")
        assert self.ser.read(1) == b"\x02"
        return int.from_bytes(self.ser.read(2), "big", signed=False)

    def read_voltage(self) -> float:
        """
        Retrieve voltage measurement from the device.
        :return: Voltage measurement.
        :rtype: float
        """
        raw = self.read_voltage_raw()
        v = self.to_volt(raw)
        return v

    def on_off(self, enable: bool):
        """
        Turn on or off high-voltage generation.

        :param enable: True or False to enable or disable the high-voltage generation.
        """
        command = b"\x01" + (b"\1" if enable else b"\0")
        self.ser.write(command)
        assert self.ser.read(1) == b"\x01"

    def set_pwm_settings(self, period: int, width: int):
        """
        Reconfigure PWM settings.

        :param period: Timer max counter value for PWM generation. Defines the
            period.
        :param width: Timer comparator value for PWM generation. Defines the
            pulse width.
        """
        if period < 1:
            raise ValueError("Invalid PWM period: it must be greater or equal to 1")
        if width < 0:
            raise ValueError("Invalid PWM width: it must be positive")
        if width >= period:
            raise ValueError(
                "Invalid PWM settings values: width must be lesser than period"
            )
        command = bytearray(b"\x03")
        command += period.to_bytes(2, "big", signed=False)
        command += width.to_bytes(2, "big", signed=False)
        self.ser.write(command)
        assert self.ser.read(1) == b"\x03"

    def software_shoot(self, duration: int):
        """
        Generate a pulse with the device to discharge de capacitors.
        """
        if duration not in range(0x10000):
            raise ValueError(
                f"Invalid software shoot duration: it must be lesser than {0x10000}"
            )
        command = bytearray(b"\x04")
        command += duration.to_bytes(2, "big", signed=False)
        self.ser.write(command)
        assert self.ser.read(1) == b"\x04"

    def get_ticks(self) -> int:
        """
        Get the timestamp in number of ticks, since the powerup of the silicon toaster.

        :return: The timestamp value
        """
        self.ser.write(b"\x05")
        assert self.ser.read(1) == b"\x05"
        return int.from_bytes(self.ser.read(8), "big")

    def get_voltage_setpoint(self) -> float:
        """
        Get the ADC Control's set point and return the corresponding voltage value.

        :return: The configured voltage value to aim through the ADC Control.
        """
        self.ser.write(b"\x06")
        assert self.ser.read(1) == b"\x06"
        destination = struct.unpack(">H", self.ser.read(2))[0]
        return self.to_volt(destination)

    def set_voltage_setpoint(self, destination: float):
        """
        Set the ADC Control's set point to aim the given voltage.

        :param destination: The desired voltage.
        """
        command = b"\x07"
        command += struct.pack(">H", self.to_raw(destination))
        self.ser.write(command)
        assert self.ser.read(1) == b"\x07"

    def get_pwm_settings(self) -> tuple[int, int]:
        """
        Retrieve the last values set for PWM.

        :return: A tuple containing the period and the width.
        """
        self.ser.write(b"\x08")
        assert self.ser.read(1) == b"\x08"
        period = int.from_bytes(self.ser.read(2), "big", signed=False)
        width = int.from_bytes(self.ser.read(2), "big", signed=False)
        return period, width

    def get_adc_control_pid(self, from_flash=False):
        """
        Get ADC control PID.

        :return: A tuple containing the period and the width.
        """
        command = b"\x0A"
        command += struct.pack(">?", from_flash)
        self.ser.write(command)
        assert self.ser.read(1) == b"\x0A"
        return struct.unpack(">3fQ", self.ser.read(3 * 4 + 8))

    def set_adc_control_pid(
        self,
        kp: float,
        ki: float,
        kd: float,
        control_ticks: int,
        to_flash=False,
    ):
        command = b"\x0B"
        command += struct.pack(">?3fQ", to_flash, kp, ki, kd, control_ticks)
        self.ser.write(command)
        assert self.ser.read(1) == b"\x0B"

    def get_adc_control_pid_ex(self):
        """
        Retrieve supplementary values of configuration and information of the ADC Control.
        Those values are transient.

        :return: A tuple containing the configuration of the PID:
            The PID limitations of value contributed by Kp, Ki and Kd.
            The PID's output limit. The PID setpoint (float). The timestamp (
            in ticks) of last PID sampling.
        """
        command = b"\x0D"
        self.ser.write(command)
        assert self.ser.read(1) == b"\x0D"
        return struct.unpack(">5fQ", self.ser.read(5 * 4 + 8))

    def set_adc_control_pid_ex(
        self, p_limit: float, i_limit: float, d_limit: float, output_limit: float
    ):
        """
        Set supplementary values of configuration of the ADC Control.
        Those values are transient and are reset to their default values on startup.
        :param p_limit: PID limitation of value contributed by Kp. Default is 200.0.
        :param i_limit: PID limitation of value contributed by Ki. Default is 200.0.
        :param d_limit: PID limitation of value contributed by Kd. Default is 200.0.
        :param output_limit: PID limitation of output value. Default is 200.0.
        """
        command = b"\x0C"
        command += struct.pack(">4f", p_limit, i_limit, d_limit, output_limit)
        self.ser.write(command)
        assert self.ser.read(1) == b"\x0C"

    def set_adc_control_on_off(self, enable: bool):
        """
        Turn on or off of the ADC Control.
        :param enable: True or False to enable or disable the of the ADC Control.
        """
        command = b"\xAA" + (b"\1" if enable else b"\0")
        self.ser.write(command)
        assert self.ser.read(1) == b"\xAA"

    def adc_control_on_off(self) -> bool:
        """
        Give information if ADC Control is enabled or not.

        :return: True or False to enable or disable the of the ADC Control.
        """
        command = b"\xAB"
        self.ser.write(command)
        assert self.ser.read(1) == b"\xAB"
        return self.ser.read(1) == b"\x01"

    def panic(self):
        """
        Send an illegal command in order to enter in the panic()
        """
        command = b"\x77"
        self.ser.write(command)
        assert self.ser.read(1) == b"\x77"

    def adc_results(self) -> int:
        """
        Get values of ADC values passed to PID.
        """
        command = b"\xAC"
        self.ser.write(command)
        assert self.ser.read(1) == b"\xAC"
        v = struct.unpack(">I", self.ser.read(4))[0]
        print(v)
        return struct.unpack(f">{v}H", self.ser.read(v * 2))

    def get_last_error(self) -> int:
        """
        Get the error counter, and acknowledges it (reset to zero).

        :return: Error counter value.
        """
        command = b"\xEE"
        self.ser.write(command)
        assert self.ser.read(1) == b"\xEE"
        return int.from_bytes(self.ser.read(2), "big")

    def __del__(self):
        self.on_off(False)
