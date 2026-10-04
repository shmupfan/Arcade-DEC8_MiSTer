# jt65c02 cycle audit (second reader, R17 / R19 / R21)

Date: 2026-10-04. Scope: an independent check of the two jt65c02 microcode
errors fixed in commit 69e1dbc (`rtl/vendor/jt65c02/PROVENANCE.md`, local
changes 2 and 3; `docs/m3_findings.md` section 7.1), re-derived from the data
sheets, the board documents, MAME source and new measurements. Nothing in
69e1dbc's benches or `sim/m3/cycle_audit.py` was reused for the numbers below.
RTL was not changed.

## 1. Summary

| Claim | Verdict |
|---|---|
| (1) Upstream ADC/SBC took one extra cycle in binary mode and two instead of one in decimal mode | Confirmed for 17 of the 18 ADC/SBC opcodes. SBC (zp,X) (E1) was already correct upstream (6 binary, 7 decimal). The fix brings every ADC/SBC opcode to the data sheets in binary mode and to the R65C02 data sheet in decimal mode, except ADC/SBC (zp),Y with a page crossing, which went from 6 (correct by coincidence) to 5 (data sheets 6), the same deviation as the R21 LDA (zp),Y item. |
| (2) Upstream not-taken branches took 2.25 cycles instead of 2 | Confirmed: 9 microsteps (4 per bus cycle) in all 7 not-taken cases measured; 2.000 after the fix; taken branches unchanged. |
| ALU results unchanged by the fix | Confirmed: ADC and SBC over all 256 x 256 operands, C = 0/1, D = 0/1 (8 x 131,072 logged bytes, A and P) are identical before and after. Binary results match MAME's model on every input. |
| Sound CPU type (R19 and the CMOS assumption) | Last Mission and Gondomania: the board documents name an NMOS 6502A, not an R65C02 (MAME uses R65C02). SRD: MAME's DECO 222 is its NMOS m6502; the custom part's process is not documented. The two fixed items are the same on NMOS and CMOS, so the fix stands either way. |

New findings, not in R21 or the earlier documents:

- A taken branch to a different page takes 3 cycles in the core, before and
  after the fix (both data sheets and MAME: 4).
- jt65c02's decimal-mode results are wrong for 9 to 12% of valid BCD operand
  pairs (both versions; for example 67 + 99 gives 60 with C=0, 09 - 07 gives
  FB). The DEC8 programs never run with D=1 (section 6), so this has no
  effect here.
- The R21 page-crossing cases do occur in the DEC8 sound programs (section 7).

## 2. Sources

Data sheets (`../mister-arcade-survey/datasheets/r65c02/`, SOURCES.md md5s):

| Tag | Document | Rows used |
|---|---|---|
| R65C02-DS | Rockwell R65C00 family data sheet (R65C02, R65C102, R65C112), `rockwell_r65c00_microprocessors.pdf`, 16 pages | p. 1-11 (PDF p. 9) Instruction Set Op Code Matrix; p. 1-12 (PDF p. 10) Instruction Set Summary; p. 1-10 (PDF p. 8) Table 4 |
| R650X-DS | Rockwell R650X/R651X (NMOS) data sheet, `rockwell_r650x_r651x.pdf` | p. 10 (PDF p. 10) Instruction Set Op Code Matrix |
| MOS-DS | MOS Technology 6500 microprocessors, Mar 1980, `mos_6500_mpu_mar_1980.pdf` | p. 8 "Instruction Set, Op Codes, Execution Time, Memory Requirements" |
| MCS-HW | MOS MCS6500 Microcomputer Family Hardware Manual 6500-10A, Jan 1976 | Appendix A "Summary of Single Cycle Execution", A-2 to A-5 and A-12, A-13 (PDF p. 169-172, 179, 180) |

R65C02-DS p. 1-11, matrix cells ("bytes cycles"):

- ADC: 61 (IND,X) "2 6†", 65 ZP "2 3†", 69 IMM "2 2†", 6D ABS "3 4†",
  71 (IND),Y "2 5*†", 72 (IND) "2 5†", 75 ZP,X "2 4†", 79 ABS,Y "3 4*†",
  7D ABS,X "3 4*†".
- SBC: E1 "2 6†", E5 "2 3†", E9 "2 2†", ED "3 4†", F1 "2 5*†", F2 "2 5†",
  F5 "2 4†", F9 "3 4*†", FD "3 4*†".
- Branches: 10/30/50/70/90/B0/D0/F0 Relative "2 2**"; 80 BRA "2 3*".
- Others used as controls: 6C JMP (ABS) "3 6"; 9D STA ABS,X "3 5";
  99 STA ABS,Y "3 5"; DE DEC ABS,X "3 7"; B1 LDA (IND),Y "2 5*".
- Footnotes: "†Add 1 to N if in decimal mode." "*Add 1 to N if page
  boundary is crossed." "**Add 1 to N if branch occurs to same page; Add 2
  to N if branch occurs to different page."

R65C02-DS p. 1-12 notes: ADC carries notes (1)(5)(7), SBC (1)(3)(5);
"5. Add 1 to N if in Decimal Mode."

R65C02-DS p. 1-10, Table 4 "R65C00 Operational Enhancements" (NMOS R6502 /
CMOS R65C00): "Decimal flag. Indeterminate after reset. / Initialized to
binary mode (D=0) after reset and interrupts."; "Flags after decimal
operation. Invalid N, V and Z flags. / Valid flag adds one additional
cycle."; "Jump Indirect, operand = XXFF. Page address does not increment. /
Page address increments and adds one additional cycle."; "Read/modify/write
instructions at effective address. One read and two write cycles. / Two read
and one write cycle."

