# Credits and third-party components

This core combines new RTL with proven open-source components. Every
third-party component retains its own license and copyright headers in
place; the combined work is distributed under GPL-3.0-or-later (see
LICENSE). Local modifications to vendored cores are documented in each
component's `PROVENANCE.md`.

## New work in this repository

- Video (`rtl/d8_video.sv`, `rtl/d8_fifo.sv`, `rtl/d8_dpram.sv`,
  `rtl/d8_snapram.sv`): line renderer for the background and text
  tilemaps, both Data East sprite chips and the palette.
  GPL-3.0-or-later.
- System glue (`rtl/d8_sys.sv`), MCU glue (`rtl/d8_mcu.sv`), sound board
  (`rtl/d8_snd.sv`), Gondomania rotary input (`rtl/d8_rotary.sv`), SDRAM
  controller (`rtl/d8_sdram.sv`), board wrapper (`rtl/d8_board.sv`),
  MiSTer shell (`Arcade-DEC8.sv`), simulation and verification harness
  (`sim/`), tooling (`tools/`). GPL-3.0-or-later.

## Vendored cores (`rtl/vendor/`)

| Component | Author | License | Upstream |
|---|---|---|---|
| mc6809i (6809 / 6809E, cycle-accurate) | Greg Miller; clock-enable version by Jose Tejada in jtframe | BSD-3-Clause (jtframe additions GPL-3.0-or-later) | https://github.com/cavnex/mc6809, https://github.com/jotego/jtcores |
| jt8051 (Intel 8751 MCU) | Jose Tejada (@topapate / jotego) | GPL-3.0-or-later | https://github.com/jotego/jtcores |
| jt65c02 (6502 / 65C02, DECO 222 mode) | Jose Tejada (@topapate / jotego) | GPL-3.0-or-later | https://github.com/jotego/jtcores |
| jt03 (YM2203) with jt49 (its SSG) | Jose Tejada (@topapate / jotego) | GPL-3.0 | https://github.com/jotego/jt12, https://github.com/jotego/jt49 |
| jtopl (YM3526 / YM3812) | Jose Tejada (@topapate / jotego) | GPL-3.0-or-later | https://github.com/jotego/jtopl |

Local changes:

- mc6809i: not modified (the jtframe copy's behaviour differences from
  the original are listed in `rtl/vendor/mc6809i/PROVENANCE.md`).
- jt8051: two interface additions for the DEC8 MCU glue (port write
  events, MAME's forced P0 input) and a microcode path macro; no change
  to the CPU's behaviour (`rtl/vendor/jt8051/PROVENANCE.md`).
- jt65c02: microcode regenerated with two cycle-count fixes to the 6502
  data sheets (ADC/SBC, untaken branches) and a microcode path macro
  (`rtl/vendor/jt65c02/PROVENANCE.md`), confirmed by an independent
  audit (`docs/jt65c02_cycle_audit.md`).
- jt03 and jtopl: unchanged.

The 8751, sound CPU and sound chips come from Jose Tejada's cores. If you
enjoy this core, consider supporting him: https://www.patreon.com/jotego

## MiSTer framework (`sys/`)

The MiSTer template and framework files are copyright their respective
authors (Sorgelig and MiSTer-devel contributors), GPL-2.0-or-later.
https://github.com/MiSTer-devel

## Reference material

- MAME's DEC8 driver and devices (`dataeast/dec8.cpp`, `dec8_v.cpp`,
  `decbac06.cpp`, `decmxc06.cpp`, `decrmc3.cpp`, `deco222.cpp`; copyright
  Bryan McPhail, Stephane Humbert, David Haywood and contributors),
  BSD-3-Clause, are vendored under `reference/mame/` as the behavioural
  documentation of record. This core would not exist without that work.
  https://github.com/mamedev/mame
- Data East USA's Last Mission and Gondomania operator manuals with
  schematics (board wiring, mixing network, DIP switches).

## The games

The games are copyright Data East. This repository contains no game ROM
data in any form; the core loads a user-supplied MAME ROM set at runtime
via the MRA files.
