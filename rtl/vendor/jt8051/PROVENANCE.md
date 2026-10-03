# jt8051 (Intel 8051/8751 MCU core)

Source: jotego/jtcores master a72a4460d6b762b8a6b63e76785405f72b440a49
(fetched 2026-10-03), `modules/jt8051/hdl/` (jt8051.v, jt8051_alu.v,
jt8051_ctrl.v, jt8051_periph.v, jt8051_regs.v, jt8051_serial.v),
`modules/jt8051/ucode/8051.yaml`, `modules/jt8051/README.md`. Author Jose
Tejada Gomez. Licence GPL-3.0-or-later (SPDX headers; LICENSE copied from the
jtcores repository root).

Generated files: `jt8051.vh`, `jt8051_param.vh`, `jt8051.uc` are the
microcode tables the core includes. jtcores does not ship them (they are in
its .gitignore); they were produced from `ucode/8051.yaml` with jtframe's
ucode generator (jtcores `modules/jtframe/src/jtframe/ucode/ucode.go`, same
commit), built locally as `tools/uctool` (a 30-line driver around that
package, Go 1.27.1, sprig v2.22.0, yaml.v2 v2.4.0), equivalent to
`jtframe ucode --output jt8051 jt8051 8051`:

    cd tools/uctool && go build -o uctool .
    mkdir -p /tmp/m/jt8051/ucode /tmp/j/src/jtframe/ucode
    cp ../../rtl/vendor/jt8051/ucode/8051.yaml /tmp/m/jt8051/ucode/
    cp ucode/ucode.vh ucode/ucparam.vh /tmp/j/src/jtframe/ucode/
    MODULES=/tmp/m JTFRAME=/tmp/j ./uctool jt8051 jt8051 8051.yaml

The generator printed no "not cycle-accurate" warning (every instruction in
8051.yaml has the documented machine-cycle count).

## DEC8 patches (all marked "DEC8 patch" in the source)

1. `jt8051.v`: outputs `sfr_wr`, `sfr_wa`, `sfr_wd` (the SFR write strobe,
   address and data, `sfr_wr` qualified with `cen`). MAME calls the port
   output callbacks on every write to P0-P3, including writes of an unchanged
   value (i8051.cpp:287-313), and the DEC8 MCU glue acts on such writes
   (dec8.cpp:732-766: P2.0/P2.1 low clear INT0/INT1 on any write); the
   wrapper needs the write events, not only the latch value. No change to
   the CPU's behaviour.
2. `jt8051.v`, `jt8051_periph.v`: input `p0_force`; a P0 pin read returns
   `(latch | p0_force) & p0_i`, MAME's `p0_r` with `m_forced_inputs[0]`
   (i8051.cpp:282-285). Last Mission's glue sets the forced input to the
   latched main-CPU value on every P2.4 falling edge because "lastmisn mcu
   sets p0 to 0x00" (dec8.cpp:740-746). Tied to 0 the core is unchanged.
   Whether the real board's P0 behaves this way (the 8751's P0 is open drain;
   a MOVX would rewrite the latch with 1s) is research item R13.
3. `jt8051.vh` (generated): `$readmemb` takes the microcode file from the
   macro `JT8051_UCFILE` when the build defines it (Verilator runs from a
   different directory); the default path is unchanged.