R650X-DS p. 10 (NMOS): ADC 61 "2 6", 65 "2 3", 69 "2 2", 6D "3 4",
71 "2 5*", 75 "2 4", 79 "3 4*", 7D "3 4*"; SBC E1 "2 6", E5 "2 3", E9 "2 2",
ED "3 4", F1 "2 5*", F5 "2 4", F9 "3 4*", FD "3 4*"; branches "2 2**";
6C JMP Indirect "3 5"; 9D "3 5"; DE "3 7". Footnotes as above, without the
decimal-mode note.

MOS-DS p. 8 (NMOS): ADC IMM 69 "2 2", ABS 6D "4 3", ZP 65 "3 2", (IND,X) 61
"6 2", (IND),Y 71 "5 2", ZP,X 75 "4 2", ABS,X 7D "4 3", ABS,Y 79 "4 3"
(cycles then bytes in this table); SBC the same; JMP indirect 6C "5 3".
Notes: "(1) ADD 1 TO N IF PAGE BOUNDARY IS CROSSED", "(2) ADD 1 TO N IF
BRANCH OCCURS TO SAME PAGE / ADD 2 TO N IF BRANCH OCCURS TO DIFFERENT PAGE",
"(4) IF IN DECIMAL MODE Z FLAG IS INVALID". No decimal cycle.

MCS-HW Appendix A: A.2 "Internal execution on memory data" lists ADC and SBC
with AND, BIT, CMP, CPX, CPY, EOR, LDA, LDX, LDY, ORA (same timing as LDA);
A.2.1 "Immediate Addressing (2 cycles)", A.2.2 "Zero Page Addressing (3
cycles)", A.2.3 "Absolute Addressing (4 cycles)", A.2.4 "Indirect, X
Addressing (6 cycles)", A.2.5 "Absolute, X or Absolute, Y Addressing (4 or 5
cycles)", A.2.6 "Zero Page, X ... (4 cycles)", A.2.7 "Indirect, Y Addressing
Mode (5 or 6 cycles)"; A.3 (stores): "No overlapping occurs and no shortening
of the instruction time occurs on indexing operations."; A.5.6.2 "Indirect
Addressing Mode (5 cycles)" (JMP); A.5.8 "Branch Operation ... (2, 3, or 4
cycles)", T2 "*Skip if branch not taken", T3 "**Skip if branch not taken;
skip if branch operation doesn't cross page boundary."

Decimal mode summary: the CMOS data sheet adds one cycle to every ADC/SBC
with D=1; both NMOS data sheets and the NMOS hardware manual give no extra
cycle. Branches: 2 not taken, 3 taken to the same page, 4 taken to a
different page, on both.

MAME (tag mame0288, the oracle version; `src/devices/cpu/m6502/`, fetched
2026-10-04 from github.com/mamedev/mame at that tag). Each `read`, `write`
and the final `prefetch()` in a .lst body is one bus cycle:

- `r65c02.cpp:24`: R65C02 is a `w65c02_device`; opcode map `dr65c02.lst`
  (md5 e9335c4f0f3e6adba8af66482a7c3f83) uses the `_c_` bodies of
  `ow65c02.lst` (md5 e929670a975c3f7faaf3325d5e98697a) and the shared bodies
  of `om6502.lst` (md5 704e40b84460cd560f6c32af09dbd6f6).
- `ow65c02.lst:83` adc_c_imm, `:67` adc_c_idy, `:18` adc_c_abx: the m6502
  body plus `if(m_P & F_D) { read_pc(); set_nz(m_A); }` (one extra cycle in
  decimal mode); `:422` jmp_c_ind 6 cycles; `:311` dec_c_abx 7 cycles.
- `om6502.lst:53` adc_idy, `:222` bcc_rel (`read_pc()` only when taken,
  `read_arg()` only when the page changes), `:721` jmp_ind 5 cycles,
  `:1294` sta_abx 5 cycles; NMOS ADC/SBC have no decimal cycle.
- DECO 222: `reference/mame/v0288/deco222.cpp:16` constructs
  `m6502_device(mconfig, DECO_222, ...)`, so it uses the NMOS `dm6502.lst`
  map (md5 729e41cd1bfbb50831a6f83bd41671ac) and om6502.lst bodies, with only
  the opcode bit 5/6 swap added.
- `m6502.cpp:109` initial `m_P = 0x36` (D=0); `m6502.cpp:156` do_adc_d;
  `w65c02.cpp:28` do_sbc_cd (used for the decimal reference model below).

A script that counts the cycles in each body (section 9) gives the MAME
columns of the tables in section 5; they agree with the data sheet columns
in every row.

Board documents (`../mister-arcade-survey/datasheets/boards/`):

| Tag | Document | Used |
|---|---|---|
| LM-SCH | Last Mission Operation and Service Manual with schematics, `lastmisn/Last-Mission.pdf`, md5 977e716672a959f8ab76a51fe58680b7 | sheet 25 (PDF p. 29): sound CPU 5J |
| GONDO-TSM | Gondomania Operation and Service Manual, `gondomania/Gondomania.pdf`, md5 cc39ffa8ad1c3543b502063aab32b99e | section 2a Component List (manual p. 3, PDF p. 22); sheet 27 (PDF p. 45): sound CPU 5J |

## 3. Sound CPU type per set (R19 widened)

