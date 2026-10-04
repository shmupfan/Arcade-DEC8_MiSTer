# jt65c02 (6502 / 65C02, DECO 222 mode)

Source: jotego/jtcores, commit a72a4460d6b762b8a6b63e76785405f72b440a49, `modules/jt680x`
(jt65c02.v, jt65c02_ctrl.v, jt65c02_alu.v, jt65c02_regs.v), fetched
2026-10-03 with git. Copyright Jose Tejada Gomez, GPL-3.0-or-later (SPDX
headers in each file; LICENSE = jtcores' GPL-3.0 text).

Microcode: generated with jtframe's `ucode` command (jtcores
`modules/jtframe/src/jtframe`, same commit, built locally with Go 1.27)
from `ucode/deco222.yaml` (jt680x's file; it includes `65c02.yaml` and
adds the DECO 222's two-to-four byte NOPs on opcodes the 65C02 leaves
undefined). Output: `65c02.vh`, `65c02_param.vh`, `deco222.uc`. The
generator reported no instruction that is not cycle-accurate to the YAML.
The plain 65C02 build (`ucode/65c02_only.*`) is kept for reference only.
One table serves all three machines: the extra NOPs are opcodes that the
Last Mission and Gondomania sound programs never execute (MAME debugger
traces of 2,400 frames each, docs/m3_findings.md 2).

Local change: `65c02.vh` reads its microcode file through the macro
`JT65C02_UCFILE` (default "deco222.uc") so the simulation and Quartus can
point at it by path; the generated file named it by bare file name.

Used by rtl/d8_snd.sv with `DECO222=1` and `opdec` high on srdarwin
(opcode bits 5 and 6 swapped on opcode fetches, as MAME's deco222.cpp:34).

## Local change 2 (2026-10-04, R17): ADC/SBC binary-mode cycle count

Upstream `ucode/65c02.yaml` declared every ADC and SBC one cycle longer
than the Rockwell R65C02 data sheet ("ADC and SBC contain one extra cycle
to cover the case with decimal adjustment") and padded the shared ADC/SBC
sequence with three idle microsteps, so binary-mode ADC/SBC took the
decimal cycle too, and decimal mode took two extra cycles instead of one.
The data sheet (R65C00 family, Instruction Set Op Code Matrix, p. 1-11;
datasheets/r65c02/rockwell_r65c00_microprocessors.pdf) gives ADC/SBC
(ind,x) 6, (ind),y 5*, (ind) 5, zp 3, zp,x 4, imm 2, abs,y 4*, abs 4,
abs,x 4* cycles, with "Add 1 to N if in decimal mode". Change: those
counts declared, and the ALU step plus the conditional BCD jump placed on
the step after the fetch, as for every other ALU instruction; the daa/das
subroutine (taken only when D=1) supplies the decimal cycle. Regenerated
with the same jtframe ucode package (the unchanged YAML reproduces the
previous deco222.uc byte for byte); `65c02_param.vh` and `65c02.vh` are
unchanged; `deco222.uc` md5 a6b11e7f6e81e6121d776f4feb4742c2 ->
fffe818eb8034b4d9f07724f572f0d6e (with change 3 below). Verified by sim/m3/cputest/tb_6502.sv:
ADC/SBC + STA pairs 5/6/6/6/7 cycles in binary/decimal (data sheet),
5/6 previously all +1; BCD results unchanged.

## Local change 3 (2026-10-04, R17): not-taken branches 2 cycles

The ucode generator pads an instruction whose body is shorter than its
declared cycle count with idle steps at the FRONT of the body
(`fix_cycles`). The branch body was 11 microsteps against the declared 3
cycles (12), so one idle step preceded the condition test, and the
not-taken exit (`nobr` -> `nobranch`) took 9 microsteps: 2.25 bus cycles
instead of the data sheet's 2 (Bcc "2 2**", ** = add 1 if taken to the
same page, 2 to a different page). Change: one idle step added in the
taken-only part of the branch sequence (body 12 steps, no front padding).
Measured (sim/m3/cputest/tb_6502e.sv, 16 minus 8 repetitions): not taken
2.000, taken same page 3.000 (were 2.250 and 3.000).

## Known remaining deviations (not changed; research item R21)

Measured with tb_6502e.sv against the same data sheet matrix:
- STA abs,X / abs,Y crossing a page: 6 cycles (data sheet 5, no page
  dependence); not crossing: 5 (correct).
- DEC/INC (and other read-modify-write) abs,X crossing a page: 8 (data
  sheet 7, no page dependence); not crossing: 7 (correct).
- LDA (zp),Y crossing a page: 5 (data sheet 6: "add 1 if page boundary is
  crossed"); not crossing: 5 (correct).
The addressing-mode subroutines are shared by many instructions; none of
these cases occurs in the M3 traces' key-off and timer paths. Fix with a
full regression of every M2/M3 run.
