# mc6809i (cycle-accurate MC6809/MC6809E)

Core by Greg Miller, original repository cavnex/mc6809 (master
17e94a6ef163be8b79a9b15b2e814847b6062f0f): "Cycle-Accurate 6809 Core",
validated against hard MC6809/MC6809E parts on a GODIL (README there).
Licence: the author offers a choice of the standard 3-clause BSD licence or
a binary-only modified BSD licence (`LICENSE.md`, copied from
`documentation/LICENSE.md`); this core uses the standard BSD licence, which
is compatible with GPL-3.0. This closes research item R11.

File used: `mc6809i.v` from jotego/jtcores master
a72a4460d6b762b8a6b63e76785405f72b440a49,
`modules/jtframe/hdl/cpu/mc6809i.v` (fetched 2026-10-03): the same core with
the E/Q clock inputs converted to clock enables `cen_E` (falling edge of E)
and `cen_Q` (falling edge of Q) on a single clock, Verilator lint pragmas,
an `OP` output and simulation-only signals added by Jose Tejada (jtframe,
GPL-3.0-or-later). Reviewed by diff against the original (whitespace
ignored, 139 changed lines): besides the clocking conversion, lint pragmas
and the additions above, jtframe's copy changes behaviour in three places:

- SEX (inherent 0x1D) sets N and Z from B and clears V; the original left
  the flags unchanged. (MAME 0.288 m6809.lst `SEX`: NZ from D, V not
  touched; any V difference shows in the M2 comparison. Motorola's own
  documents disagree, docs/m2_findings.md R15.)
- The NMI arm: the original releases the NMI mask when S changes value
  (`s != s_nxt`); jtframe's when S is written (`s_wr`: LDS, TFR/EXG to S,
  LEAS, PULS S). The 6809 data sheet arms NMI on the first load of S.
- S resets to 0 (original 0xFFFD, whose only purpose was the S-change
  detector above).

Also a few width-cast changes in the ALU (no behaviour change). The BSD
copyright notice is retained in the file header.

Not modified for DEC8.
