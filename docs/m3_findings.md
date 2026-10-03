# M3 findings (DEC8 sound)

Date: 2026-10-03. Scope: the sound board of the three machines (6502
family CPU, YM2203, YM3526 / YM3812, sound latch and NMI) inside `d8_sys`,
booted from power-on with the main system of M2, compared with MAME 0.288:
every chip register write, latch transfer and interrupt (order, value,
time), the 6502's RAM every 100 frames, and the audio against MAME's WAV.

The vendor cores write SIMULATION-only dumps (`sim/jt12.raw`,
`sim/jtopl.raw`, `sim/opl_wr.log`, ignored by git).

Reproduce (from `sim/`): `make m3-build`, `make m3-oracle` (MAME with the
sound log and `-wavwrite` at 48 kHz, cfg and nvram wiped per run by
`mame/run_mame.sh`), `make m3-boot` (the core, 3 runs at a time, nice 15),
then per run `m3/compare_snd.py`, `m3/compare_sndram.py`,
`m3/compare_audio.py --fit`.

## 1. Gate result

Runs: the M2 captures' inputs, cut at 3600 frames (60 s); Gondomania cut
before its first random choice (m2_findings 3.5: go_play 1740,
go_attract 2700), because after it the main program differs by design.

Event kinds: L main CPU latch write, Y YM2203 write, P OPL write, R 6502
latch read, N / I NMI / IRQ entry, U unmapped access.

| Run | Frames | L (main to sound) | Y stream | P stream | IRQs taken core / MAME | Timing of equal events | 6502 RAM | Audio: RTL mix vs MAME, 20 ms envelope corr. |
|---|---|---|---|---|---|---|---|---|
| lm_play | 3600 | 180, identical | 6852, identical | 328952, identical | 54234 / 54234 | p50 0.8 us, p99 34 us, max 136 us | identical on all 36 dumps (stack page aside) | -0.16 dB, 0.965 |
| lm_attract | 3600 | 116, identical | identical to frame 2020 (16494 both) | identical to frame 3397, then 18 fewer | 54017 / 54020 | to frame 1104: p50 0.8 us, max 81 us | 0x0001-0x0002 differ from frame 2000 (3.2) | -0.24 dB, 0.959 |
| go_attract | 2700 | 129, identical | identical to frame 2512 (7236 / 7304) | identical in content, ends 40 short | 40372 / 40378 | see 3.1, 3.3 | 0x0001-0x0002 from frame 2000s; 0x0018 transient | -0.36 dB, 0.983 |
| go_play | 1740 | 6, identical | 310, identical | identical in content, ends 12 short | 26160 / 26162 | startup as 3.1; Y p50 30 us, max 229 us | 0x0001-0x0002 from frame 1400; 0x0018 transient | -0.53 dB, 0.981 |
| sr_attract | 3600 | 893, identical | identical to frame 725 (76344 / 76830) | identical to frame 546, then one timer period behind (3.3) | 51509 / 51679 | to frame 3: p50 0.8 us, max 4.3 us | 0x0001-0x0002 from frame 100; music work bytes later | -0.54 dB, 0.897 |
| sr_play | 3600 | 109, identical | identical to frame 2221 (23006 / 23022) | as sr_attract | 53656 / 53669 | as sr_attract | as sr_attract | -0.16 dB, 0.942 |

No run made an unmapped 6502 access, a ROM write or a chip read
(`sndunm 0`, no U and no chip R events in either log). The 6502 reads only
the latch, once per NMI.

Gate: every command from the main CPU arrives in the same order with the
same value in every run; the chip register streams are identical except
where the 6502 takes a different number of timer IRQs (3.2), after which
the music runs one timer period apart from MAME's and the streams drift.
Level within 0.6 dB of MAME in every run (RTL mix RMS, 20 Hz to 3.5 kHz).

## 2. What was built

`rtl/d8_snd.sv`, instantiated in `rtl/d8_sys.sv` (new ports: sound ROM
load, the three chip outputs and the mix, a debug counter):

- CPU: jt65c02 (jotego, GPL-3.0-or-later) with its DECO222 parameter set;
  the opcode bit 5 / 6 swap enabled on srdarwin only. Microcode generated
  with `jtframe ucode jt680x deco222`, vendored as `deco222.uc`
  (`rtl/vendor/jt65c02/PROVENANCE.md`). One build serves R65C02
  (lastmisn, gondo) and DECO 222 (srdarwin).
- YM2203: jt03 (as in the Dooyong core). OPL: jtopl2 (jtopl commit
  7ac0c81); YM3526 behaviour on lastmisn / gondo by masking register 01
  bit 5 (the OPL2 wave-select enable) on its way in, which keeps jtopl2 on
  jtopl's OPL1 operator path.
- Clocks (96 MHz system): 6502 cen 6 MHz (4 per 1.5 MHz bus cycle),
  YM2203 1.5 MHz, OPL 3 MHz (dec8.cpp:1992, 2031, 2038 and the gondo /
  srdarwin equivalents).
