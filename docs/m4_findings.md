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
runs (section 6): RESULTS.

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
  first clock sees the state a reset release gives in M2. Board runs print
  the pre-run video: RESULTS.
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

RESULTS

## 7. Timing closure

RESULTS

## 8. Compile PC

`tools/pc_build.sh` (PC_HOST required, no default): push to C:\d8_build,
scheduled task d8compile (C:\d8_build\runcompile.cmd, quartus_sh --flow
compile on the E-cores, affinity FFFF0000), status, fetch. One compile at
a time (tasklist checked for quartus before each run). Timing reports were
taken with a second task, d8sta (quartus_sta -t), never as an ssh child.

## 9. Open items

- Hardware test on a MiSTer (M5): rotary direction and feel, Rotate and
  Scale, the black screen during download, volume.
- High-score saving: hiscore.dat entries for the three games not checked.
- R21 (jt65c02 page-crossing cycles) left documented: fixing it needs the
  full M2/M3 regression.
