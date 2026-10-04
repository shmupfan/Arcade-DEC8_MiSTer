# DEC8 core plan (Last Mission, Gondomania, SRD: Super Real Darwin)

Third core of the shmup glue-core programme (after 1945k III and Tecmo 16).
One core, one RBF for the three shooters on Data East's 1986-87 8-bit
boards that have no MiSTer core anywhere (checked 2026-10-03, section 1),
game selected by an MRA machine byte, as in the Dooyong and 1945k III cores.

Lee's standing rule: accuracy first, document everything. MAME 0.288 is the
oracle for verification; where MAME is known or suspected to be less
accurate than the hardware, the core follows the hardware's most plausible
behaviour, every divergence from MAME is classified with its cause, and an
open research item names the evidence that would settle it.

## 1. Coverage check (2026-10-03)

- GitHub code search of every .mra file for srdarwin, gondo, lastmisn,
  makyosen: 0 results each. Repository search for "dec8 mister", "darwin
  mister", "gondomania", "last mission mister", "srdarwin": nothing
  relevant.
- The 2026-10-02 coverage list (Distribution_MiSTer, jtbin, Coin-Op, Ongo,
  Slop-Core, kuzecores, meatcores, jlrh, Shmup Deck) has cobracom and oscar
  (Coin-Op) from dec8.cpp, none of the ten sets here.
- Same driver, also uncovered and not shooters: Shackled/Breywood, The Real
  Ghostbusters, Meikyuu Hunter G, Garyo Retsuden, Captain Silver. They share
  most of this hardware (Ghostbusters adds the BAC06 tilemap chip) and are
  candidates for a later extension, not part of this plan.

## 2. Sets (10)

lastmisn, lastmisnu6, lastmisnu5, lastmisnj; gondo, gondou, makyosen;
srdarwin, srdarwinj, srdarwinb. Machine configs and MCU dump status: spec
section 1. Parent sets with a BAD_DUMP MCU (lastmisn, gondo, srdarwinj)
run in MAME; whether the core can be exact for them depends on what the
real MCU does (R1). Sets with good dumps (lastmisnu5/u6, gondou, makyosen,
srdarwin) are the accuracy references.

## 3. Reusable HDL