| Sets | MAME 0.288 device | Board documents | Determination |
|---|---|---|---|
| lastmisn, lastmisnu6, lastmisnu5, lastmisnj | `R65C02` (dec8.cpp:1992; master lastmisn.cpp:1145), no PCB note | LM-SCH sheet 25 (PDF p. 29): 40-pin part at 5J labelled "6502A" (pins 40 RST, 4 IRQ, 6 NMI, 37 clock from *H2H) | NMOS 6502A per the schematic. MAME's CMOS choice is not supported by the documents available. |
| gondo, gondou, makyosen | `R65C02` (dec8.cpp:2109; master ghostb.cpp:1105), no PCB note | GONDO-TSM Component List, DE-0269 PCB: "CPU 6502A 100-0094-01 5J"; sheet 27 (PDF p. 45): 5J labelled "6502A" | NMOS 6502A per the parts list and the schematic. |
| srdarwin, srdarwinj, srdarwinb | `DECO_222` (dec8.cpp:2423, also on the bootleg), derived from the NMOS `m6502_device` | No SRD schematic in the survey. deco222.cpp header: "also sometimes implemented as basic logic outside the CPU on early revs and bootlegs"; master ghostb.cpp:1216 (The Real Ghostbusters, also a DECO 222 set): "also seen with stock M6502" | NMOS-like in MAME; the DECO 222 / C10707 die process is not documented. Unknown, leaning NMOS (a stock NMOS 6502 plus decode logic is a known substitute). |

Supporting evidence from the programs (MAME 0.288 debugger traces of the
sound CPU, 3600 frames from power-on with no inputs, `noloop`, about 32
million instructions per set, sets lastmisnu6, gondou, srdarwin):

- Only NMOS opcodes are executed (no BRA, STZ, PHX/PLX, TSB/TRB, (zp) mode,
  RMB/SMB/BBR/BBS, INC A/DEC A).
- The reset code is `8000: sei`, `8001: cld` on all three (traced from
  machine start), and no SED, PLP or CLD occurs afterwards. D is 0 for the
  whole run, as on NMOS hardware after an explicit CLD.

Caveat: a schematic names the designed part. A production board could carry
a pin-compatible R65C02 at 5J. A photo of the 5J marking on a Last Mission
or Gondomania PCB, or a cycle measurement on hardware, would settle it.

Consequence for the timing reference: for the two fixed items the NMOS and
CMOS documents agree (binary ADC/SBC counts and branch counts are identical
in R65C02-DS, R650X-DS, MOS-DS and MCS-HW). The sets differ only on JMP
(ind) (NMOS 5, CMOS 6), the decimal-mode cycle (NMOS none, CMOS +1) and
bus-level details (RMW write pattern, page-crossing dummy-read address).

## 4. Method

Cores built (Verilator 5.050, `--binary -O3`, nice 15), DECO222=1, opdec=0, cen
on every clock (4 clocks = 1 bus cycle, as `d8_snd.sv` with cen at 6 MHz):

- Original: the vendored RTL at fb9b52f (jt65c02.v, _ctrl, _alu, _regs; git
  blob hashes equal to jtcores a72a4460d6b762b8a6b63e76785405f72b440a49
  `modules/jt680x/hdl/`) with the pre-fix `deco222.uc` (md5
  a6b11e7f6e81e6121d776f4feb4742c2). I regenerated this file with jtframe
  `ucode jt680x deco222` built from the same jtcores commit (Go, sparse
  clone): byte-identical. The pre-fix `ucode/65c02.yaml` has the upstream
  blob hash ce133096.
- Fixed: the same RTL with the current `deco222.uc` (md5
  fffe818eb8034b4d9f07724f572f0d6e). Regenerating from the current
  `ucode/65c02.yaml` with the same jtframe build is also byte-identical;
  `deco222.vh` and `deco222_param.vh` are unchanged between the two.

Timing bench (section 9): one straight-line program at $0400 with 126
instruction cases (all ADC/SBC modes with and without page crossing, D=0 and
D=1, branches not taken / taken same page / taken across a page forward and
backward / not taken with the next instruction on the next page, BRA, and 60
control instructions). The bench logs the clock of every instruction start,
taken as the microsequencer step that loads the opcode into IR
(`u_ctrl.enable && u_ctrl.next_instruction`). An instruction's length is the
time to the next instruction start divided by 4. Every case's successor
address was checked (taken or not taken as intended). NOP measures 2.000.

Result bench: an exhaustive loop (a = 0..255, m = 0..255) that sets P with
PLP (C and D), runs ADC zp or SBC zp, and writes A and the pushed P to an
I/O address; 4 flag settings x 2 operations x 2 cores. A second variant sets
the flags with SED/SEC/CLC instead of PLP (same results).

## 5. Measured cycle counts

"DS" = data sheet; NMOS column = R650X-DS and MOS-DS (they agree);
"differs" = the fixed core differs from R65C02-DS. Page cases: abs,X $20FE,X
with X=4; abs,Y $20F8,Y with Y=$10; (zp),Y pointer $20F8 with Y=$10.

