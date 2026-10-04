# M4 findings: MiSTer shell, SDRAM, MRAs, board simulation, Quartus

Date: 2026-10-04. Templates: the 1945k III core's M4 (shell, black screen
with sync during download/reset, MRA generator, SDRAM controller with
registered requests, board simulation, compile scripts) and the Tecmo 16
core's Rotate option and CRT note.

## 1. Names

| Item | Value |
|---|---|
| Repository (proposed) | Arcade-DEC8_MiSTer |
| Quartus project / revision | Arcade-DEC8 |
| Released core | releases/Arcade-DEC8_YYYYMMDD.rbf |
| MRA `<rbf>` | dec8 |
| OSD title | DEC8 |

## 2. ROM stream and SDRAM layout

One stream on ioctl index 0, the same layout for every set
(`rtl/d8_board.sv`, `tools/make_mra.py`):

| Stream bytes | Content | SDRAM |
|---|---|---|
| 0x000000-0x087FFF | sim/build/regions/<set>/sdram.bin bytes 0-0x87FFF: maincpu 0x000000, mainbank 0x010000, sub 0x050000, audiocpu 0x060000, mcu 0x080000, proms 0x081000 (tools/build_regions.py SDRAM_SLOTS) | bank 0 |
| 0x088000-0x0FFFFF | zero fill | bank 0 |
| 0x100000-0x207FFF | the graphics port image (tools/gfx_layout.py: bg 0x000000, sprites 0x080000, fix 0x100000 of the block) | bank 1 |

2,129,920 bytes per set. On the way past, d8_board copies the MCU program
(0x080000-0x080FFF) into d8_sys's MCU ROM and the sound program
(0x068000-0x06FFFF, the 6502's 8000-FFFF) into the sound board's ROM, the
same bytes the M2/M3 harness loads before reset. Both 6809 program ROMs
(main with its banks, Last Mission's sub) and the graphics are read from
SDRAM.

srdarwinb: MAME's init_srdarwinb swaps bytes 1 and 2 of every 4-byte group
of the sprite region after loading (dec8.cpp L4097-4110). Every lane of an
SRD sprite word comes from the same region offset (word i = {s[i],
s[0x20000+i], s[0x10000+i], 0}), so the swap is a swap of the word address
bits 0 and 1. The MRA streams the bootleg's ROMs as dumped and d8_board
swaps byte-address bits 2 and 3 for sprite-block reads when the machine
byte's bootleg bit is set. This replaces the plan's "swap done by the MRA
interleave", which would have needed 16-byte interleave units.

Machine byte (index 1): bits 1:0 = 0 Last Mission, 1 Gondomania, 2 SRD;
bit 2 = srdarwinb (no MCU). DIP switches (index 254): byte 0 = DSW0 (SW1),
byte 1 = DSW1 (SW2).

## 3. SDRAM controller (rtl/d8_sdram.sv)

From the 1945k III controller (close page, CL2, tRCD/tRP 3, P_RET 3,
registered request addresses and arbitration, pending job slot, refresh in
the window after a CPU landing). Changes:

- CPU engine: the main 6809's program bytes on bank 0 (16-bit words, even
  byte = [15:8]); the served word is kept, so the other byte of it is a
  hit.
- Other engine: download, Last Mission's sub 6809 (byte reads on bank 0,
  its want decision and address registered), graphics (two words of one
  row per request, bank 1), refresh. The two OKI clients of 1945k III are
  gone.
- Both engines can use bank 0, so a bank is marked busy from its ACT
  (bank_t = 15) until its precharge completes; an ACT waits for it.
- A download invalidates the kept CPU and sub words (a second MRA loaded
  without reconfiguring the FPGA).

Latency budget (d8_sys latches the byte until falling E; m2_findings 2.2):
28 clocks at 3 MHz (Gondomania), 60 at 1.5 MHz. Measured in the board
runs (section 6): main CPU at most 10 clocks, Last Mission's sub CPU at
most 32, no late program byte (o_dbg_prom_late 0), no forced refresh.

## 4. Shell (Arcade-DEC8.sv)