| Block | Candidate | Licence | Status |
|---|---|---|---|
| MC6809E x2 (lastmisn), MC6809E (srdarwin) | jtframe `mc6809i.v` (Greg Miller, "Cycle-Accurate 6809 Core"), as wrapped by `jtframe_sys6809.v` | BSD-3-Clause (cavnex/mc6809 LICENSE.md; R11 closed); vendored with PROVENANCE in rtl/vendor/mc6809i | M2 (DONE) |
| HD6309E (gondo; the board's component list says 6809E, R16) | the same 6809 core: the 2,930-frame attract trace (36.1 M instructions) shows only 6809 mnemonics and no LDMD, so the 6309 stays in emulation mode, where its timing equals the 6809's; confirmed on gameplay in M2 (R4 closed) | as above | M2 (DONE) |
| R65C02 (lastmisn, gondo sound) | jtcores `jt65c02` (jt680x) | GPL-3.0-or-later | M3 |
| DECO 222 (srdarwin sound) | 6502 with opcode-fetch bits 5 and 6 swapped (deco222.cpp): a wrapper on a 6502 core (jt65c02 in 6502 mode or T65) | own wrapper | M3 |
| i8751 | jtcores `jt8051`, vendored with its generated microcode and three documented patches (rtl/vendor/jt8051/PROVENANCE.md) | GPL-3.0-or-later | M2 (DONE) |
| YM2203 | jt03 (vendored in dooyong-mister/rtl/vendor, with PROVENANCE) | GPL-3.0-or-later | M3 |
| YM3526 (lastmisn, gondo), YM3812 (srdarwin) | jotego jtopl / jtopl2 (jtcores submodule) | GPL-3.0-or-later | M3 |
| Karnov sprite chip (lastmisn, gondo) | jtcores `jtkarnov_obj.v` as a reference; the sprite list semantics here are MAME's deckarn.cpp; reuse only where it matches the oracle exactly (verified, not assumed), as Tecmo 16 did with jtgaiden | GPL-3.0-or-later | M1 |
| Tilemaps, srdarwin sprites, palette | new RTL (the renderer `sim/oracle/d8_render.py` is the model) | GPL-3.0-or-later | M1 |
| Coin-Op Collection cobracom/oscar cores | no public HDL (RBFs only); their public `Development-Modules` repo is CC BY-NC 4.0, which cannot go into a GPL core | not usable | |

## 4. Milestones

| M | Content | Gate |
|---|---|---|
| M0 | spec, ROM checks, region builder, MAME oracle, reference renderer | 10/10 sets, regions byte-identical, renderer pixel-exact on every captured frame (DONE, docs/m0_findings.md) |
| M1 | video RTL for the three machines | RTL pixel-exact against MAME on every M0 frame; mid-scan writes rendered live and every differing frame classified; synthetic scenes against the renderer; line budget with a pessimistic ROM model (DONE, docs/m1_findings.md) |
| M2 | full system: 6809 x2 / 6309-as-6809 / 6809, i8751, memory maps, interrupts, MCU protocol, inputs, DIPs | boots from power-on match MAME's I/O streams, images and RAM; divergences root-caused (DONE, docs/m2_findings.md) |
| M3 | sound: 6502/R65C02/DECO 222, YM2203, YM3526/YM3812, latches and NMIs | register streams and level against MAME WAVs (DONE, docs/m3_findings.md; R17-R20 open) |
| M4 | MiSTer shell, SDRAM, MRAs (DIPs from the driver, machine byte; srdarwinb's sprite byte swap done by a sprite word address swap in the board, docs/m4_findings.md 2), rotary input for Gondomania, Quartus timing at 96 MHz | board sim equals M2 (all but 32 pixels of one frame, R22); timing closed; first RBF built (DONE, docs/m4_findings.md); on hardware in M5 |
| M5 | hardware QA, release to the shmupfan database | |

Lessons carried from the other cores: register every SDRAM request address
and arbitration decision before SDRAM_A (1945k III compile 1); program ROM
fetches must not add wait states (DTACK on time, latch until ok); pause
input from the start; MRA game switch without reload is a known MiSTer
shell edge case to test (1945k III known issue 9.1).

## 5. Decisions

- 5.1 Oracle version: MAME 0.288 (local), matching the other cores; master's
  driver split is vendored for reference (spec section 12).
- 5.2 Mid-scan writes (Lee, 2026-10-02, all cores): the core renders live
  (race the beam). MAME draws each frame once at vblank, so frames with
  visible-area tile, palette or scroll writes will differ from MAME; M1
  classifies each one. Most plausible PCB behaviour, unconfirmed (R5).
- 5.3 MCU dumps (Lee, 2026-10-03): the good-dump clones are the accuracy
  references: lastmisnu5/lastmisnu6 for Last Mission, gondou (and
  makyosen) for Gondomania, srdarwin for SRD. The parent sets lastmisn and
  gondo and the clones lastmisnj and srdarwinj carry BAD_DUMP MCU programs
  in MAME (lastmisn "not verified to be the same data as the A MCU dump",
  gondo "hand-crafted from the US version", lastmisnj and srdarwinj marked
  BAD_DUMP); they are still supported and compared against MAME, but a
  difference that traces to their MCU program is not a core bug (R1).
- 5.4 Karnov sprite flip (Lee, 2026-10-03): MAME's behaviour is the default
  (the Karnov sprites of lastmisn/gondo are not flipped when the screen
  flips, because dec8.cpp never sets the sprite chip's flip flag), behind a
  one-bit parameter so the other behaviour costs nothing to switch to. A
  separate research task is looking for real PCB 1CC footage on YouTube to
  validate it (R7).
- 5.5 Gondomania rotary joystick (Lee, 2026-10-03): support both a
  spinner/paddle input and a button mapping (rotate left/right) for the
  12-position rotary; M4 shell work. DONE (M4): buttons, spinner and
  paddle all active at once (rtl/d8_rotary.sv, docs/m4_findings.md 4).

## 6. Research items

| # | Question | Evidence that would close it |
|---|---|---|
| R1 | What do the BAD_DUMP MCU programs (lastmisn "e", gondo "e" hand-crafted, srdarwinj) differ in; is the gondo second coin failure (MAME TODO) a property of the hacked dump? | a verified dump of each MCU; comparing gondo with gondou behaviour in M2 |
| R2 | Priority PROMs (dl-14.9c, ds-23.b10, dy_11.c11) are unused by MAME; MAME's fixed rules may differ from the hardware | decode the PROMs against MAME's rules in M1; PCB footage of overlaps |
| R3 | Sprite buffer copy duration and timing (MAME copies instantly at the write) | schematics (gondo schematics exist per MAME comments) or PCB timing |
| R4 | Does Gondomania ever enter 6309 native mode or use 6309-only opcodes in gameplay? | CLOSED (M2): gameplay trace of 6,000 frames, 72.3 M instructions, 90 distinct mnemonics, all 6809, no LDMD (m2_findings 1) |
| R5 | Live rendering of mid-scan tile/palette/scroll writes vs MAME's frame-at-once | frame-by-frame PCB footage of a frame with a mid-scan text or scroll write |
| R6 | srdarwin double-height sprites at the top are clipped in MAME (TODO): do they wrap on hardware? | PCB footage of a sprite entering from the top |
| R7 | The Karnov sprite chip's flip flag is never set in dec8.cpp, so MAME draws lastmisn/gondo sprites unflipped when the screen is flipped; the M0 flip run matches MAME this way. Does the hardware flip them, or does the program compensate? | PCB footage in flip mode (a research task is searching YouTube for real PCB 1CC footage, decision 5.4); the program's sprite coordinates in flipped frames |
| R8 | gondo NMI-enable latency ("1 more opcode") and MCU INT1 auto-clear (4 vs 64 ticks, not confirmed) | INT1: the Gondomania schematic [GONDO-TSM sheet 26, PDF p. 44] drives 8751 INT1 from QA of a 74LS194 shifting ones in from *SECREQ, low for four *12H clocks (two readings agree, m2_findings 5), supporting MAME's 4 ticks; *12H frequency still to read. NMI enable: the DE-0269 gate sheet, not yet traced. M2 implements MAME (enable one 3 MHz CPU cycle after the write; INT1 4 ticks of 1.5 MHz); interrupt counts per frame equal MAME's |
| R9 | srdarwin MCU clock ("unknown frequency") and main CPU type ("MC68A09EP or HD63?09EP") | PCB photos Related evidence (M3): the Last Mission schematic shows its 8751 (18B) on an 8 MHz crystal X1 (LM-SCH PDF p. 15), the frequency MAME uses for all three |
| R10 | srdarwin fix layer colour fixed at 0 ("?") | PCB footage of the text layer colours |
| R11 | mc6809i licence | CLOSED (M2): BSD-3-Clause, cavnex/mc6809 documentation/LICENSE.md (rtl/vendor/mc6809i/PROVENANCE.md) |
| R12 | Does the PCB limit sprites per line? The core draws the whole list (256 Karnov, 128 srdarwin) on one line (m1_findings 4) | PCB footage of a crowded line; schematics |
| R13 | Last Mission's MCU writes 0x00 to its own P0 and then reads the main CPU's byte from P0; MAME forces the P0 input bits to the latched byte on P2.4 falling (dec8.cpp:741-746). The 8751's P0 is open drain and needs a 1 in the latch to read (MCS51 p. 3-7). WIRING SETTLED (M3, Last Mission schematic sheet 11 = LM-SCH PDF p. 15): P0 (pins 32-39) has a 5.6 kOhm x 8 pull-up pack (RA1) and is driven directly by the LS374 at 16C (clocked by the main CPU's *SECREQ, output enabled by P2.4, pin 25), with no isolation; P1 the same from 15C (*SECWRD, P2.5). With 0x00 in its P0 latch the 8751 pulls the pins low against the LS374's outputs, so the board relies on the LS374 overdriving the 8751's pull-down transistors: MAME's forced input models the outcome. Kept as M2 implements it (jt8051 patch 2). Open only for the electrical margin (a read with the latch at 0x00 is a bus fight) | a logic probe on P0 of a working board during the P2.4 read |
| R14 | 8051 interrupt response: jt8051 latches at S5P2 and polls in the next machine cycle, at least 3 machine cycles to the service routine, as Intel documents (MCS51 p. 3-25, 3-26); MAME enters at the next instruction boundary. Changes Gondomania's random source in gameplay and SRD's MCU clock (m2_findings 3.3 to 3.8). CPU rule settled for the core | the board's INT0 edge against the MCU clock (logic analyser on a PCB) |
| R15 | mc6809i (jtframe copy) clears V on SEX; MAME leaves V unchanged. Motorola disagrees with itself (6809E data sheet PDF p. 31: V cleared; programming manual p. A-62: not affected). No compared stream differs because of it | a hard-part test of SEX on V |
| R16 | Gondomania main CPU: the DE-0269 component list says 6809E (GONDO-TSM manual p. 3, PDF p. 22); MAME says HD63C09EP at 3 MHz, above Motorola's fastest 6809E grade (2.0 MHz). The core runs a 6809E at 3 MHz (m2_findings 2.1). M3: the clock-generator sheet (GONDO-TSM PDF p. 30: E and Q from flip-flops 1E/3E, clocked from *M1H / M1H / HCLK of sheet 19) carries the note beside jumper K1 "3MHz動作にてカットする (1ケ所)" (cut for 3 MHz operation, one place): the board was designed with a jumper-selected 3 MHz CPU clock, which supports MAME's 3 MHz. Not shown: which setting production boards shipped with | a production board's K1 or a measured E clock |
| R17 | Sound timer IRQs lost while masked. CLOSED 2026-10-04 (m3_findings 7.1): jt65c02 ADC/SBC and not-taken branches fixed to the R65C02 data sheet; lastmisn and go_play IRQ counts now equal MAME's; the remaining OPL timer phase is jtopl's free-running prescaler, which the YM3812 die-level model also has (MAME differs) | done |
| R18 | Power-on: Gondomania's 6502 makes its first YM2203 write before the first NMI in the core, after it in MAME (m3_findings 3.1) | the board's reset release order |
| R19 | DECO 222: NMOS (MAME) or CMOS (jt65c02) timing; SRD uses jmp (ind), 5 cycles NMOS, 6 CMOS (m3_findings 3.3) | a DECO 222 cycle measurement |
| R20 | Mix balance. The 1:1 of m3_findings 7.2 (schematics) was superseded on 2026-10-04 by a PCB recording of SRD (docs/r20_pcb_audio_check.md): OPL:FM 1.65, SSG 3400-3900 for FM 102. Set FM 102, OPL 170 (all three games), SSG 3600; output AC coupled as the boards. CLOSED for SRD; lastmisn/gondo inferred (same chips and network) | a Last Mission or Gondomania PCB recording would confirm theirs |
| R21 | jt65c02 page-crossing cycle counts: STA abs,X/Y 6 (data sheet 5), RMW abs,X 8 (7), LDA (zp),Y 5 (6); not reached in the sound programs' timer paths (rtl/vendor/jt65c02/PROVENANCE.md) | fix with a full M2/M3 regression |
| R22 | d8_video reads tile codes ahead of the beam on a schedule set by its graphics fetches, so a CPU write racing the beam can land on either side of the read depending on the ROM latency: the M4 board run and the M2 harness differ in 32 pixels of one frame (lastmisn displayed frame 180, m4_findings 6) | PCB footage of the fix-layer clear in Last Mission's attract; or read tile codes at fixed slots per line so the result no longer depends on the SDRAM |
