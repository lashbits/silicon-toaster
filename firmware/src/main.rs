#![no_std]
#![no_main]

use core::panic::PanicInfo;
use stm32f2::stm32f215;
use cortex_m;
use heapless;

static mut USART1_QUEUE: heapless::spsc::Queue<u8, heapless::consts::U128> =
    heapless::spsc::Queue(heapless::i::Queue::new());

#[panic_handler]
fn panic(_: &PanicInfo) -> ! {
    unsafe {
        // In case of panic, the peripherals may have already been taken, and we
        // cannot take it again... But this is panic, we can do dirty things and
        // call steal to use peripherals anyway!
        // Here we just blink the red LED forever to indicate there is a
        // problem.
        let peripherals = stm32f215::Peripherals::steal();
        set_led_green(&peripherals, false);
        loop {
            for _ in 0..50000 {
                set_led_red(&peripherals, true);
            }
            for _ in 0..50000 {
                set_led_red(&peripherals, false);
            }
        }
    }
}

pub extern "C" fn handler_default() {
    loop {};
}

/// USART interrupt handler. Called in case of data byte reception or overrun.
/// When a byte is received, it is pushed in the USART queue. If the queue is
/// full, the program will panic.
pub extern "C" fn handler_usart1() {
    unsafe {
        let mut producer = USART1_QUEUE.split().0;
        let peripherals = stm32f215::Peripherals::steal();
        if peripherals.USART1.sr.read().rxne().bit() {
            // If queue is full, panic!
            producer.enqueue(peripherals.USART1.dr.read().bits() as u8).unwrap();
        } else {
            // This is probably an overrun error.
            panic!();
        }
    }
}

#[link_section=".isr_vectors.reset"]
#[no_mangle]
pub static reset_vector: unsafe extern "C" fn() -> ! = _start;

#[link_section=".isr_vectors"]
#[no_mangle]
pub static interrupt_vectors: [unsafe extern "C" fn(); 95] = {
    let mut v: [unsafe extern "C" fn(); 95] = [handler_default; 95];
    v[51] = handler_usart1;
    v
};

/// Toggle the red LED on or off.
/// `peripherals` - This method needs to borrow the peripherals.
/// `state` - true to turn on the LED, false to turn off.
fn set_led_red(peripherals: &stm32f215::Peripherals, state: bool) {
    peripherals.GPIOC.odr.modify(|_, w| { w.odr13().bit(state) });
}

/// Toggle the red LED on or off.
/// `peripherals` - This method needs to borrow the peripherals.
/// `state` - true to turn on the LED, false to turn off.
fn set_led_green(peripherals: &stm32f215::Peripherals, state: bool) {
    peripherals.GPIOC.odr.modify(|_, w| { w.odr14().bit(state) });
}

/// Enable or disable on-board 15 V regulator.
/// `peripherals` - This method needs to borrow the peripherals.
/// `state` - true to turn on the regulator, false to turn off.
fn set_15v_regulator(peripherals: &stm32f215::Peripherals, state: bool) {
    peripherals.GPIOB.odr.modify(|_, w| { w.odr11().bit(state) });
}

/// Approximated delay function. Precise enought for what we need to do...
#[inline(never)]
fn delay_ms(duration: u32) {
    // Estimated duration for each loop: 7 clock cycles.
    assert!(duration <= 0xffffffff / 64000);
    let count: u32 = (duration * 64000) / 7;
    for _ in 0..count {
        cortex_m::asm::nop();
    }
}

/// Receives a byte from USART1. Blocks until data is available.
fn usart1_rx() -> u8 {
    unsafe {
        let mut producer = USART1_QUEUE.split().1;
        loop {
            match producer.dequeue() {
                Some(byte) => { return byte; }
                None => {}
            }
        }
    }
}

/// Return true if USART1 has data.
fn usart1_has_data() -> bool {
    unsafe { !USART1_QUEUE.is_empty() }
}

/// Receive a 16-bits unsigned int from USART1. Blocks until all data is
/// available.
fn usart1_rx_u16() -> u16 {
    let h = usart1_rx();
    let l = usart1_rx();
    ((h as u16) << 8) + (l as u16)
}

/// Transmit a byte over USART1.
/// `peripherals` - This method needs to borrow the peripherals.
/// `value` - Byte to be transmitted.
fn usart1_tx(peripherals: &stm32f215::Peripherals, value: u8) {
    peripherals.USART1.dr.write(|w| { w.dr().bits(value as u16) });
    // Wait until byte is transferred into the shift-register.
    while !peripherals.USART1.sr.read().txe().bit() {};
}

/// Transmit a 16-bits word over USART1.
/// `peripherals` - This method needs to borrow the peripherals.
/// `value` - Byte to be transmitted.
fn usart1_tx_u16(peripherals: &stm32f215::Peripherals, value: u16) {
    usart1_tx(peripherals, (value >> 8) as u8);
    usart1_tx(peripherals, (value & 0xff) as u8);
}