- Maps, latch, NMI and IRQ from dec8.cpp:625-658, 144-149, 233-238,
  2025-2039 (header of `d8_snd.sv`).
- Mix: MAME's routes (SSG 0.20 per channel, FM 0.40, OPL 0.80, gondo OPL
  0.50) in 1/256 units, signed, saturated (4.2 for the schematic's mix).

### 2.1 Chip write and busy wiring (the Tecmo 16 YM2151 lesson)

- The 6502 never reads either chip in any run (oracle log: no chip R
  events in 2.1 M sound events over the six runs), so status and busy are never polled:
  busy duration differences between datasheets, jt03 (busy 32 synthesizer
  cycles after a data write, `jt12_mmr.v:431`) and ymfm cannot change
  program flow on DEC8. The YM3526's status register has no busy flag
  (YM3526 datasheet register map).
- Writes: one bus write gives one one-clock chip select (`wev`). jt03
  (`jt12_top.v:86`) and jtopl (`jtopl.v:87`) take the write on the system
  clock and hold it for their own clock enable, so no hold-until-cen
  logic is needed (unlike jt51 in Tecmo 16). Verified by the identical
  register streams and level.
- Reset: jt03 and jtopl clear their operator pipelines only on clock
  enables while in reset. With enables frozen during reset, jt03 left
  reset with a garbage envelope pipeline and output a large wandering FM
  signal while MAME was silent. The enables now run through reset; the
  output is silent until the first key-on, as MAME. The YM2203 needs
  reset held for at least 72 master clocks and the YM3526 for 80; the M4
  board reset must hold the sound board in reset at least that long with
  the enables running. This is very likely also the cause of the Dooyong
  core's "jt03 constant before the first write" note.

## 3. Divergences from MAME (root causes)

### 3.1 Startup: the first YM2203 write and the first NMI swap places (go_attract)

Gondomania's main CPU writes the latch 14.5 us after reset. MAME's 6502
takes the NMI (19.3 us) before its first YM2203 write (38.7 us); the
core's 6502 has already made that write (15.7 us) when the NMI arrives
(19.7 us). The 6502 starts a few cycles earlier in the core relative to
the main CPU. From event 4 the streams are identical. Effect: one register
write at power-on in a different order. Accurate side: unknown (depends on
when the board releases the sound CPU from reset relative to the main
CPU). Open (R18).

### 3.2 Timer IRQs lost while the NMI handler runs (lm_attract, go_attract)

The music is paced by OPL timer 1 (register 2 = 0xF4, period 1.152 ms;
the IRQ handler writes 4 = 0x80, 2 = 0xF4, 4 = 0x01). During a long NMI
handler the 6502 runs with interrupts masked; the timer flag stays set,
and a second expiry inside the masked period is lost. How many expiries
are lost depends on the handler's length to the cycle. In lm_attract the
core takes 3 fewer IRQs than MAME over 60 s (first at frame 1906, which
puts the music one timer period behind MAME; Y diverges at 2020); in
go_attract 6 fewer (Y diverges at 2512). RAM 0x0001-0x0002 (the tick
count) differs from then on.

Narrowed to the 6502's cycle count, not the chips: at lm_attract frame
740 the NMI handler's OPL key-off loop (registers B8 to B0, `sta $1000`
/ `sta $1001` routines at 8C3B / 8C44 padded with NOPs) runs 204.0 us per
iteration in the core against 200.7 us in MAME, 5 bus cycles more
(event logs, 1.5 MHz). The 6502 never reads the chips, so only CPU
timing can make that difference. Also contributing: OPL timer restart
semantics. ymfm starts timer 1 exactly at the write; jtopl's timer
counts on a free-running /4 prescaler of the sample clock, so the first
period after a restart is up to 3 samples (72 us) short. The core's IRQ
intervals after long handlers differ from MAME's by up to 80 us because
of this.

Accurate side: open. The R65C02 instruction timing in the handler needs a
cycle trace of both (tools are in place: `+sndtrace=F0:F1:file` in
`m2/tb_sys.cpp`, `SNDTRACE_CYC=1` in `d8_oracle.lua`) and comparing each
instruction against the Rockwell R65C02 data sheet. For the timer, the
YM3526 data sheet does not say whether the timer prescaler is reset by
the start bit; a die-level model or a board measurement would. R17.

### 3.3 SRD: DECO 222 is an NMOS 6502 in MAME, CMOS in jt65c02

MAME derives deco222 from its NMOS m6502; jotego's DECO222 microcode is
the 65C02 set. A trace of SRD's sound program (MAME, 2400 frames) uses
only opcodes common to both, and one instruction whose timing differs:
`jmp ($000a)` (NMOS 5 cycles, CMOS 6). In both SRD runs the core loses
one timer IRQ within the first 100 frames (1496 against 1497), so its
music runs one timer period (1.152 ms) behind MAME's from frame 3; the
register streams are the same sequence shifted (first visible as a
reordering at frame 546). Over sr_attract the core takes 170 fewer IRQs
(0.33%): the music tempo is 0.33% slower than MAME's, about 0.2 s behind
at 60 s, which is why the envelope correlation drops to 0.41-0.65 in the
middle of that run while the level stays within 0.7 dB. sr_play loses 13.
Same mechanism as 3.2 (IRQs lost while masked), with the extra CMOS cycle
on `jmp (ind)` a likely contributor. Accurate side:
unknown (the DECO 222 is a Data East custom; whether it is NMOS or CMOS
is not documented). R19.