- Inputs in MAME's port layout per machine (dec8.cpp L824-904, L1028-1116,
  L1552-1622), the vblank bits merged in d8_sys. Gondomania's IN0/IN1
  upper nibbles read 0 as in MAME (the M2 harness's power-on values).
- Keyboard: MAME defaults (P1 arrows, LCtrl, LAlt, Space; P2 R/F/D/G, A, S,
  Q; 1/2 start, 5/6 coin, 9 service, P pause), plus MAME's rotary keys Z/X
  (P1) and N/M (P2).
- J1: Button 1, Button 2, Button 3, Turn Left, Turn Right, Start, Coin,
  Service, Pause. The MRAs name them per game (Last Mission Shoot, Bomb,
  Select).
- Gondomania rotary (decision 5.5): rtl/d8_rotary.sv, buttons, spinner and
  paddle all active at once. MAME's AN ports are PORT_REVERSE with Z as
  decrement and X as increment, so Turn Right (X) lowers the position the
  game reads. Buttons step on press and repeat every 100 ms after 250 ms;
  the spinner steps once per 4, 8 or 16 counts (OSD Spinner speed, shown
  only for Gondomania); the paddle sets the position (11 - paddle x 12 /
  256) when it moves. Unit test: `make -f m4.mk m4-rotary` (15 checks,
  PASS). Not tried with real controllers; the on-screen direction is
  MAME's key convention.
- Video: 256 x 240 at 6 MHz, ROT270 for every set. Orientation, Rotate
  (CCW = MAME, CW for monitors mounted for ROT90 games; HDMI only), aspect,
  Scale through video_freak. No 216-line crop (240 lines). On a CRT the
  picture is not rotated; Gondomania and SRD have a Flip Screen DIP, Last
  Mission has none (README).
- Pause: OSD open (option, default on), the P key or the J1 Pause button;
  d8_sys holds the CPUs, MCU and sound, video keeps scanning.
- Black picture with running sync during download and reset (d8_sys
  FREE_TIMING=1, as 1945k III): the raster runs from the PLL lock; the core
  is released on the raster's power-on phase (line 248, pixel 0), so its
  first clock sees the state a reset release gives in M2. Every board run
  shows 7 vsyncs and 430,080 active pixels during the download, all black.
- Audio: d8_snd's mix times 38/16 (Last Mission), 40/16 (Gondomania),
  27/16 (SRD), then the OSD volume (Normal, +6, -6, -12 dB), saturated.
  From the M3 runs (mix channel, 1 s RMS median / peak sample): Last
  Mission play -28.2 dBFS, peak 13,462; Gondomania play -27.2, peak 12,176;
  SRD play -23.3, peak 18,934. With the gains the loudest measured sample
  is -0.2 to -0.6 dBFS (no clipping on any M3 run) and the gameplay medians
  are -20.7, -19.2 and -18.8 dBFS, against Final Star Force's -16.4 on the
  Tecmo 16 core: the peaks, not the medians, set the gain.

## 5. MRAs and DIP switches (tools/make_mra.py)

10 MRAs: parents in releases/, clones in releases/_alternatives/_<Game>/.
Each MRA is replayed with Main_MiSTer's mra_loader rules from the zips and
compared with the expected stream (sdram.bin bytes 0-0x87FFF, zero fill,
gfx.bin; srdarwinb through the board's address swap): 10/10 byte-exact,
26 parts (Last Mission), 39 (Gondomania), 37-40 (SRD). The verified stream
is written to sim/build/regions/<set>/stream.bin, which the board
simulation downloads.

The interleave encoder of 1945k III is extended so that one file can give
several lanes of a unit at different offsets (SRD's tiles and the fix
layer interleave planes from the same ROM).

DIP switches are parsed from INPUT_PORTS (PORT_INCLUDE and PORT_MODIFY
followed, so lastmisnj and srdarwinj get their own Bonus Life, Difficulty
and coin tables). Defaults equal the M2 harness's power-on values
(lastmisn CF/7F, lastmisnj CF/FF, gondo FF/EF, srdarwin 7F/FF).

Operator manuals (mister-arcade-survey/datasheets/boards; scans, read as
images):
- Gondomania operation and service manual (Data East USA, 1987), page 4
  (PDF p. 8), Tables 1 and 2: every switch MAME names, same settings and
  factory defaults. SW1:5, SW1:8 and SW2:6-8 "not used". MAME's SW1:8
  "Swap buttons" is found in the program (code at 0x8a2b) and is kept. The
  manual calls SW1:1-2 "Player 2 coin" and SW1:3-4 "Player 1 coin" (MAME:
  Coin A, Coin B); the MRA keeps MAME's names.
- Last Mission operation and service manual (Data East USA), page 5 (PDF
  p. 9): the same switches as MAME except SW1:7 and SW1:8 ("switches 7 and
  8 are not used"), which MAME found in the program as Invulnerability and
  Infinite Lives (kept, they are MAME's). The manual's second bonus life
  setting is "40K/70K & every 90K"; the program's tables in lastmisn,
  lastmisnu6 (0x82c1 and 0xde38) and lastmisnu5 (0x82c1 and 0xde17) give
  30/40/40/50k first and 70/90/80k second, so the setting is 40k, 90k,
  every 90k, as MAME lists it. The manual's labels are taken as a misprint.
- No SRD manual is in the library.

## 6. Board gate

`make -f m4.mk m4-ref m4-boot m4-compare`. Seven runs, each on both
harnesses: the M2 harness rebuilt from the M4 RTL (d8_sys FREE_TIMING=0,
C++ ROM models) and the board harness (machine byte, the MRA's stream and
the DIP bytes through d8_board's ioctl port, d8_sdram, the cycle-checked
SDRAM model; both 6809 program ROMs and all graphics from SDRAM). Inputs
from the MAME oracle; captures at frames 1-60 and every 20th frame.

| Run | Frames | Capture files | io / ints / sound log |
|---|---|---|---|
| lm_attract | 1200 | 1401 of 1402 identical | identical |
| lm_play | 1500 | 1581 of 1582 identical | identical |
| go_attract | 1200 | 1402 identical | identical |
| go_play | 1200 | 1402 identical | identical |
| sr_attract | 1200 | 1402 identical | identical |
| sr_play | 1200 | 1402 identical | identical |
| clone_srdarwinb | 900 | 1222 identical | identical |

io.txt carries the beam position of every logged CPU write, ints.txt the
interrupt vector reads per frame, sndlog.csv every sound latch, chip and
vector access with its time: all identical, so the CPUs, MCU and sound
board run clock for clock as in M2. Work RAM, MCU RAM, sound RAM, palette,
tile and sprite RAM are identical at every capture. srdarwinb's sprites
come out right through the board's address swap.

The one difference, the same in both Last Mission runs: displayed frame
180, 32 pixels (one 8-pixel fix-layer row on screen lines 74, 81, 102 and
109). The program is clearing the fix layer while the beam passes (writes
to 0x2266, 0x22a6, 0x22e6... at raster lines 69, 78, 88, 97, 106, each the
first lines of the character row being written), and d8_video reads the
fix tile codes ahead of the beam on a schedule set by its graphics fetches,
which wait on the ROM. With the M2 model (fixed 9-clock latency) the
renderer read the old character, with the SDRAM the new one. Every
graphics word the SDRAM returned in that frame was checked against
gfx.bin (15,834 words, all correct). This is the live rendering of
decision 5.2 meeting a latency-dependent read time; it is research item
R22. Gate counters on the board: 0 renderer overruns, worst line 987 of
6,144 clocks, 0 video errors, 0 late program reads.

Audio: o_audio is checked every clock against d8_sys's mix times the
machine's gain, saturated: 0 mismatches, 0 saturated clocks, loudest
sample 31,951 (SRD attract). (The first gate pass counted 6,848
mismatches on the non-Last-Mission runs: the harness switched its
expected gain after the download, the board when the machine byte
arrives; harness fixed.)

### 6.1 Reset-length independence (d8_snd)

The first canary differed from M2 only in sound timing: the sound board's
dividers and chip enables run through reset (m3_findings 3), so the state
at release depended on how long reset lasted (37,464 clocks in the M2
harness, the whole ROM download on the board). Now the dividers and enables
run for the first 37,464 clocks of a reset and then stop until the release:
the board leaves reset in exactly the state of the M2/M3 harness. Check:
the new reference runs equal the M3 runs (sim/build/m3) at every
common capture (142-178 files per run, frames 100-1200) and in the sound
log, byte for byte, for all six M3 runs.

### 6.2 Other RTL changes in M4 (behaviour-neutral, same check)

- d8_video: o_mvbl, MAME's vblank (lines 248-271, 0-7) as a register
  updated with the line counter, replacing a comparator on the counter in
  d8_sys (a critical path into the MCU's INT0).
- d8_snd: the mix's three products registered (the audio is one clock
  later; not in the compared files).
- d8_sys / d8_video: FREE_TIMING parameter (default 0 = M1-M3 behaviour).

## 7. Timing closure

Three compiles. Compile 1 (no multicycles): 96 MHz setup slack -15.0 ns,
TNS -10,308 (jt8051 25 ns paths, mc6809i 20 ns, jt65c02, sound mix,
d8_sdram sub path, line counter into the MCU). Compile 2 (multicycles of
Arcade-DEC8.sdc, registered vblank, sub request registered, the SDRAM
word mapping without adders): -1.87 ns, only the sound mix into the
board. Compile 3 (mix products registered): every clock meets timing.

| Clock | Setup slack |
|---|---|
| 96 MHz system | +0.782 ns |
| 48 MHz video | +3.359 ns |
| HDMI | +0.277 ns |

No negative setup, hold, recovery or removal slack in the summary
(builds/20261004_0300_Arcade-DEC8.sta.summary). RBF:
builds/20261004_0300_Arcade-DEC8.rbf, md5 70ef132767ae6777700205213261b2e2.

Multicycles (Arcade-DEC8.sdc) and the endpoints that rely on them (TimeQuest
listing of paths over 10 ns from each core, compile 3):
- mc6809i, 2 clocks to the rest of the board, 4 inside: endpoints are the
  bus-cycle registers loaded at the access slots (bank, IRQ/FIRQ flags,
  MCU and sound latches, video and work RAMs, scroll and flip registers,
  the sprite snapshot engine's hold registers), the read pipeline and
  o_prom_req / o_srom_req (loaded at phase 1, 2 clocks after cen_E). All
  are loaded only at a slot or phase that is at least 2 clocks after cen_E.
- jt8051, 4 clocks: endpoints are jt8051's own registers (all enabled by
  cen; uaddr and irq state included), its RAM, and d8_sys's port glue
  (mcu_return, p0/p1 latches, int0/int1, FIRQ/IRQ) loaded on an SFR write,
  which includes cen. Longest path 29.8 ns of 41.6.
- jt65c02, 4 clocks: its registers (uaddr and jsr_ret enabled by
  cen && !halt), the sound RAM/ROM address registers (read at the next
  enable), the latch-pending flag (cleared on cpu_cen), opl_sel and the
  YM2203 / OPL register files (written by the write event). Longest 18.3 ns.
- jt03 and jtopl, 2 clocks inside each chip: endpoints in the phase
  generators, operators and accumulators, all enabled by the chip's enable.

## 8. Compile PC

`tools/pc_build.sh` (PC_HOST required, no default): push to C:\d8_build,
scheduled task d8compile (C:\d8_build\runcompile.cmd, quartus_sh --flow
compile on the E-cores, affinity FFFF0000), status, fetch. One compile at
a time (tasklist checked for quartus before each run). Timing reports were
taken with a second task, d8sta (quartus_sta -t), never as an ssh child.

## 9. Open items

- R22: d8_video's tilemap reads follow its graphics fetches, so a write
  racing the beam can land on either side of the read depending on the
  ROM latency (section 6). Fix if wanted: read the tile codes at fixed
  slots per line.

- Hardware test on a MiSTer (M5): rotary direction and feel, Rotate and
  Scale, the black screen during download, volume.
- High-score saving: hiscore.dat entries for the three games not checked.
- R21 (jt65c02 page-crossing cycles) left documented: fixing it needs the
  full M2/M3 regression.