| Instruction (case) | Opcode | R65C02 DS | R650X / MOS 6500 DS | MAME r65c02 | MAME m6502 / deco222 | Core original | Core fixed |
|---|---|---|---|---|---|---|---|
| ADC D=0 #imm | 69 | 2 | 2 | 2 | 2 | 3 | 2 |
| ADC D=0 zp | 65 | 3 | 3 | 3 | 3 | 4 | 3 |
| ADC D=0 zp,X | 75 | 4 | 4 | 4 | 4 | 5 | 4 |
| ADC D=0 abs | 6D | 4 | 4 | 4 | 4 | 5 | 4 |
| ADC D=0 abs,X | 7D | 4 | 4 | 4 | 4 | 5 | 4 |
| ADC D=0 abs,X +page | 7D | 5 | 5 | 5 | 5 | 6 | 5 |
| ADC D=0 abs,Y | 79 | 4 | 4 | 4 | 4 | 5 | 4 |
| ADC D=0 abs,Y +page | 79 | 5 | 5 | 5 | 5 | 6 | 5 |
| ADC D=0 (zp,X) | 61 | 6 | 6 | 6 | 6 | 7 | 6 |
| ADC D=0 (zp),Y | 71 | 5 | 5 | 5 | 5 | 6 | 5 |
| ADC D=0 (zp),Y +page | 71 | 6 | 6 | 6 | 6 | 6 | 5 (differs) |
| ADC D=0 (zp) | 72 | 5 | n/a | 5 | n/a | 6 | 5 |
| SBC D=0 #imm | E9 | 2 | 2 | 2 | 2 | 3 | 2 |
| SBC D=0 zp | E5 | 3 | 3 | 3 | 3 | 4 | 3 |
| SBC D=0 zp,X | F5 | 4 | 4 | 4 | 4 | 5 | 4 |
| SBC D=0 abs | ED | 4 | 4 | 4 | 4 | 5 | 4 |
| SBC D=0 abs,X | FD | 4 | 4 | 4 | 4 | 5 | 4 |
| SBC D=0 abs,X +page | FD | 5 | 5 | 5 | 5 | 6 | 5 |
| SBC D=0 abs,Y | F9 | 4 | 4 | 4 | 4 | 5 | 4 |
| SBC D=0 abs,Y +page | F9 | 5 | 5 | 5 | 5 | 6 | 5 |
| SBC D=0 (zp,X) | E1 | 6 | 6 | 6 | 6 | 6 | 6 |
| SBC D=0 (zp),Y | F1 | 5 | 5 | 5 | 5 | 6 | 5 |
| SBC D=0 (zp),Y +page | F1 | 6 | 6 | 6 | 6 | 6 | 5 (differs) |
| SBC D=0 (zp) | F2 | 5 | n/a | 5 | n/a | 6 | 5 |
| ADC D=1 #imm | 69 | 3 | 2 | 3 | 2 | 4 | 3 |
| ADC D=1 zp | 65 | 4 | 3 | 4 | 3 | 5 | 4 |
| ADC D=1 zp,X | 75 | 5 | 4 | 5 | 4 | 6 | 5 |
| ADC D=1 abs | 6D | 5 | 4 | 5 | 4 | 6 | 5 |
| ADC D=1 abs,X | 7D | 5 | 4 | 5 | 4 | 6 | 5 |
| ADC D=1 abs,X +page | 7D | 6 | 5 | 6 | 5 | 7 | 6 |
| ADC D=1 abs,Y | 79 | 5 | 4 | 5 | 4 | 6 | 5 |
| ADC D=1 abs,Y +page | 79 | 6 | 5 | 6 | 5 | 7 | 6 |
| ADC D=1 (zp,X) | 61 | 7 | 6 | 7 | 6 | 8 | 7 |
| ADC D=1 (zp),Y | 71 | 6 | 5 | 6 | 5 | 7 | 6 |
| ADC D=1 (zp),Y +page | 71 | 7 | 6 | 7 | 6 | 7 | 6 (differs) |
| ADC D=1 (zp) | 72 | 6 | n/a | 6 | n/a | 7 | 6 |
| SBC D=1 #imm | E9 | 3 | 2 | 3 | 2 | 4 | 3 |
| SBC D=1 zp | E5 | 4 | 3 | 4 | 3 | 5 | 4 |
| SBC D=1 zp,X | F5 | 5 | 4 | 5 | 4 | 6 | 5 |
| SBC D=1 abs | ED | 5 | 4 | 5 | 4 | 6 | 5 |
| SBC D=1 abs,X | FD | 5 | 4 | 5 | 4 | 6 | 5 |
| SBC D=1 abs,X +page | FD | 6 | 5 | 6 | 5 | 7 | 6 |
| SBC D=1 abs,Y | F9 | 5 | 4 | 5 | 4 | 6 | 5 |
| SBC D=1 abs,Y +page | F9 | 6 | 5 | 6 | 5 | 7 | 6 |
| SBC D=1 (zp,X) | E1 | 7 | 6 | 7 | 6 | 7 | 7 |
| SBC D=1 (zp),Y | F1 | 6 | 5 | 6 | 5 | 7 | 6 |
| SBC D=1 (zp),Y +page | F1 | 7 | 6 | 7 | 6 | 7 | 6 (differs) |
| SBC D=1 (zp) | F2 | 6 | n/a | 6 | n/a | 7 | 6 |
| BCC not taken | 90 | 2 | 2 | 2 | 2 | 2.25 | 2 |
| BCS not taken | B0 | 2 | 2 | 2 | 2 | 2.25 | 2 |
| BEQ not taken | F0 | 2 | 2 | 2 | 2 | 2.25 | 2 |
| BNE not taken | D0 | 2 | 2 | 2 | 2 | 2.25 | 2 |
| BMI not taken | 30 | 2 | 2 | 2 | 2 | 2.25 | 2 |
| BVS not taken | 70 | 2 | 2 | 2 | 2 | 2.25 | 2 |
| BCC not taken, next instruction on the next page | 90 | 2 | 2 | 2 | 2 | 2.25 | 2 |
| BCS taken, same page (+0) | B0 | 3 | 3 | 3 | 3 | 3 | 3 |
| BCS taken, same page (+2) | B0 | 3 | 3 | 3 | 3 | 3 | 3 |
| BNE taken, same page | D0 | 3 | 3 | 3 | 3 | 3 | 3 |
| BPL taken | 10 | 3 | 3 | 3 | 3 | 3 | 3 |
| BVC taken | 50 | 3 | 3 | 3 | 3 | 3 | 3 |
| BNE backward loop: taken, taken, not taken | D0 | 3, 3, 2 | 3, 3, 2 | 3, 3, 2 | 3, 3, 2 | 3, 3, 2.25 | 3, 3, 2 |
| BRA same page | 80 | 3 | n/a | 3 | n/a | 3 | 3 |
| BCC taken, forward page cross ($05F0 to $0612) | 90 | 4 | 4 | 4 | 4 | 3 | 3 (differs) |
| BCC taken, backward page cross ($0700 to $06F2) | 90 | 4 | 4 | 4 | 4 | 3 | 3 (differs) |
| BRA forward page cross | 80 | 4 | n/a | 4 | n/a | 3 | 3 (differs) |
| NOP | EA | 2 | 2 | 2 | 2 | 2 | 2 |
| LDA #imm / zp / zp,X / abs | A9 A5 B5 AD | 2 / 3 / 4 / 4 | 2 / 3 / 4 / 4 | 2 / 3 / 4 / 4 | 2 / 3 / 4 / 4 | 2 / 3 / 4 / 4 | 2 / 3 / 4 / 4 |
| LDA abs,X / abs,X +page / abs,Y +page | BD BD B9 | 4 / 5 / 5 | 4 / 5 / 5 | 4 / 5 / 5 | 4 / 5 / 5 | 4 / 5 / 5 | 4 / 5 / 5 |
| LDA (zp,X) / (zp),Y / (zp) | A1 B1 B2 | 6 / 5 / 5 | 6 / 5 / n/a | 6 / 5 / 5 | 6 / 5 / n/a | 6 / 5 / 5 | 6 / 5 / 5 |
| LDA (zp),Y +page | B1 | 6 | 6 | 6 | 6 | 5 | 5 (differs) |
| AND #imm, ORA zp, EOR abs, CMP abs,X | 29 05 4D DD | 2, 3, 4, 4 | 2, 3, 4, 4 | 2, 3, 4, 4 | 2, 3, 4, 4 | 2, 3, 4, 4 | 2, 3, 4, 4 |
| STA zp / abs / abs,X / (zp),Y | 85 8D 9D 91 | 3 / 4 / 5 / 6 | 3 / 4 / 5 / 6 | 3 / 4 / 5 / 6 | 3 / 4 / 5 / 6 | 3 / 4 / 5 / 6 | 3 / 4 / 5 / 6 |
| STA abs,X +page | 9D | 5 | 5 | 5 | 5 | 6 | 6 (differs) |
| STA abs,Y +page | 99 | 5 | 5 | 5 | 5 | 6 | 6 (differs) |
| INC zp / INC abs / DEC abs,X | E6 EE DE | 5 / 6 / 7 | 5 / 6 / 7 | 5 / 6 / 7 | 5 / 6 / 7 | 5 / 6 / 7 | 5 / 6 / 7 |
| DEC abs,X +page | DE | 7 | 7 | 7 | 7 | 8 | 8 (differs) |
| ASL A, ROR zp, LSR zp | 0A 66 46 | 2, 5, 5 | 2, 5, 5 | 2, 5, 5 | 2, 5, 5 | 2, 5, 5 | 2, 5, 5 |
| INX, DEX, TAX, TXA, CLC, SEC, CLD, SED | | 2 each | 2 each | 2 each | 2 each | 2 each | 2 each |
| PHA, PLA, PHP, PLP | 48 68 08 28 | 3, 4, 3, 4 | 3, 4, 3, 4 | 3, 4, 3, 4 | 3, 4, 3, 4 | 3, 4, 3, 4 | 3, 4, 3, 4 |
| STZ zp | 64 | 3 | n/a | 3 | n/a | 3 | 3 |
| JMP abs, JSR abs, RTS | 4C 20 60 | 3, 6, 6 | 3, 6, 6 | 3, 6, 6 | 3, 6, 6 | 3, 6, 6 | 3, 6, 6 |
| JMP (ind) | 6C | 6 | 5 | 6 | 5 | 6 | 6 (NMOS: differs) |