/// Enable or disable very-high voltage generation by enabling or disabling the
/// PWM output and the on-board 15 V generator.
/// `peripherals` - This method needs to borrow the peripherals.
/// `state` - true to enable, false to disable.
fn set_high_voltage_generator(peripherals: &stm32f215::Peripherals,
    state: bool){
    // When PWM if off, it seems the output pin is left floating. This is not
    // good because charges will accumulate on the gate of the charge pump
    // transistor, making it always conductive after a while and creating a
    // permanent shortcut. To solve this issue, we force output to zero when
    // high voltage generation if off.
    if state {
        peripherals.TIM1.bdtr.write(|w| { w.moe().set_bit() });
        peripherals.GPIOA.moder.modify(|_, w| { w.moder8().alternate() });
    } else {
        peripherals.GPIOA.odr.modify(|_, w| { w.odr8().clear_bit() });
        peripherals.GPIOA.moder.modify(|_, w| { w.moder8().output() });
        peripherals.TIM1.bdtr.write(|w| { w.moe().clear_bit() });
    }
}

/// Configure PWM parameters for high voltage generation. If the parameters are
/// invalid, this method may panic.
/// `peripherals` - This method needs to borrow the peripherals.
/// `period` - Maximum counter value to the timer. Defines the period of the
///     PWM.
/// `width` - Comparator value for the counter. Defines the PWM positive pulse
///     width.
fn set_pwm_parameters(peripherals: &stm32f215::Peripherals, period: u16,
    width: u16) -> Result<(),()> {
    if width > period {
        return Err(());
    }
    if period == 0 {
        return Err(());
    }
    let tim1 = &peripherals.TIM1;
    tim1.arr.write(|w| { w.arr().bits(period-1) });
    tim1.ccr1.write(|w| { w.ccr().bits(width) });
    Ok(())
}

/// Perform software shoot.
/// `peripherals` - This method needs to borrow the peripherals.
/// `duration` - Pulse duration, in number of program loop.
fn software_shoot(peripherals: &stm32f215::Peripherals, duration: u16){
    let gpioa = &peripherals.GPIOA;
    gpioa.odr.modify(|_, w| { w.odr13().set_bit() });
    for _ in 0..duration {
        cortex_m::asm::nop();
    }
    gpioa.odr.modify(|_, w| { w.odr13().clear_bit() });
}

/// Configure internal Flash memory interface.
/// This changes the Flash latency to be compatible with PLL settings.
fn setup_flash(peripherals: &stm32f215::Peripherals){
    unsafe {
        peripherals.FLASH.acr.modify(|_, w| { w.latency().bits(2) });
    }
}

/// Configure PLL
fn setup_pll(peripherals: &stm32f215::Peripherals){
    let rcc = &peripherals.RCC;
    // Disable PLL
    rcc.cr.modify(|_, w| { w.pllon().clear_bit() });
    // HSI = 16 MHz
    // F = ((HSI (N / M) / P
    // Constraints to be respected:
    // 50 <= N <= 432
    // 2 <= M <= 63
    // Here the target frequency is 64 MHz
    unsafe {
        rcc.pllcfgr.modify(|_, w|
            { w.plln().bits(64).pllm().bits(8).pllp().div2() });
    }
    // Enable PLL and wait it to be locked.
    rcc.cr.modify(|_, w| { w.pllon().set_bit() });
    while !rcc.cr.read().pllrdy().bit() {}
    // Switch to PLL clock
    rcc.cfgr.modify(|_, w| { w.sw().pll() });
}

