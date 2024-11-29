import struct
import time
from typing import Union
import anomaly.util.logging

import serial


class SiliconToaster:

    # these are coefficients calculated using the calibration scripts
    CALIBRATION_RAW_TO_V = [
        -4.02294398e-11,
        1.53492378e-07,
        -2.71166328e-04,
        7.66927146e-01,
        -1.12729564e00,
    ]
    CALIBRATION_V_TO_RAW = [
        5.59972560e-10,
        -1.02408301e-06,
        1.06453179e-03,
        1.24457162e00,
        2.57379247e00,
    ]

    def __init__(self, dev):
        self._logger = anomaly.util.logging.new_logger(__name__)

        self.ser = serial.Serial(dev, baudrate=9600, timeout=1)
        self.set_adc_control_on_off(True)

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.ser.close()

    def close(self):
        self.ser.close()

    def _ser_write(self, data):
        self.ser.write(data)
        time.sleep(0.1)

    def _ser_read(self, size=1):
        return self.ser.read(size)

    def _verify_response(self, expected: [bytes, bytearray]):
        received = self._ser_read(len(expected))
        if received != expected:
            if len(received) == 0:
                self._logger.error(f"expected {expected.hex()} but received no response")
            else:
                self._logger.error(f"expected {expected.hex()} but received {received.hex()}")
            raise RuntimeError("received data is not what was expected")

    @staticmethod
    def _convert(value: Union[float, int], calibration: list[float]) -> float:
        """
        Converts a value to another according to the calibration coefficients.
        """
        v = 0.0
        value = float(value)
        for i, c in enumerate(calibration):
            v += c * value**(len(calibration) - i - 1)
        return v

    def _to_raw(self, value: float) -> int:
        return int(round(SiliconToaster._convert(value, SiliconToaster.CALIBRATION_V_TO_RAW)))

    def _to_volt(self, value: int) -> float:
        return SiliconToaster._convert(value, SiliconToaster.CALIBRATION_RAW_TO_V)

    def _read_voltage_raw(self) -> int:
        """
        Retrieve raw ADC voltage measurement from the device.
        :return: ADC measurement.
        :rtype: int
        """
        self._ser_write(b"\x02")
        self._verify_response(b"\x02")
        return int.from_bytes(self._ser_read(2), "big", signed=False)

    def read_voltage(self) -> float:
        """
        Retrieve voltage measurement from the device.
        :return: Voltage measurement.
        :rtype: float
        """
        raw = self._read_voltage_raw()
        v = self._to_volt(raw)
        return v

    def on_off(self, enable: bool):
        """
        Turn on or off high-voltage generation.

        :param enable: True or False to enable or disable the high-voltage generation.
        """
        command = b"\x01" + (b"\1" if enable else b"\0")
        self._ser_write(command)
        self._verify_response(b"\x01")

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
            raise ValueError("Invalid PWM settings values: width must be lesser than period")
        command = bytearray(b"\x03")
        command += period.to_bytes(2, "big", signed=False)
        command += width.to_bytes(2, "big", signed=False)
        self._ser_write(command)
        self._verify_response(b"\x03")

    def software_shoot(self, duration: int):
        """
        Generate a pulse with the device to discharge de capacitors.
        """
        if duration not in range(0x10000):
            raise ValueError(f"Invalid software shoot duration: it must be lesser than {0x10000}")
        command = bytearray(b"\x04")
        command += duration.to_bytes(2, "big", signed=False)
        self._ser_write(command)
        self._verify_response(b"\x04")

    def get_ticks(self) -> int:
        """
        Get the timestamp in number of ticks, since the powerup of the silicon toaster.

        :return: The timestamp value
        """
        self._ser_write(b"\x05")
        self._verify_response(b"\x05")
        return int.from_bytes(self._ser_read(8), "big")

    def get_voltage_setpoint(self) -> float:
        """
        Get the ADC Control's set point and return the corresponding voltage value.

        :return: The configured voltage value to aim through the ADC Control.
        """
        self._ser_write(b"\x06")
        self._verify_response(b"\x06")
        destination = struct.unpack(">H", self._ser_read(2))[0]
        return self._to_volt(destination)

    def set_voltage_setpoint(self, destination: float):
        """
        Set the ADC Control's set point to aim the given voltage.

        :param destination: The desired voltage.
        """
        assert 0 <= destination <= 1000

        command = b"\x07"
        command += struct.pack(">H", self._to_raw(destination))
        self._ser_write(command)
        self._verify_response(b"\x07")

    def get_pwm_settings(self) -> tuple[int, int]:
        """
        Retrieve the last values set for PWM.

        :return: A tuple containing the period and the width.
        """
        self._ser_write(b"\x08")
        self._verify_response(b"\x08")
        period = int.from_bytes(self._ser_read(2), "big", signed=False)
        width = int.from_bytes(self._ser_read(2), "big", signed=False)
        return period, width

    def get_adc_control_pid(self, from_flash=False):
        """
        Get ADC control PID.

        :return: A tuple containing the period and the width.
        """
        command = b"\x0A"
        command += struct.pack(">?", from_flash)
        self._ser_write(command)
        self._verify_response(b"\x0A")
        return struct.unpack(">3fQ", self._ser_read(3 * 4 + 8))

    # TODO fix pylint
    #pylint: disable=too-many-arguments, too-many-positional-arguments
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
        self._ser_write(command)
        self._verify_response(b"\x0B")

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
        self._ser_write(command)
        self._verify_response(b"\x0D")
        return struct.unpack(">5fQ", self._ser_read(5 * 4 + 8))

    def set_adc_control_pid_ex(self, p_limit: float, i_limit: float, d_limit: float, output_limit: float):
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
        self._ser_write(command)
        self._verify_response(b"\x0C")

    def set_adc_control_on_off(self, enable: bool):
        """
        Turn on or off of the ADC Control.
        :param enable: True or False to enable or disable the of the ADC Control.
        """
        command = b"\xAA" + (b"\1" if enable else b"\0")
        self._ser_write(command)
        self._verify_response(b"\xAA")

    def adc_control_on_off(self) -> bool:
        """
        Give information if ADC Control is enabled or not.

        :return: True or False to enable or disable the of the ADC Control.
        """
        command = b"\xAB"
        self._ser_write(command)
        self._verify_response(b"\xAB")
        return self._ser_read(1) == b"\x01"

    def panic(self):
        """
        Send an illegal command in order to enter in the panic()
        """
        command = b"\x77"
        self._ser_write(command)
        self._verify_response(b"\x77")

    def adc_results(self) -> int:
        """
        Get values of ADC values passed to PID.
        """
        command = b"\xAC"
        self._ser_write(command)
        self._verify_response(b"\xAC")
        v = struct.unpack(">I", self._ser_read(4))[0]
        print(v)
        return struct.unpack(f">{v}H", self._ser_read(v * 2))

    def get_last_error(self) -> int:
        """
        Get the error counter, and acknowledges it (reset to zero).

        :return: Error counter value.
        """
        command = b"\xEE"
        self._ser_write(command)
        self._verify_response(b"\xEE")
        return int.from_bytes(self._ser_read(2), "big")

    def __del__(self):
        self.on_off(False)