Mechanisms (read from the RTL and the YAML):

- ADC/SBC: the upstream YAML declared each ADC/SBC one cycle longer than the
  data sheet, except SBC (zp,X) E1 (declared 6), and the shared ALU sequence
  had three idle microsteps before the ALU step. The fixed YAML declares
  the data sheet counts and puts the ALU step and the BCD jump right after
  the fetch; the daa/das subroutine supplies the decimal cycle.
- Not-taken branch: confirmed as described in PROVENANCE change 3 (front
  padding put one idle microstep before the condition test).
- Taken branch to another page (new): the page penalty is a 4-step stall
  (`jt65c02_ctrl.v`, `wait4cy & (branch ? pcpage : calt)`), but `pcpage` is
  registered in `jt65c02_regs.v` on the same step that asserts `wait4cy`
  ("branch, add_alu, alt_carry, wait4cy"), so it is high only on the step
  after, when `wait4cy` is low. The stall is never taken. The same in the
  original and the fixed microcode.
- (zp),Y with a page crossing: the core adds nothing for any (zp),Y read
  (LDA, ADC, SBC). Upstream's ADC/SBC extra cycle hid this for ADC/SBC; the
  fix exposes it.

## 6. ALU results

- Original against fixed: ADC zp and SBC zp over a = 0..255, m = 0..255, for
  P = 00, 01, 08, 09 (C, D): every logged A and P byte identical (8 runs x
  131,072 bytes). The fix changes timing only.
- Binary mode against MAME's model (`do_adc_nd` / `do_sbc_nd`, m6502.cpp):
  0 mismatches in 262,144 cases (N, V, Z, C and A).
- Decimal mode against MAME's 65C02 model (m6502.cpp:156 `do_adc_d` with
  `set_nz(A)`, w65c02.cpp:28 `do_sbc_cd`), valid BCD operands only (10,000
  pairs per run): ADC C=0: A wrong 84, C wrong 624, V differs 312; ADC C=1:
  A 112, C 640, V 360; SBC C=0: A 1200, N 40, Z 20; SBC C=1: A 1200, N 120,
  Z 20. Direct checks on both cores: 67 + 99 (C=0) gives 60 with C=0
  (expected 66, C=1); 09 - 07 (C=1) gives FC (expected 02); 09 - 07 (C=0)
  gives FB (expected 01); 15 + 27 = 42, 42 - 15 = 27, 58 + 46 = 04 (C=1),
  00 - 01 = 99 are correct. This is upstream jt65c02 behaviour, unchanged by
  69e1dbc, and the earlier bench (`sim/m3/cputest/tb_6502.sv`) checked only
  three vectors that happen to be correct. Not reached in DEC8 (D=0, section
  3).

