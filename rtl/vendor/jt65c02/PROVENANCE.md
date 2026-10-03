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
