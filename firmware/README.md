# Build instructions

First ensure that you have the `thumbv6m-none-eabi` target installed for rust:

```sh
$: rustup target add thumbv6m-none-eabi
```

Afterwards, install the `cargo-binutils` package:

```sh
$: cargo install cargo-binutils
$: rustup component add llvm-tools
```

Last step is to run `make`.

# Flashing

Flashing is done with the `stm32flash` utility. It can be obtained from [sourceforge](https://sourceforge.net/projects/stm32flash/).

```sh
$: git clone https://git.code.sf.net/p/stm32flash/code stm32flash
$: cd stm32flash
$: make
```