## 7. Exposure in the DEC8 sound programs

MAME 0.288, 3600 frames from power-on, no inputs (sets lastmisnu6, gondou,
srdarwin). Branch outcomes from consecutive trace lines; indexed stores from
a Lua write tap on $0200-$03FF keyed by instruction PC; (zp),Y reads from a
Lua read tap with the pointer and Y at each (zp),Y instruction (tap totals
against trace totals: Last Mission 24,239 = 24,239, Gondomania 21,988 vs
21,939, SRD 83,654 = 83,654).

| Event (per 3600 frames) | Last Mission | Gondomania | SRD | Fixed core vs data sheet |
|---|---|---|---|---|
| Instructions | 32,041,528 | 32,140,647 | 32,106,486 | |
| ADC + SBC (all binary) | 146,332 | 164,591 | 276,649 | fixed: equal (was +1 each) |
| Branches not taken | 507,253 | 898,736 | 1,029,181 | fixed: equal (was +0.25 each) |
| Branches taken, same page | 1,722,624 | 1,777,953 | 1,938,761 | equal |
| Branches taken, other page | 104 | 261 | 938 | -1 each (new finding) |
| STA abs,X crossing a page ($02F3,X, $0353,X) | 866 | 0 | 1,896 | +1 each (R21) |
| RMW abs,X crossing a page | 0 | 0 | 0 | (R21, not reached) |
| (zp),Y reads crossing a page | 129 | 306 | 3,627 | -1 each (R21, includes SBC (zp),Y) |
| JMP ($000A) | 6,046 | 4,293 | 16,556 | CMOS 6 = core; NMOS 5: +1 each |
| SED, PLP, decimal ADC/SBC | 0 | 0 | 0 | decimal path unused |

Net residual against the data sheet of the documented CPU (NMOS for all
three, section 3), per 3600 frames: Last Mission +866 - 129 - 104 + 6,046 =
+6,679 cycles; Gondomania -306 - 261 + 4,293 = +3,726; SRD +1,896 - 3,627 -
938 + 16,556 = +13,887 (about 0.007%, 0.004% and 0.015% of roughly 93
million cycles). Against MAME's own CPU choice (R65C02 for Last Mission and
Gondomania, NMOS for SRD): +633, -567 and +13,887. The R21 note "not reached
in the sound programs' timer paths" holds only for those paths; the cases
occur in the music code at $87A0-$87DE and elsewhere.

## 8. Verdicts and open items

- Claim (1): confirmed, with the two qualifications in section 1 (SBC (zp,X)
  was already right; ADC/SBC (zp),Y across a page is now one cycle short).
  Correct for NMOS and CMOS in binary mode. In decimal mode the fix follows
  the CMOS data sheet (+1); an NMOS part has no extra cycle. Unused by these
  programs.
- Claim (2): confirmed and correctly fixed for NMOS and CMOS.
- Disagreements with the current state (RTL not changed, reported here):
  1. The CPU reference. The fix was argued from the Rockwell R65C02 data sheet
     as the boards' CPU; the Last Mission schematic and the Gondomania parts
     list and schematic give an NMOS 6502A. The fixed items are unaffected;
     JMP (ind) is not (core 6, NMOS 5).
  2. R21 is incomplete: add taken branches to another page (3, should be 4)
     and ADC/SBC (zp),Y across a page (5, should be 6; 6/7 in decimal per
     CMOS), and note that STA abs,X and (zp),Y crossings occur in the
     programs.
  3. jt65c02 decimal arithmetic is incorrect for some BCD inputs (both
     versions); harmless here because D is always 0.

R19, if resolved:

- All three NMOS (the reading of section 3): JMP (ind) should be 5 cycles on
  every set. That needs an NMOS variant of the microcode (JMP (ind) without
  the extra cycle; ideally also no decimal cycle and the NMOS RMW
  read-write-write pattern) selected per set. Removing the decimal cycle and
  CMOS decimal flags would change nothing observable in these programs. The
  NMOS RMW double write targets only RAM here ($0203,X-$0363,X), so it has no
  side effect. Residuals in section 7 would drop by the JMP (ind) counts
  (6,046 / 4,293 / 16,556 per 3600 frames).
- SRD CMOS (DECO 222 on a CMOS core): the core's JMP (ind) 6 is right for SRD,
  and MAME's DECO 222 (NMOS m6502) is the side in error for the R19 timer IRQ
  difference noted in m3_findings 3.3.
- Last Mission / Gondomania actually fitted with R65C02s (as MAME): the
  current CMOS behaviour is right for them; only the R21 items remain.

Evidence that would settle R19: a photo of the 5J part marking on a Last
Mission and a Gondomania board and of the DECO 222 on an SRD board, or a
logic-analyser cycle count of a JMP (ind) (5 or 6 cycles) on hardware.

## 9. Reproduction

Benches and scripts were run from a scratch folder and are not committed;
the testbench and timing program generator are reproduced here.

Build, per microcode file (V = rtl/vendor/jt65c02; UC = the .uc file;
original: `git show 69e1dbc^:rtl/vendor/jt65c02/deco222.uc`):

    nice -n 15 verilator --binary -O3 -Wno-fatal -Wno-lint -Wno-style -Wno-WIDTH \
      --top-module tb_cyc -I$V -DSIMULATION -DJT65C02_UCFILE="\"$UC\"" tb_cyc.sv \
      $V/jt65c02.v $V/jt65c02_ctrl.v $V/jt65c02_alu.v $V/jt65c02_regs.v -Mdir obj
    python3 gen_timing.py   # timing.hex, timing_cases.json
    ./obj/Vtb_cyc +hex=timing.hex +log=timing.log