#[no_mangle]
pub extern "C" fn _start() -> ! {
    // Get .bss segment position for .bss initialization performed in _start.
    extern {
        static _bss: u32;
        static _ebss: u32;
    }
    // Clear RAM of .bss section before doing anything!
    unsafe {
        for i in ((&_bss as *const u32) as u32 .. (&_ebss as *const u32) as u32)
            .step_by(4) {
            core::ptr::write_volatile(i as *mut u32, 0u32);
        }
    }

    let peripherals = stm32f215::Peripherals::take().unwrap();
    setup_flash(&peripherals);
    setup_pll(&peripherals);

    peripherals.RCC.apb2enr.write(|w| { w.usart1en().set_bit() });
    // USART1 uses PA9 for TX and PA10 for RX.
    // LEDs are connected to PC13 and PC14.
    // Enable clock for PORT A, PORT B and PORT C peripherals.
    peripherals.RCC.ahb1enr.write(
        |w| { w.gpioaen().set_bit().gpioben().set_bit().gpiocen().set_bit() } );
    peripherals.GPIOC.moder.modify(
        |_, w| { w.moder13().output().moder14().output() });
    set_15v_regulator(&peripherals, true);
    peripherals.GPIOB.moder.write(|w| { w.moder11().output() });

    // Configure UART1
    // UART Enable, Transmitter Enable, Receiver Enable
    peripherals.USART1.cr1.write(
        |w| { w.ue().set_bit().te().set_bit().re().set_bit() });
    peripherals.USART1.cr2.write(|w|{ w.stop().bits(2) });
    // Baudrate is Fck/(8*(2-OVER8)*DIV)
    // Fck = 64 MHz
    // OVER8 = 0
    // DIV = BRR / 16
    // Here we set 9600 bps
    let brr_value = 6666;
    peripherals.USART1.brr.write(
        |w| { w.div_mantissa().bits(brr_value >> 4)
        .div_fraction().bits((brr_value & 0x0f) as u8) });
    // Select Alternate Function 7 (USART1) for PA9 and PA10.
    let gpioa = &peripherals.GPIOA;
    gpioa.afrh.write(|w| { w.afrh10().af7().afrh9().af7() });
    gpioa.moder.write(|w| { w.moder10().alternate().moder9().alternate() });
    // Configure PA9 and PA10 GPIOs in high frequency
    gpioa.ospeedr.write(
        |w| { w.ospeedr10().very_high_speed().ospeedr9().very_high_speed() });
    // Enable interrupt for USART1
    peripherals.USART1.cr1.modify(|_, w| { w.rxneie().set_bit() });
    unsafe {
        cortex_m::peripheral::NVIC::unmask(stm32f215::Interrupt::USART1);
    }

    // Configure SW_SHOOT signal on pin PA13.
    gpioa.ospeedr.modify(|_, w| { w.ospeedr13().very_high_speed() });
    gpioa.moder.modify(|_, w| { w.moder13().output() });

    // Give some time for the FT232 to boot-up.
    set_led_green(&peripherals, false);
    set_led_red(&peripherals, true);
    delay_ms(500);

    // Configure PWM using TIM1.
    // PWM output on PA8. Alternate Function 1.
    peripherals.RCC.apb2enr.modify(|_, w| { w.tim1en().set_bit() });
    let tim1 = &peripherals.TIM1;
    tim1.cr1.write(|w| { w.cen().set_bit() });
    set_pwm_parameters(&peripherals, 100, 5).unwrap();
    tim1.ccmr1_output().write(|w| { w.oc1m().pwm_mode1() });
    tim1.ccer.write(|w| { w.cc1e().set_bit() });
    gpioa.ospeedr.modify(|_, w| { w.ospeedr8().very_high_speed() });
    gpioa.afrh.modify(|_, w| { w.afrh8().af1() });
    gpioa.moder.modify(|_, w| { w.moder8().alternate() });

    // Configure ADC.
    // Input is PA0.
    peripherals.RCC.apb2enr.modify(|_, w| { w.adc1en().set_bit() });
    gpioa.moder.modify(|_, w| { w.moder0().analog() });
    let adc1 = &peripherals.ADC1;
    adc1.cr2.write(|w| { w.cont().set_bit().adon().set_bit() });
    adc1.cr2.modify(|_, w| { w.swstart().set_bit() });  // Start the conversion
    // I don't understand why the following is unsafe...
    adc1.smpr2.write(|w| { unsafe { w.smp0().bits(7) } });

    let mut high_voltage_enabled = false;
    set_high_voltage_generator(&peripherals, high_voltage_enabled);

    loop
    {
        let adc_result: u16 = adc1.dr.read().data().bits();
        if usart1_has_data()
        {
            let command_byte = usart1_rx();
            match command_byte {
                0x01 => {
                    let value = usart1_rx();
                    assert!(value <= 1);
                    high_voltage_enabled = value != 0;
                    set_high_voltage_generator(&peripherals, high_voltage_enabled);
                    usart1_tx(&peripherals, command_byte);
                },
                0x02 => {
                    usart1_tx_u16(&peripherals, adc_result);
                },
                0x03 => {
                    let period: u16 = usart1_rx_u16();
                    let width: u16 = usart1_rx_u16();
                    usart1_tx(
                        &peripherals,
                        match set_pwm_parameters(&peripherals, period, width) {
                            Ok(_) => command_byte,
                            Err(_) => !command_byte
                        }
                    );
                },
                0x04 => {
                    let duration = usart1_rx_u16();
                    software_shoot(&peripherals, duration);
                    usart1_tx(&peripherals, command_byte);
                },
                _ => {
                    // Unknown command. Panic!
                    panic!();
                }
            }
        }
        let danger: bool = (adc_result >= 67) || high_voltage_enabled;
        set_led_red(&peripherals, danger);
        set_led_green(&peripherals, !danger);
    }
}
