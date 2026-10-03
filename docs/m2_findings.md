# M2 findings (DEC8 full system)

Date: 2026-10-03. Scope: the main system of every set (6809 main CPU,
Last Mission's second 6809, the i8751 MCU, work RAM, memory maps, bank and
control registers, interrupts, inputs, DIPs, video) booted from power-on in
Verilator and compared with MAME 0.288 frame by frame. The sound CPU and
chips are M3: the main CPUs never read the sound side (the sound latch is
write-only, dec8.cpp:625-658), so they cannot change program flow here.

Reproduce (from `sim/`): `make m2-build`, `python3 m2/run_oracle.py 3`
(MAINRAM reruns of every M0 capture, about 1 minute each),
`python3 m2/run_boots.py --jobs 4` (every capture on the core from power-on;
`m2/build_fast.sh` builds the same harness with -O3 into build/m2fast),
`python3 m2/compare.py <run> ...`.

## 1. Gate result

Every M0 capture booted from power-on on the core (Verilator, `d8_sys` with
the program ROM latency model at 9 clocks) and in MAME 0.288 with the same
inputs replayed (MAINRAM reruns, `m2/run_oracle.py`), compared by
`m2/compare.py` and tabulated by `m2/gate_table.py`: the I/O write stream
of each CPU (address, value, order; beam position as a delta), the
interrupts taken per frame, every dump's work RAM, MCU RAM and video RAM,
and every dump's image (exact, live = mid-scan writes per M1, or
unexplained).

Whole captures (Gondomania rows include the play after the divergence of
3.5, so their differences there are expected):