`tb_cyc.sv`:

```systemverilog
module tb_cyc;
  logic clk = 0, rst = 1;
  logic [7:0] mem [0:65535];
  wire [15:0] addr; wire [7:0] dout; wire wr, rd, fetch;
  wire [7:0] din = mem[addr];
  always #1 clk = ~clk;
  jt65c02 #(.DECO222(1)) u_cpu (.rst(rst), .clk(clk), .cen(1'b1), .irq(1'b0), .nmi(1'b0),
    .opdec(1'b0), .wr(wr), .rd(rd), .fetch(fetch), .addr(addr), .din(din), .dout(dout));
  integer t = 0, fd;
  string hexf, logf;
  logic wr_d = 0; logic [15:0] wa_d = 0;
  always @(posedge clk) begin
    t <= t + 1;
    if (!rst) begin
      if (wr) mem[addr] <= dout;
      wr_d <= wr; wa_d <= addr;
      if (u_cpu.u_ctrl.enable && u_cpu.u_ctrl.next_instruction)
        $fwrite(fd, "I %0d %02x %04x\n", t, din, addr);
      if (wr && !(wr_d && wa_d == addr)) begin
        if (addr == 16'hFFF0) $fwrite(fd, "W %0d %02x\n", t, dout);
        if (addr == 16'hFFF1) begin $fclose(fd); $finish; end
      end
    end
  end
  initial begin
    if (!$value$plusargs("hex=%s", hexf)) $fatal(1, "no +hex");
    if (!$value$plusargs("log=%s", logf)) $fatal(1, "no +log");
    $readmemh(hexf, mem);
    fd = $fopen(logf, "w");
    repeat (20) @(posedge clk);
    rst = 0;
  end
endmodule
```

Cycles per instruction = (next "I" time - this "I" time) / 4.

`gen_timing.py` (case table; each `case()` emits one instruction and its
expected counts: R65C02-DS, NMOS DS, MAME r65c02, MAME m6502):

