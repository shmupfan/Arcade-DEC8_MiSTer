# jt65c02 cycle tests (R17)

Stand-alone Verilator benches for the sound CPU (rtl/vendor/jt65c02) against
the Rockwell R65C02 data sheet (R65C00 family, Instruction Set Op Code
Matrix, p. 1-11; mister-arcade-survey/datasheets/r65c02/).

- tb_6502.sv: ADC/SBC results in binary and decimal mode, and the cycle count
  of ADC/SBC + STA zp pairs (binary 5/6, decimal 6/6/7 per the data sheet).
- tb_6502e.sv: per-instruction cycles measured as (16 reps - 8 reps) / 8,
  which cancels fetch-timing edge effects: branches, indexed and indirect
  modes with and without page crossings.
- tb_6502b/c/d.sv: earlier single-pass variants (edge effects included).

Build, from this folder (V = ../../../rtl/vendor/jt65c02):

    verilator --binary -Wno-fatal -Wno-lint -Wno-style -Wno-WIDTH \
      --top-module tb_6502e -I$V -DSIMULATION \
      -DJT65C02_UCFILE="\"$V/deco222.uc\"" tb_6502e.sv \
      $V/jt65c02.v $V/jt65c02_ctrl.v $V/jt65c02_alu.v $V/jt65c02_regs.v -Mdir obje
    ./obje/Vtb_6502e
