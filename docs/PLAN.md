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
| MC6809E x2 (lastmisn), MC6809E (srdarwin) | jtframe `mc6809i.v` (Greg Miller, "Cycle-Accurate 6809 Core"), as wrapped by `jtframe_sys6809.v` | header has a copyright line, no licence text: needs-review before vendoring | M2 |
| HD6309E (gondo) | the same 6809 core: the 2,930-frame attract trace (36.1 M instructions) shows only 6809 mnemonics and no LDMD, so the 6309 stays in emulation mode, where its timing equals the 6809's; a gameplay trace must confirm (R4) | as above | M2 |
| R65C02 (lastmisn, gondo sound) | jtcores `jt65c02` (jt680x) | GPL-3.0-or-later | M3 |
| DECO 222 (srdarwin sound) | 6502 with opcode-fetch bits 5 and 6 swapped (deco222.cpp): a wrapper on a 6502 core (jt65c02 in 6502 mode or T65) | own wrapper | M3 |
| i8751 | jtcores `jt8051` | GPL-3.0-or-later | M2 |
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
| M2 | full system: 6809 x2 / 6309-as-6809 / 6809, i8751, memory maps, interrupts, MCU protocol, inputs, DIPs | boots from power-on match MAME's I/O streams, images and RAM; divergences root-caused |
| M3 | sound: 6502/R65C02/DECO 222, YM2203, YM3526/YM3812, latches and NMIs | register streams and level against MAME WAVs |
| M4 | MiSTer shell, SDRAM, MRAs (DIPs from the driver, machine byte, srdarwinb sprite byte swap done by the MRA interleave), rotary input for Gondomania, Quartus timing at 96 MHz | board sim equals M2; timing closed; first RBF on hardware |
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
  12-position rotary; M4 shell work.

## 6. Research items

| # | Question | Evidence that would close it |
|---|---|---|
| R1 | What do the BAD_DUMP MCU programs (lastmisn "e", gondo "e" hand-crafted, srdarwinj) differ in; is the gondo second coin failure (MAME TODO) a property of the hacked dump? | a verified dump of each MCU; comparing gondo with gondou behaviour in M2 |
| R2 | Priority PROMs (dl-14.9c, ds-23.b10, dy_11.c11) are unused by MAME; MAME's fixed rules may differ from the hardware | decode the PROMs against MAME's rules in M1; PCB footage of overlaps |
| R3 | Sprite buffer copy duration and timing (MAME copies instantly at the write) | schematics (gondo schematics exist per MAME comments) or PCB timing |
| R4 | Does Gondomania ever enter 6309 native mode or use 6309-only opcodes in gameplay? | gameplay trace in M2 (attract: none in 36.1 M instructions) |
| R5 | Live rendering of mid-scan tile/palette/scroll writes vs MAME's frame-at-once | frame-by-frame PCB footage of a frame with a mid-scan text or scroll write |
| R6 | srdarwin double-height sprites at the top are clipped in MAME (TODO): do they wrap on hardware? | PCB footage of a sprite entering from the top |
| R7 | The Karnov sprite chip's flip flag is never set in dec8.cpp, so MAME draws lastmisn/gondo sprites unflipped when the screen is flipped; the M0 flip run matches MAME this way. Does the hardware flip them, or does the program compensate? | PCB footage in flip mode (a research task is searching YouTube for real PCB 1CC footage, decision 5.4); the program's sprite coordinates in flipped frames |
| R8 | gondo NMI-enable latency ("1 more opcode") and MCU INT1 auto-clear (4 vs 64 ticks, not confirmed) | schematics, M2 interrupt timing against MAME |
| R9 | srdarwin MCU clock ("unknown frequency") and main CPU type ("MC68A09EP or HD63?09EP") | PCB photos |
| R10 | srdarwin fix layer colour fixed at 0 ("?") | PCB footage of the text layer colours |
| R11 | mc6809i licence | the original repository's licence file |
| R12 | Does the PCB limit sprites per line? The core draws the whole list (256 Karnov, 128 srdarwin) on one line (m1_findings 4) | PCB footage of a crowded line; schematics |