```python
import json
mem = bytearray([0xEA] * 65536); cases = []; pc = 0
def org(a):
    global pc; pc = a
def b(*bs):
    global pc
    for x in bs: mem[pc] = x & 0xFF; pc += 1
def case(label, cmos, nmos, mame_c, mame_n, *bs):
    cases.append(dict(addr=pc, label=label, ds_cmos=cmos, ds_nmos=nmos,
                      mame_r65c02=mame_c, mame_m6502=mame_n, op=bs[0])); b(*bs)
mem[0x10], mem[0x11] = 0x00, 0x20   # ($10),Y Y=$10 -> $2010
mem[0x12], mem[0x13] = 0xF8, 0x20   # ($12),Y -> $2108 (page cross)
mem[0x18], mem[0x19] = 0x00, 0x20   # ($14,X) X=4 -> $2000
mem[0x30], mem[0x31] = 0x00, 0x09   # jmp ($0030) -> $0900
mem[0xFFFC], mem[0xFFFD] = 0x00, 0x04
org(0x0400)
case('LDX #4', 2, 2, 2, 2, 0xA2, 4); case('LDY #$10', 2, 2, 2, 2, 0xA0, 0x10)
case('CLD', 2, 2, 2, 2, 0xD8); case('CLC', 2, 2, 2, 2, 0x18)
def alu_block(tag, o, d):
    x = 1 if d else 0
    case(f'{tag} #imm', 2+x, 2, 2+x, 2, o+0x08, 0x12)
    case(f'{tag} zp', 3+x, 3, 3+x, 3, o+0x04, 0x20)
    case(f'{tag} zp,X', 4+x, 4, 4+x, 4, o+0x14, 0x20)
    case(f'{tag} abs', 4+x, 4, 4+x, 4, o+0x0C, 0x00, 0x20)
    case(f'{tag} abs,X', 4+x, 4, 4+x, 4, o+0x1C, 0x00, 0x20)
    case(f'{tag} abs,X +page', 5+x, 5, 5+x, 5, o+0x1C, 0xFE, 0x20)
    case(f'{tag} abs,Y', 4+x, 4, 4+x, 4, o+0x18, 0x00, 0x20)
    case(f'{tag} abs,Y +page', 5+x, 5, 5+x, 5, o+0x18, 0xF8, 0x20)
    case(f'{tag} (zp,X)', 6+x, 6, 6+x, 6, o+0x00, 0x14)
    case(f'{tag} (zp),Y', 5+x, 5, 5+x, 5, o+0x10, 0x10)
    case(f'{tag} (zp),Y +page', 6+x, 6, 6+x, 6, o+0x10, 0x12)
    case(f'{tag} (zp)', 5+x, None, 5+x, None, o+0x11, 0x10)
alu_block('ADC D=0', 0x61, False); alu_block('SBC D=0', 0xE1, False)
case('SED', 2, 2, 2, 2, 0xF8)
alu_block('ADC D=1', 0x61, True); alu_block('SBC D=1', 0xE1, True)
case('CLD', 2, 2, 2, 2, 0xD8); case('SEC', 2, 2, 2, 2, 0x38)
case('BCC not taken', 2, 2, 2, 2, 0x90, 0x00)
case('BCS taken +0', 3, 3, 3, 3, 0xB0, 0x00)
case('BCS taken +2', 3, 3, 3, 3, 0xB0, 0x02); b(0x00, 0x00)
case('CLC', 2, 2, 2, 2, 0x18)
case('BCS not taken', 2, 2, 2, 2, 0xB0, 0x00)
case('BEQ not taken', 2, 2, 2, 2, 0xF0, 0x00)
case('BNE taken', 3, 3, 3, 3, 0xD0, 0x00)
case('BRA same page', 3, None, 3, None, 0x80, 0x00)
case('LDX #3', 2, 2, 2, 2, 0xA2, 3); loop = pc
case('DEX', 2, 2, 2, 2, 0xCA)
case('BNE backward', '3,3,2', '3,3,2', '3,3,2', '3,3,2', 0xD0, (loop - (pc + 2)) & 0xFF)
case('LDX #4', 2, 2, 2, 2, 0xA2, 4); case('JMP abs', 3, 3, 3, 3, 0x4C, 0xF0, 0x05)
org(0x05F0); case('BCC taken, forward page cross', 4, 4, 4, 4, 0x90, 0x20)
org(0x0612); case('BRA forward page cross', 4, None, 4, None, 0x80, 0x7E)
org(0x0692); case('JMP abs', 3, 3, 3, 3, 0x4C, 0x00, 0x07)
org(0x0700); case('BCC taken, backward page cross', 4, 4, 4, 4, 0x90, 0xF0)
org(0x06F2); case('JMP abs', 3, 3, 3, 3, 0x4C, 0x10, 0x07)
org(0x0710)
case('LDA #$40', 2, 2, 2, 2, 0xA9, 0x40); case('CMP #$40', 2, 2, 2, 2, 0xC9, 0x40)
case('BNE not taken', 2, 2, 2, 2, 0xD0, 0x00); case('BMI not taken', 2, 2, 2, 2, 0x30, 0x00)
case('BPL taken', 3, 3, 3, 3, 0x10, 0x00); case('BVC taken', 3, 3, 3, 3, 0x50, 0x00)
case('BVS not taken', 2, 2, 2, 2, 0x70, 0x00); case('JMP abs', 3, 3, 3, 3, 0x4C, 0xFE, 0x07)
org(0x07FE); case('BCC not taken, next page', 2, 2, 2, 2, 0x90, 0x00)
for args in [('NOP',2,0xEA),('LDA #',2,0xA9,0),('LDA zp',3,0xA5,0x20),('LDA zp,X',4,0xB5,0x20),
             ('LDA abs',4,0xAD,0,0x20),('LDA abs,X',4,0xBD,0,0x20),('LDA abs,X +page',5,0xBD,0xFE,0x20),
             ('LDA abs,Y +page',5,0xB9,0xF8,0x20),('LDA (zp,X)',6,0xA1,0x14),('LDA (zp),Y',5,0xB1,0x10),
             ('LDA (zp),Y +page',6,0xB1,0x12)]:
    case(args[0], args[1], args[1], args[1], args[1], *args[2:])
case('LDA (zp)', 5, None, 5, None, 0xB2, 0x10)
for args in [('AND #',2,0x29,0xFF),('ORA zp',3,0x05,0x20),('EOR abs',4,0x4D,0,0x20),('CMP abs,X',4,0xDD,0,0x20),
             ('STA zp',3,0x85,0x40),('STA abs',4,0x8D,0,0x30),('STA abs,X',5,0x9D,0,0x30),
             ('STA abs,X +page',5,0x9D,0xFE,0x30),('STA abs,Y +page',5,0x99,0xF8,0x30),('STA (zp),Y',6,0x91,0x10),
             ('STX zp',3,0x86,0x41),('INC zp',5,0xE6,0x40),('INC abs',6,0xEE,0,0x30),('DEC abs,X',7,0xDE,0,0x30),
             ('DEC abs,X +page',7,0xDE,0xFE,0x30),('ASL A',2,0x0A),('ROR zp',5,0x66,0x40),('LSR zp',5,0x46,0x40),
             ('INX',2,0xE8),('DEX',2,0xCA),('TAX',2,0xAA),('TXA',2,0x8A),('PHA',3,0x48),('PLA',4,0x68),
             ('PHP',3,0x08),('PLP',4,0x28)]:
    case(args[0], args[1], args[1], args[1], args[1], *args[2:])
case('STZ zp', 3, None, 3, None, 0x64, 0x42)
case('JSR abs', 6, 6, 6, 6, 0x20, 0x00, 0x0A)
case('JMP (ind)', 6, 5, 6, 5, 0x6C, 0x30, 0x00)
org(0x0A00); case('RTS', 6, 6, 6, 6, 0x60)
org(0x0900); case('LDA #0', 2, 2, 2, 2, 0xA9, 0x00); b(0x8D, 0xF1, 0xFF)
open('timing.hex', 'w').write(''.join('%02x\n' % x for x in mem))
json.dump(cases, open('timing_cases.json', 'w'))
```

Result bench program (per run: OP = 65 for ADC zp or E5 for SBC zp, FLAGS =
the P value): `$0400: A9 00 85 10 85 11` then loop `A5 12 48 A5 10 28 OP 11
08 8D F0 FF 68 8D F0 FF D8 E6 11 D0 EB E6 10 D0 E7 8D F1 FF`, with $12 =
FLAGS. Logged pairs are (A, P) for a = mem[$10], m = mem[$11].

MAME traces: `sim/mame/run_mame.sh <set> <lua> -debug -debugger none` with a
frame notifier that issues `trace <fifo>,audiocpu,noloop` on frame 1 and
exits on frame 3600; the trace streams through a FIFO into a counter
(distinct PC/mnemonic/operand counts and branch outcomes from consecutive
lines). Boot code: the same `trace` command issued from the autoboot script
before the first frame. Write tap: `install_write_tap(0x0200, 0x03ff, ...)`
on the audiocpu program space, keyed by `state["PC"]` (the PC of the
instruction being executed). Read tap: `install_read_tap` on the whole
space, counting each (zp),Y instruction once with the pointer read from zero
page and the current Y.