| Run | Frames | I/O writes main / sub | Moved | Beam delta px (min / median / max) | Interrupt frames differ | Images exact / live / unexplained | Work RAM byte differences summed over dumps (dead stack / idle counter / transient / other persistent) | MCU RAM (tick / other) | Video RAM persistent | Counters | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lm_attract | 11993 | 78984 / 8757 | 0 | -28 / 4 / 64 | 0 | 1964 / 60 / 0 | 1679 / 0 / 6 / 0 | 0 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | PASS |
| lm_play | 6000 | 20356 / 3508 | 0 | -28 / 4 / 64 | 0 | 1235 / 16 / 0 | 313 / 0 / 0 / 0 | 0 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | PASS |
| clone_lastmisnu6 | 9000 | 58879 / 6466 | 0 | -28 / -8 / 64 | 0 | 291 / 9 / 0 | 244 / 0 / 0 / 0 | 0 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | PASS |
| clone_lastmisnu5 | 9000 | 58879 / 6466 | 0 | -28 / -8 / 64 | 0 | 291 / 9 / 0 | 192 / 0 / 0 / 0 | 0 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | PASS |
| clone_lastmisnj | 9000 | 58753 / 6180 | 0 | -28 / 0 / 64 | 0 | 286 / 14 / 0 | 180 / 0 / 1 / 0 | 0 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | PASS |
| sr_attract | 11993 | 128430 / 0 | 1 | -44 / 4 / 40 | 0 | 2022 / 2 / 0 | 632 / 0 / 0 / 0 | 104 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 1 xacc 0 | PASS |
| sr_play | 6000 | 61848 / 0 | 0 | -40 / 8 / 40 | 0 | 1323 / 3 / 0 | 1654 / 0 / 0 / 0 | 55 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 1 xacc 0 | PASS |
| sr_flip | 5981 | 65970 / 0 | 1 | -16 / 12 / 40 | 0 | 299 / 0 / 0 | 136 / 0 / 0 / 0 | 10 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 1 xacc 0 | PASS |
| clone_srdarwinj | 9000 | 87515 / 0 | 0 | -28 / 4 / 40 | 0 | 300 / 0 / 0 | 300 / 0 / 0 / 0 | 16 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 1 xacc 0 | PASS |
| clone_srdarwinb | 9000 | 91252 / 0 | 0 | -28 / 4 / 40 | 0 | 299 / 1 / 0 | 125 / 0 / 0 / 0 | 0 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 1 xacc 0 | PASS |
| go_attract | 11993 | 791541 (first diff #133167) / 0 | 0 | -320 / 0 / 16 | 74 | 1018 / 11 / 995 | 9447 / 2018 / 1415 / 610426 | 0 / 0 | 4799 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | DIFF (3.5) |
| go_play | 6000 | 343554 (first diff #77084) / 0 | 0 | -116 / 4 / 66 | 4 | 810 / 91 / 425 | 1284 / 1187 / 29 / 40814 | 0 / 1 | 2665 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | DIFF (3.5) |
| go_flip | 5981 | 354930 (first diff #133167) / 0 | 0 | -320 / 0 / 16 | 24 | 157 / 3 / 139 | 840 / 297 / 656 / 46272 | 0 / 0 | 636 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | DIFF (3.5) |
| clone_gondou | 9000 | 624078 (first diff #28584) / 0 | 0 | -556 / -2 / 404 | 40 | 63 / 9 / 228 | 1990 / 296 / 1135 / 169045 | 0 / 0 | 1026 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | DIFF (3.5) |
| clone_makyosen | 9000 | 486295 (first diff #94446) / 0 | 0 | -222 / 2 / 64 | 40 | 107 / 5 / 188 | 1893 / 297 / 1020 / 109624 | 0 / 0 | 902 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | DIFF (3.5) |

Gondomania sets up to the frame before their first beam step of more than
20 pixels (the start of the 3.5 window; the dump that follows is the first
with a persistent RAM difference):

| Run | Frames | I/O writes main / sub | Moved | Beam delta px (min / median / max) | Interrupt frames differ | Images exact / live / unexplained | Work RAM byte differences summed over dumps (dead stack / idle counter / transient / other persistent) | MCU RAM (tick / other) | Video RAM persistent | Counters | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| go_attract | 2696 | 131353 / 0 | 0 | -18 / 0 / 16 | 0 | 862 / 0 / 0 | 323 / 860 / 0 / 0 | 0 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | PASS |
| go_play | 1746 | 67255 / 0 | 0 | -18 / 4 / 16 | 0 | 262 / 0 / 0 | 175 / 144 / 0 / 0 | 0 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | PASS |
| go_flip | 2696 | 131353 / 0 | 0 | -18 / 0 / 16 | 0 | 134 / 0 / 0 | 74 / 133 / 0 / 0 | 0 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | PASS |
| clone_gondou | 1469 | 26409 / 0 | 0 | -16 / -2 / 16 | 0 | 49 / 0 / 0 | 6 / 46 / 0 / 0 | 0 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | PASS |
| clone_makyosen | 2063 | 75375 / 0 | 0 | -18 / 0 / 16 | 0 | 68 / 0 / 0 | 54 / 68 / 0 / 0 | 0 / 0 | 0 | overruns 0 verr 0 promlate 0 unmapped 0 xacc 0 | PASS |

Columns: beam delta = core minus MAME position of each equal write, in
pixels; moved = writes in the same frame on the other side of an
interrupt (3.9); work RAM classes are byte differences summed over all
dumps (dead stack below S, idle counter, transient = differs at one dump
only, other persistent); MCU tick = SRD's MCU clock (3.8); counters from
the run's last line (`unmapped` 1 on SRD is 3.7).

- **Last Mission** (lastmisn, lastmisnu6, lastmisnu5, lastmisnj; attract
  and gameplay, both CPUs and the MCU): equal I/O streams, interrupts and
  RAM on every run. lastmisn and lastmisnj carry BAD_DUMP MCU programs
  (PLAN 5.3); they match MAME, which runs the same programs, so this says
  nothing about R1.
- **SRD** (srdarwin, srdarwinj, srdarwinb): equal, with one bank write
  moved across an NMI in frame 4267 (3.9) and the MCU clock tick (3.8).
- **Gondomania** (gondo, gondou, makyosen): equal until the game reads
  its idle counter as a random number (3.5): every check passes on
  go_play to frame 1746, go_attract and go_flip to 2696, gondou to 1469,
  makyosen to 2063. In the next few frames the beam positions step (up to
  556 pixels on gondou) and the following dump differs; the cause is the
  MCU interrupt timing of 3.3.
- **Counters**: renderer overruns, snapshot errors, late program fetches,
  MCU MOVX accesses 0 on every run; `unmapped` 1 on SRD (3.7).
- **Soak**: lastmisnu6 attract, 20,000 frames from power-on (both CPUs,
  MCU, video), every counter 0, the game still writing at frame 20,000
  (`build/m2/soak`).
- **Program ROM latency**: 28 clocks at 3 MHz pass, 29 fail (2.2).
- **Pause**: SRD paused at frame 200 for 60 frames: no CPU or MCU write
  while paused, the paused frames identical, and the I/O stream after it
  equal to MAME's shifted by exactly 60 frames.
- **R4**: Gondomania never leaves 6809 emulation mode in gameplay (5).


## 2. What was built

| File | Content |
|---|---|
| `rtl/d8_sys.sv` | clocks and enables, two mc6809i (main, Last Mission sub), the three memory maps, work RAM, bank/control/scroll/flip registers, IRQ/FIRQ/NMI logic and gates, input ports, MCU glue (port latches, INT0/INT1, P2 handshakes), sound latch output, d8_video, gate counters |
| `rtl/d8_mcu.sv` | i8751: jt8051 with its 4 KB program ROM (loader port) and 128-byte internal RAM, wired as jtframe's jtframe_8751mcu |
| `rtl/d8_video.sv` | M1 video; new output `o_vcnt` (the system derives MAME's vblank from it); no other change |
| `rtl/vendor/mc6809i/` | cycle-accurate 6809 (Greg Miller, BSD-3-Clause; jtframe's clock-enable copy), PROVENANCE.md |
| `rtl/vendor/jt8051/` | jt8051 (jotego, GPL-3.0-or-later) with its generated microcode and three documented DEC8 patches, PROVENANCE.md |
| `tools/uctool/` | the 30-line Go driver around jtframe's ucode generator that produced jt8051's microcode tables |
| `sim/m2/tb_sys.cpp` | harness: SDRAM image, program ROM latency model, MCU ROM load, graphics ROM model, input replay, captures, I/O and interrupt logs, PC/bus/MCU traces, pause |
| `sim/m2/run_oracle.py`, `run_boots.py`, `compare.py`, `gate_table.py`, `quickcmp.sh`, `trace_cmp.py`, `build_fast.sh`, `ports_probe.lua`, `mcu_p2_probe.lua` | MAME reruns, core runs, comparison, debugging |
| `sim/mame/d8_oracle.lua` | `MAINRAM=1`: work RAM in d8_sys's layout, MCU internal RAM, CPU state per dump frame |
| `sim/mame/trace/trace_window.lua`, `trace_fifo_inputs.lua` | MAME debugger traces over a frame window; with replayed inputs (R4 on gameplay) |
| `reference/mame/v0288/cpu/`, `machine/` | MAME 0.288 i8051, 6809/6309 and input_merger sources read for this milestone (BSD-3-Clause, not built) |

### 2.1 CPU and MCU cores (licences)

- **6809: mc6809i** (Greg Miller, "Cycle-Accurate 6809 Core", validated on
  hard MC6809/MC6809E parts; cavnex/mc6809). Licence: the author offers
  the standard 3-clause BSD licence (or a binary-only variant); this core
  takes the BSD licence, compatible with GPL-3.0. **R11 closed.** The file
  is jtframe's copy (jtcores a72a4460): E/Q converted to clock enables,
  plus three behaviour changes reviewed by diff and documented in its
  PROVENANCE (SEX sets N/Z and clears V; NMI arms on a write to S; S
  resets to 0).
- **Gondomania's main CPU: a 6809E, on the same core.** The Data East USA
  component list for the DE-0269 board names it "CPU 6809E 100-0189-01
  1F" [GONDO-TSM, manual p. 3, PDF p. 22, section 2a "Component List"];
  MAME declares an HD6309E at 3 MHz with the comment "HD63C09EP"
  (dec8.cpp:2106). The list gives no maker or speed grade. Motorola's
  6809E grades stop at 2.0 MHz (MC68B09E) [6809E-DS, ordering
  information], so a 3 MHz clock needs a faster part such as Hitachi's
  HD63C09E, whose emulation mode "acts and executes instructions the same
  as the 6809" [HD6309-TRG, "Modes of Operation"]. The program never
  executes LDMD or any other 6309 instruction (R4: 108 M traced
  instructions), so the 6309 stays in emulation mode. The core runs
  mc6809i, a 6809E, at MAME's 3 MHz: the documented part, and what the
  6309 does with this program. The clock itself is not yet read from the
  schematics (R16).
- **i8751: jt8051** (Jose Tejada, GPL-3.0-or-later), "cycle-scheduled",
  verified by its author against MCS-51 vectors. Its microcode is generated
  from `ucode/8051.yaml` by jtframe's tool; the generator reported every
  instruction cycle-accurate.
- Not used: Coin-Op Collection's cobracom/oscar (no public HDL; their module
  library is CC BY-NC); jtframe's other wrappers (re-implemented minimally
  in d8_sys/d8_mcu to keep the vendored surface small).

### 2.2 Clocks and bus

96 MHz system clock, every other clock a fractional enable:

| Item | Rate | Source |
|---|---|---|
| 6809 bus cycle (E) | 1.5 MHz (64 clocks), Gondomania 3 MHz (32 clocks) | dec8.cpp:1985-1989, 2106, 2420 |
| E falling (`cen_E`) / Q falling (`cen_Q`) | end of cycle / three quarters in | 6809E quadrature clocks; mc6809i samples interrupts at Q falling |
| i8751 oscillator | 8 MHz (`cen` every 12 clocks; machine cycle 1.5 us) | dec8.cpp:1997, 2111, 2426; Gondomania board: "XTAL 8 MHZ X1" [GONDO-TSM p. 3], at the 8751 on sheet 26 |
| pixel | 6 MHz (every 16 clocks) | dec8.cpp:1977-1981 |

A bus cycle starts after E falling with the address the CPU state holds.
Program ROM (SDRAM): requested at ph = 1, the byte held in a latch, read by
the CPU at E falling. RAM and I/O: the main CPU's access at ph = 12 and
the sub CPU's at ph = 20 (Last Mission's two CPUs share work RAM, video RAM
and I/O; MAME runs them one instruction at a time with no contention),
writes as one strobe at the slot, reads latched 3 clocks later. The
mc6809i's dead cycles put 0xFFFF on the bus (a ROM read, harmless).

Program ROM latency limit, measured (Gondomania at 3 MHz, 200 frames
against MAME): 28 clocks from request to data gives identical I/O; 29
clocks makes every fetch late (`o_dbg_prom_late` counts them) and the game
fails at once. At 1.5 MHz the budget is 60 clocks. The other cores' SDRAM
controllers answer in 8 to 10 clocks.

### 2.3 Memory maps, registers, interrupts (all from dec8.cpp)

- Maps: lastmisn main and sub (L301-350), gondo (L451-472), srdarwin and
  srdarwinb (L562-592). Unmapped reads return 0 (MAME's default unmap
  value); `o_dbg_unmapped` counts accesses MAME does not map.
- Work RAM, 8 KB (MAME's oracle dumps it in this layout): lastmisn share1
  0x0000-0x0fff at 0 and share2 0x3000-0x37ff at 0x1000; gondo
  0x0000-0x17ff; srdarwin 0x0000-0x05ff at 0 and 0x1000-0x13ff at 0x1800.
- Bank and control: lastmisn 0x180d (bank, scroll MSBs, sub CPU reset hold
  on bit 7 clear, dec8_v.cpp:93-120); gondo 0x3830 (bank, SECCLR clears
  the main IRQ, NMI enable after one CPU cycle, flip; machine_reset writes
  0, L1948-1953; m_bank_data starts 0xff so the reset write arms the NMI
  timer with 0, dec8.h:250); srdarwin 0x1805/0x1806 (bank, scroll).
- Interrupts: lastmisn IRQ/FIRQ registers 0x1800-0x1804 (either CPU), FIRQ
  to both from the MCU's P2.2 rising (L753-758); gondo NMI = vblank AND
  the delayed enable (input merger, L2131-2135), IRQ from P2.2 rising
  while SECCLR is set (L725-727); srdarwin NMI = vblank (L2441). Vblank =
  MAME's screen vblank, lines 248-271 and 0-7.
- Input ports, DIP defaults and the vblank bits were read from MAME
  (`m2/ports_probe.lua`, build/m2_ports_probe.txt): lastmisn IN2 bit 7 =
  vblank (high in vblank), gondo IN3 bit 3 = vblank active low, srdarwin
  IN1 bit 6 = vblank (high). Gondomania's rotary: one-hot positions,
  `player_io_r` (L116-129).
- MCU glue (L694-790): P0/P1 inputs are the board's latches; the MCU's own
  P0/P1 writes also write them (i8751_port0_w/port1_w); P2 writes act on
  every write (MAME calls the port callback on each write): falling P2.4-7
  move bytes between the main CPU's value/return latches and the port
  latches, P2.2 rising interrupts the main CPU(s), P2.0/P2.1 low clear INT0
  /INT1 (lastmisn; srdarwin P2.1). INT1 = the main CPU's value write
  (lastmisn/srdarwin when P2.1 is high; gondo always, cleared after 4
  ticks of 1.5 MHz, L177-180; the schematic's 74LS194 gives four *12H
  clocks, R8). INT0: lastmisn = coin (rising edge of the
  any-low coin merger, L1886-1891, L2005), gondo = vblank level (L2132),
  srdarwin = none. P3 = COIN. Last Mission's P0 forced input (L741-746)
  via jt8051 patch 2.

### 2.4 Port list (d8_sys, for the M4 board wrapper)

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk`, `rst_n` | in | 1 | 96 MHz system clock, active-low reset (hold at least 256 clocks: the MCU RAM clear) |
| `i_machine`, `i_srdb` | in | 2, 1 | 0 lastmisn, 1 gondo, 2 srdarwin; srdarwinb (no MCU) |
| `i_pause` | in | 1 | holds the CPU and MCU enables and the interrupt timers; video keeps running |
| `i_in0..i_in3`, `i_coin`, `i_dsw0`, `i_dsw1` | in | 8 each | MAME's ports, active low (the vblank bits are set inside) |
| `i_an0`, `i_an1` | in | 4 each | Gondomania rotary position 0-11 per player |
| `o_prom_req`, `o_prom_addr[20:0]`, `i_prom_data[7:0]`, `i_prom_ok` | | | main CPU program ROM byte (SDRAM image address, build_regions.py SDRAM_SLOTS); data within 28 clocks at 3 MHz, 60 at 1.5 MHz |
| `o_srom_req`, `o_srom_addr[20:0]`, `i_srom_data[7:0]`, `i_srom_ok` | | | Last Mission sub CPU program ROM, same timing |
| `i_mcu_we`, `i_mcu_addr[11:0]`, `i_mcu_din[7:0]` | in | | i8751 program ROM load before reset release |
| `o_rom_req`, `o_rom_addr[21:0]`, `i_rom_gnt`, `i_rom_rv`, `i_rom_data[31:0]` | | | graphics ROM port (d8_video, M1) |
| `o_snd_wr`, `o_snd_data[7:0]` | out | | sound latch write (M3) |
| `o_r/g/b[7:0]`, `o_de`, `o_hblank`, `o_vblank`, `o_hs`, `o_vs`, `o_vbl`, `o_ce_pix`, `o_pen[9:0]` | out | | video |
| `o_dbg_overruns`, `o_dbg_maxcyc`, `o_dbg_verr`, `o_dbg_prom_late`, `o_dbg_unmapped`, `o_dbg_xacc` | out | | gate counters (renderer overruns and worst line, snapshot errors, late program fetches, unmapped accesses, MCU MOVX accesses) |

Parameters: `KRN_FLIP` (PLAN 5.4, R7) and `LATCH` (PLAN 5.2) passed to
d8_video.

## 3. Divergences from MAME (root causes)

Every difference falls into one of the classes below; compare.py
classifies work RAM bytes against MAME's stack pointers at each dump and the
ROM's idle loops, video RAM dumps as transient or persistent, and images as
exact, live (mid-scan) or unexplained.

### 3.1 Write timing: same order and values, beam position within an instruction or two

Every logged write has the same address, value and order as MAME's (except
3.5 and 3.9); its beam position differs by a few pixels (one pixel = a
quarter of a 1.5 MHz bus cycle, half of a 3 MHz one). Core minus MAME, in
pixels, over every write before a 3.5 divergence (`compare.py` deltas):

| Machine | Writes | Min | 1st percentile | Median | 99th percentile | Max |
|---|---|---|---|---|---|---|
| Gondomania (go_attract to frame 2696) | 131,353 | -18 | -2 | 0 | 12 | 16 |
| Last Mission main (lm_attract) | 78,984 | -28 | -28 | 4 | 36 | 64 |
| Last Mission sub (lm_attract) | 8,757 | -27 | -27 | 9 | 33 | 33 |
| SRD (sr_play) | 61,848 | -40 | -20 | 8 | 20 | 40 |

The offset is present from the first write of the boot (SRD frame 1: +4
pixels), before any interrupt: mc6809i's reset sequence and the bus slot at
which d8_sys commits a write against MAME's instruction-level timing (reset
release against the video counter is arbitrary on a board). On top of it,
an interrupt recognised one instruction earlier or later (3.3, 3.9) shifts
the following writes by that instruction's length (traced for SRD in 3.9).
Last Mission's largest offsets are MCU round trips: the main CPU writes
0x180e (the MCU's INT1), the MCU answers by raising P2.2 (FIRQ to both
CPUs) and the FIRQ handler acknowledges at 0x1802. 1,236 of the 1,240
lm_attract main writes more than 32 pixels off are those 0x1802 writes;
over the 9,583 pairs of a 0x180e write followed by a 0x1802 write, the
core's round trip is 0 to 40 pixels longer than MAME's (most often 20),
3.3's two machine cycles (18 pixels) plus the 6809 bus cycle and
instruction granularity of each side.

### 3.2 Mid-scan writes (images "live")

As M1: a write to tile RAM, palette, scroll or the sprite buffer during the
visible scan shows from the next line drawn; MAME draws the frame once at
vblank. Kept live by Lee's decision (PLAN 5.2, R5). Every image that differs
from MAME has all its differing lines at or above the frame's last visible
video write + 2.

### 3.3 The MCU answers interrupts later than MAME's i8751 (R14)

Gondomania's MCU takes INT0 at vblank and replies on P2 (which raises the
main CPU's IRQ). Logged with the beam position (`m2/mcu_p2_probe.lua` against
the core's `+mcutrace`, frames 20-22), every P2 write of that reply comes
19 pixels (304 clocks, about two 8051 machine cycles of 288) later in the core than in
MAME. MAME's mcs51 sets IE0 the moment the line changes and enters the
interrupt at the next instruction boundary (i8051.cpp:953-1013, 1141-1149;
its own comment notes it does not model the state-5 latch and the poll in
the following cycle). jt8051 models that latch and poll, the documented
8051 response of at least three machine cycles from the request to the
first instruction of the service routine ("a minimum of three complete
machine cycles elapse between activation of an external interrupt request
and the beginning of execution of the first instruction of the service
routine"; INT0/INT1 latched at S5P2 and "not actually polled by the
circuitry until the next machine cycle" [MCS51, p. 3-25, "Response
Time"]). The board drives INT0 from *VBLK [GONDO-TSM sheet 26, PDF p. 44,
8751 pin 12]. Believed accurate: the core. Consequence: the MCU's IRQ
reaches the main CPU a little later; after the NMI handler's RTI, MAME's
CPU takes the pending IRQ at once while the core first runs one more
instruction of the idle loop (traces of frames 20-34, `m2/trace_cmp.py`).

### 3.4 Idle counters (Gondomania $CA, gondou $D0)

The idle loop `INC <$CA` / `BRA` (0x80BF; gondou 0x80D1 on $D0) counts the
spare 9-cycle passes between interrupts, so 3.3's instruction-level
difference moves it by a count or two per frame. compare.py finds these
counters in the ROM (`0C xx 20 FC`) and classes them separately. Nothing
reads them until the game's first random choice (3.5), in gameplay or in
the attract demo.

### 3.5 Gondomania: the idle counter is the game's random source

Gameplay reads $CA to make random choices (ROM 0x9898, 0x98DF: `LDA <$CA`,
`ANDA #6`, `LEAY A,Y`; 0xB21D: `LDA <$CA`, then `STA <$C9` at 0x9338 and
`LDB <$C9` at 0x93DA). In go_play the two sides' RAM differs only in one
dead stack byte at frame 1744; between 1744 and 1748 $CA ends one count
apart (0x59 / 0x58), the MAME trace of that window (inputs replayed) shows
B21D reading it and $C9 and the new object table (0x078b-0x079f) differ by
exactly that count at frame 1748, and from there the play differs. Measured
(`compare.py go_play --max N`): frames 1 to 1746 pass every check (67,255
logged writes equal, interrupts equal on all 1,746 frames, 262 of 262 images
exact, work RAM differs only in dead stack bytes and the idle counter); the
frame 1748 dump is the first with a persistent difference ($C9, the object
table, two sprite list bytes, one image); the logged I/O stream stays equal
for 77,084 writes and first differs at frame 1862 (the bank register
0x3830, 0x61 in MAME against 0xa1 in the core, at a different beam
position: by then the two games are in different states); interrupt counts
first differ at frame 3729.

The attract demo plays the game with the same random source: go_attract
passes every check up to frame 2696 (131,353 writes, 862 images exact;
from frame 2697 the beam positions step);
the frame 2705 dump is the first with a persistent difference, in the same
bytes ($C9 0x04 in MAME against 0x09 in the core, $CA 0x40 against 0x19,
the object table 0x078b-0x079f, 0x0431/0x0434); the logged I/O first
differs at write 133,167 (frame 2716, the bank register again).

gondou (the US set, good MCU dump) shows the same thing earlier in its
attract demo: every check passes to frame 1469 (work RAM differs only in
dead stack and its idle counter $D0; the frame 1470 dump still matches, and
the beam positions step from frame 1470); MAME's trace of frames
1471-1494 executes `LDA <$D0`, `ANDA #3` once (0xD464, about 22 frames in,
storing to $13,X of an object and $CF), and the logged I/O first differs
at write 28,584 (frame 1493); the frame 1500 dump then differs in $CF, the
object table 0x078b-0x07a0 and the object RAM at 0x0c00. A byte search of the
program ROM for `96 D0` (`LDA <$D0`) finds ten candidate sites (0xB971,
0xBF8E, 0xC462, 0xC7B2, 0xCA45, 0xD2D8, 0xD464, 0xD7F7, 0xD8B3, 0xD995).

makyosen (Japanese, same program family as gondo, idle loop `INC <$CA` at
0x80BE): every check passes to frame 2063; the beam positions step from
frame 2064, and the frame 2070 dump is the first with a persistent
difference ($C9 0x0f in MAME against 0x04 in the
core, with $CA 0x71 against 0x67, and 0x03ac-0x03b0), the logged I/O first
differs at write 94,446 (frame 2283, the bank register).
Root cause: 3.3. Believed accurate: the core, with 3.3.

### 3.6 Stack bytes and transient writes

Work RAM below a CPU's S at a dump (dead stack, up to 64 bytes
below) differs when an interrupt lands at a different instruction (3.3)
and pushes a different return address; live stack bytes likewise. A byte
that differs at one dump and matches at the dumps before and after is a
write landing either side of the vblank instant, mostly in the boot memory
tests (Last Mission's RAM test with S still 0; one palette and one sprite
RAM byte at boot). None persists.

### 3.7 SRD writes 0x1802 once at boot

Frame 1, line 185: a write to 0x1802, which MAME does not map
(dec8.cpp:568-575); both ignore it (`o_dbg_unmapped` = 1 on srdarwin).


### 3.8 SRD's MCU 50 ms clock runs slower in the core (R14)

The srdarwin MCU program keeps a clock in its internal RAM: timer 0 in
16-bit mode, reloaded with 0x7dca by its interrupt routine (0x02cb: `MOV
TH0,#7D`, `MOV TL0,#CA`), 33,334 machine cycles = 50 ms at 8 MHz; 0x39
counts 20 ticks, 0x3a and 0x3b count 60 each, bit 0x26 flags a tick. The
counts lost between the overflow and the reload are the interrupt response
time, so the period is 33,334 machine cycles plus that time ("The Timer 0
and Timer 1 flags, TF0 and TF1, are set at S5P2 of the cycle in which the
timers overflow. The values are then polled by the circuitry in the next
cycle" [MCS51, p. 3-25]), and
3.3 makes the core's period longer. Measured (`m2/mcu_p2_probe.lua` with
`P2_ADDR=0x8c` against `+mcutrace`, the TH0 reload write): the core's tick
is 18 pixels after MAME's at frame 2 and 2,465 pixels (0.41 ms) after it
at frame 680 (35 ppm; over the first five ticks it grows by 0 or 2
machine cycles per tick). At a vblank dump the core's 0x39 is therefore sometimes one count behind (core
= MAME + 1, or 0x01 against MAME's reloaded 0x14), with bit 0x26 and on a
wrap 0x3a/0x3b following; sr_play: 6 of 325 dumps below frame 2000, 17 of
500 to 4000, 30 of 501 to 6000, always the core behind, no other MCU byte.
The I/O stream stays equal over all 6,000 frames. Believed accurate: the
core, with 3.3.

### 3.9 SRD frame 4267: one bank write on the other side of the NMI

sr_attract and sr_flip (the same boot up to there) write 0x1805 = 0xa1 from
the main loop (0xA7CF `ORA <$C0`, 0xA7D1 `STA $1805`) at line 248, pixel
16 in the core, before the vblank NMI handler's own 0x1806/0x1805 writes;
MAME's debugger trace of frames 4266-4268 (`trace_window.lua`) shows its
NMI taken after 0xA7CD `STA <$E1` ("interrupted at A7CF"), so the same
write comes after the handler (line 250). Same writes, same values, the
register ends equal and every later write, image and RAM dump matches;
compare.py reports it as one write moved by 5 places within the frame.
Cause: the vblank NMI lands at an instruction boundary that differs by one
instruction between the two. mc6809i passes NMI through a two-stage
synchroniser (sampled at Q falling, then E falling, latched at the next Q
falling, tested at the next opcode fetch), which its author measured with
a logic analyser on a real 6809 (comment above `NMISample` in mc6809i.v),
and Motorola documents the delay: "NMI, FIRQ, and IRQ requests are sampled
on the falling edge of Q. One cycle is required for synchronization
before these interrupts are recognized" [6809E-DS, PDF p. 9, note to
Figure 8]; MAME's 6809 tests the line at the next instruction boundary.
Combined with the few-pixel phase difference of 3.1, this frame's NMI falls on the other
side of `ORA`/`STA`. Believed accurate: the core (hardware-measured
synchroniser); the phase itself is arbitrary on a board.

## 4. Decisions for Lee

- **4.1 MCU interrupt response (R14).** The core keeps jt8051's documented
  8051 response time (Intel's at least three machine cycles), following
  the accuracy-first rule. Cost: Gondomania gameplay and its attract demo
  play differently from MAME after the first random choice (go_play frame
  1748, go_attract 2705, gondou 1500, makyosen 2070), and SRD's MCU clock drifts 35 ppm from
  MAME's (3.8). The alternative is a one-parameter jt8051 change that
  enters the interrupt at the next instruction boundary as MAME does; it
  would make Gondomania comparable with MAME end to end but models a
  response the 8051 documentation says is too fast. Recommendation: keep
  the documented timing in the core; add the MAME-timing switch only as a
  simulation option if long Gondomania comparisons are wanted later.
- **4.2 Last Mission P0 (R13).** Reproduced as MAME does it (forced input
  bits). The MCS-51 manual confirms the 8751 cannot read P0 with 0x00 in
  its latch, so the board supplies the byte some other way; reading the
  Last Mission schematic (23 MB scan, not fetched) would settle how.
  Recommendation: keep MAME's model until then.
- **4.3 SDRAM budget for M4.** The main CPU program ROM byte must arrive
  within 28 clocks of the request at 3 MHz (60 at 1.5 MHz); the M4 SDRAM
  arbiter must hold this with the graphics port busy.
- **4.4 jt8051 licence.** jt8051 is GPL-3.0-or-later, the same as the other
  vendored jotego cores, so the core stays GPL-3.0.

## 5. Research items

Closed in M2:

- **R4** (Gondomania 6309 native mode): closed on gameplay. go_play traced
  in MAME's debugger with the inputs replayed (`trace_fifo_inputs.lua`),
  6,000 frames, 72,299,671 instructions, 90 distinct mnemonics, every one a
  6809 instruction, no LDMD (build/m2/gondo_play_mnemonics.txt). With the
  attract trace (36.1 M instructions) the 6309 never leaves emulation mode,
  where its timing is the 6809's.
- **R11** (mc6809i licence): BSD-3-Clause (2.1).

Progress:

- **R8**: implemented as MAME models it (NMI enable one 3 MHz CPU cycle
  after the 0x3830 write, MAME's minimum_quantum; INT1 cleared 4 ticks of
  1.5 MHz after the value write); NMI and IRQ counts per frame equal MAME's
  in every gondo run. INT1 on the board [GONDO-TSM sheet 26, PDF p. 44]:
  8751 pin 13 (P3.3/INT1) is QA (pin 15) of the 74LS194 at 3A, whose CLR
  (pin 1) is *SECREQ, CLK (pin 11) *12H, S1 (pin 10) and both serial
  inputs (pins 2, 7) +5, S0 (pin 9) ground: shift towards QA with ones
  fed in, so INT1 stays low for four *12H clocks after *SECREQ. The
  survey report read it first; a second reading of the same sheet at 300
  dpi for this milestone agrees. That supports MAME's 4 ticks over 64; the *12H
  frequency is not on this sheet, and the NMI enable gate is on another
  DE-0269 sheet not yet traced.

New or changed (PLAN section 6):

- **R13** Last Mission's MCU P0 read: MAME forces the latched byte onto P0
  input bits because the program writes 0x00 to P0 first
  (dec8.cpp:741-746). The premise is documented: "P0 lines that are being
  used as output port lines are open drain" and "To be used as an input,
  the port bit latch must contain a 1, which turns off the output driver
  FET" [MCS51, p. 3-7], so with 0x00 in the latch the 8751 itself pulls
  P0 low and the chip has no mechanism for MAME's forced read; the board
  must do it. Reproduced as MAME
  (jt8051 patch 2) until the Last Mission schematic (jammarcade scan, not
  read) shows the wiring.
- **R14** 8051 interrupt response time (3.3): the CPU rule is documented
  [MCS51, p. 3-25, 3-26: at least three machine cycles, "always more than
  3 cycles and less than 9 cycles" in a single-interrupt system]; jt8051
  follows it, MAME's entry at the next instruction boundary is shorter
  than the documented minimum. Open only for the board's INT0 edge timing
  against the CPU clock.
- **R15** SEX and V: jtframe's mc6809i clears V, MAME leaves it. Motorola
  contradicts itself: the 6809E data sheet's instruction table shows V
  "0" (cleared) on the SEX row [6809E-DS, PDF p. 31], the programming
  manual says "V - Not affected." [6809-PM, p. A-62, as quoted by the
  survey report; the scan has no text layer and was not re-read here]. No
  compared stream differs; closing evidence is a hard-part test.
- **R16** Gondomania main CPU part and clock (2.1): the component list
  says 6809E, MAME HD63C09EP at 3 MHz, above Motorola's fastest 6809E
  grade. The DE-0269 schematics [GONDO-TSM, PDF p. 29-48] show the CPU
  clock; not yet traced.

## 6. Sources

Primary documents (downloaded by the arcade survey,
`../mister-arcade-survey/datasheets/SOURCES.md`, with URLs and md5;
GONDO-TSM fetched again for this milestone, md5 matches):

| Tag | Document | Used for |
|---|---|---|
| GONDO-TSM | Data East USA, Gondomania Operation and Service Manual with Technical Support Manual, archive.org `arcademanual_Gondomania`, Gondomania.pdf, md5 cc39ffa8ad1c3543b502063aab32b99e, 71 pages | 2.1 (component list, manual p. 3 / PDF p. 22), 3.3 (INT0 = *VBLK), R8 (sheet 26, PDF p. 44), R16 |
| 6809E-DS | Motorola MC6809E data sheet, bitsavers `components/motorola/_dataSheets/6809E.pdf`, md5 e68fb25c33967bc2c0c6e0fda495f1a1 | 2.1 (speed grades), 3.9 (interrupt synchronisation, PDF p. 9), R15 (PDF p. 31) |
| 6809-PM | Motorola M6809PM/AD Programming Manual rev 0, May 1983, bitsavers, md5 63aaf7e0453d182b83c93d6910b5bae2 | R15 (p. A-62, via the survey report) |
| MCS51 | Intel MCS-51 Microcontroller Family User's Manual, Feb 1994, bitsavers, md5 6b0bbc12627d39a0fe6cf4b4f9fbecfa | 3.3, 3.8, R13 (p. 3-7), R14 (p. 3-25, 3-26) |
| HD6309-TRG | HD63B09EP Technical Reference Guide, Chet Simpson and Alan DeKok, 1994 (community document) | background for 2.1 (emulation mode) |
| Survey report | `../mister-arcade-survey/reports/chip_docs_vs_research_items_2026-10-03.md` | first readings of the above for R8, R13, R14, R15 and the CPU type |

Emulation and HDL references: MAME 0.288 (`reference/mame/v0288/`,
dec8.cpp line numbers as cited), mc6809i and jt8051 (`rtl/vendor/*/
PROVENANCE.md`). Where a document and MAME disagree, the document is
preferred as evidence (Lee, 2026-10-03); where documents disagree (R15) the
item stays open.