## 4. Decisions for Lee

- **4.1 Mix balance (schematics vs MAME).** Both schematics sum the FM DAC
  and the OPL DAC through equal 10 kOhm resistors: Last Mission sheet 27
  (LM-SCH PDF p. 31: YM3014 2H for SOUND0 and 1H for SOUND1, each through
  a 3403 buffer and 4.7 uF to 10 kOhm, R4 for the OPL, into the AUDIO node
  and VR1), Gondomania sheet 28 (GONDO-TSM PDF p. 46: same, YM2203 at 3J,
  YM3526 at 3H). MAME weights the OPL 2x the FM on lastmisn / srdarwin
  (0.80 / 0.40) and 1.25x on gondo (0.50 / 0.40). Both DACs are YM3014s
  fed the chips' 16-bit range, so the boards weight FM and OPL 1:1 if the
  emulated chip outputs share the DAC scale. SSG: Last Mission sums the
  three channels through 1 kOhm each into 470 Ohm and then 56 kOhm into
  the node; Gondomania takes each channel through 10 uF and 56 kOhm with a
  10 kOhm load. The SSG level relative to the DACs needs the YM2203's
  analog output level and the YM3014's swing, not settled here. The core
  keeps MAME's balance for M3 (fitted gains below agree within 1.5 dB).
  Recommendation: switch FM:OPL to 1:1 after a second reader confirms the
  jt03 and jtopl output scales are the DAC scale; ideally checked against
  a PCB recording (the srdarwin 1CC videos of the footage report).
  Fitted gains from MAME's WAV (x256, NNLS on 20 ms window power): FM
  79-122 (set 102), SSG 2920-3270 (set 2775), OPL 170-198 on lastmisn /
  srdarwin (set 205), 132-135 on gondo (set 128).
- **4.2 DECO 222 NMOS or CMOS (3.3).** Kept as jt65c02 provides (CMOS
  timing).
- **4.3 SRD music dropout.** The real-board bug in the PCB footage report
  (music drops out on any stage, returns after the boss or a death) is
  not reached by these captures (60 s each); test in M5 on hardware with
  long play.

## 5. Research items

Settled in M3 (PLAN.md section 6):

- R13 (Last Mission MCU P0): schematic read, wiring settled (PLAN R13).
- R16 (Gondomania CPU clock): the clock sheet's K1 note supports 3 MHz
  (PLAN R16).
- R9 related: Last Mission's 8751 is on an 8 MHz crystal (LM-SCH p. 15).

New:

- R17 timer IRQ count (3.2): 6502 cycle timing in the NMI handler and the
  OPL timer restart.
- R18 power-on order of the sound CPU's first write and NMI (3.1).
- R19 DECO 222 NMOS or CMOS (3.3).
- R20 mix balance (4.1).

## 6. Sources

| Tag | Document | Used for |
|---|---|---|
| LM-SCH | Data East USA, Last Mission Operation and Service Manual with schematics, `../mister-arcade-survey/datasheets/boards/lastmisn/Last-Mission.pdf`, md5 977e716672a959f8ab76a51fe58680b7, 52 pages | R13 (sheet 11, PDF p. 15), 8751 crystal (p. 15), mix network (sheet 27, PDF p. 31) |
| GONDO-TSM | Gondomania Operation and Service Manual, `../mister-arcade-survey/datasheets/boards/gondomania/Gondomania.pdf`, md5 cc39ffa8ad1c3543b502063aab32b99e | R16 (PDF p. 30, K1 note), mix network (sheet 28, PDF p. 46) |
| YM2203 | Yamaha YM2203 data sheet (1989) and manual, `../mister-arcade-survey/datasheets/ym2203/` | reset length, timers |
| YM3526 | Yamaha YM3526 data sheet, `../mister-arcade-survey/datasheets/ym3526/` | status register (no busy flag), timer 1 (80 us units), reset length |
| YM3812 | Yamaha YM3812 Application Manual (1994), `../mister-arcade-survey/datasheets/ym3812/` | srdarwin OPL2 |
| MAME | MAME 0.288 dec8.cpp, deco222.cpp (`reference/mame/v0288/`); ymfm_opl.cpp, ymfm_fm.ipp (`reference/mame/v0288/ymfm/`, mamedev/mame tag mame0288) | maps, routes, timer semantics (ymfm_fm.ipp:1474-1590) |

HDL: jt65c02, jt03, jtopl (`rtl/vendor/*/PROVENANCE.md`). Where a document
and MAME disagree the document is preferred as evidence; where the
evidence is incomplete the item stays open.
