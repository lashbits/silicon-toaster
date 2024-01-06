//! ADC control structure to manage the targeted value of the ADC, using the system timer, and
//! a Pid.

use crate::Flash;
use crate::SystemTimer;
use pid::Pid;

pub struct ADCControl {
    pub enabled: bool,
    /// Time interval between two controls in systimer ticks.
    pub control_ticks: u64,
    pub last_control: u64,
    pub pid: Pid<f32>,
}

impl ADCControl {
    /// Magic value in flash to indicate that it contains data.
    const DATA_MAGIC: u32 = 0x444E4A4E;
    /// The sector where the data will be serialized.
    const FLASH_SECTOR: u8 = 3;
    /// The amount of time between control updates.
    const CONTROL_DELTA: u64 = 1000; // ~ 1ms

    pub fn new() -> ADCControl {
        let mut adc = ADCControl {
            enabled: true,
            control_ticks: SystemTimer::FREQ / Self::CONTROL_DELTA,
            last_control: 0,
            pid: Pid::new(
                100.0, /* kp */
                0.0,   /* ki */
                0.0,   /* kd */
                200.0, /* p_limit */
                200.0, /* i_limit */
                200.0, /* d_limit */
                200.0, /* output_limit */
                0.0,   /* setpoint */
            ),
        };
        adc.read_from_flash();
        adc
    }

    pub fn next_control_output(&mut self, adc_result: u16, ticks: u64) -> u16 {
        // Updates the last control time and requests for next control value from PID
        self.last_control = ticks;
        // The PID object will give a value between -output_limit and output_limit
        // This seems to be broken. Sometimes the value gets out of output_limit bounds.
        let mut output = self.pid.next_control_output(adc_result as f32).output;
        let sig = if output >= 0.0f32 { 1.0 } else { -1.0 };
        let abs = output * sig;
        output = self.pid.output_limit.min(abs) * sig;
        return (output + self.pid.output_limit) as u16;
    }

    /// Returns true if
    ///     control is enabled
    ///     the delta between `ticks` and the last update is more than 1ms
    pub fn needs_control(&self, ticks: u64) -> bool {
        self.enabled && (ticks.abs_diff(self.last_control) > self.control_ticks)
    }

    // Getter for setpoint for the Controller.
    pub fn setpoint(&self) -> u16 {
        self.pid.setpoint as u16
    }

    // Setter for setpoint for the Controller.
    pub fn set_setpoint(&mut self, setpoint: u16) {
        self.pid.setpoint = setpoint as f32;
        self.pid.reset_integral_term();
    }

    pub fn read_from_flash(&mut self) {
        let address: *const u32 = Flash::base_address_for_sector(Self::FLASH_SECTOR);
        unsafe {
            if address.read() != Self::DATA_MAGIC {
                return;
            }

            self.pid.kp = f32::from_bits(address.offset(1).read());
            self.pid.ki = f32::from_bits(address.offset(2).read());
            self.pid.kd = f32::from_bits(address.offset(3).read());
            let h = address.offset(4).read() as u64;
            let l = address.offset(5).read() as u64;
            self.control_ticks = (h << 32) + l;
        }
    }

    pub fn store_in_flash(&self, flash: &Flash) {
        flash.flash_erase_sector(Self::FLASH_SECTOR);

        let base: *mut u32 = Flash::base_address_for_sector(Self::FLASH_SECTOR);

        let values = [
            Self::DATA_MAGIC,
            self.pid.kp.to_bits(),
            self.pid.ki.to_bits(),
            self.pid.kd.to_bits(),
            (self.control_ticks >> 32) as u32,
            (self.control_ticks & 0xffffffff) as u32,
        ];

        flash.flash_program(base, values.as_ptr(), values.len() as isize);
    }
}
