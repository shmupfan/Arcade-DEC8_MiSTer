# DEC8 - MiSTer FPGA Core (draft)

Three vertical shooters on Data East's 1986-87 8-bit boards, from one RBF:
Last Mission, Gondomania and SRD: Super Real Darwin, ten MAME sets. Not
yet released: this is the M4 build (the board simulation matches the
system simulation, timing closed at 96 MHz, first RBF built, not yet
tested on a MiSTer). See docs/PLAN.md and the findings documents in
docs/.

| Game | Year | Main CPU | MCU | Sound |
|---|---|---|---|---|
| Last Mission (+ US rev 6, US rev 5, Japan) | 1986 | 2x 6809 at 1.5 MHz | i8751 | R65C02, YM2203, YM3526 |
| Gondomania (+ US, Makyou Senshi) | 1987 | HD6309 at 3 MHz (runs 6809 code only) | i8751 | R65C02, YM2203, YM3526 |
| SRD: Super Real Darwin (+ Japan, Japan bootleg) | 1987 | 6809 at 1.5 MHz | i8751 (none on the bootleg) | DECO 222, YM2203, YM3812 |

The CPUs and sound chips use established cores: mc6809i (Greg Miller),
jt8051, jt65c02, jt03 and jtopl (Jose Tejada, jotego). The video hardware
(tilemaps, both sprite chips, palette) is new work. Details and licences in
docs/PLAN.md section 3 and each vendored core's PROVENANCE.md.

## Install (when released)

Copy `releases/Arcade-DEC8_*.rbf` to `/media/fat/_Arcade/cores/` and the
MRA files in `releases/` to `/media/fat/_Arcade/`. Alternative sets are in
`releases/_alternatives/` and go to `/media/fat/_Arcade/_alternatives/`.

You need the MAME ROM sets (0.288 naming) in `/media/fat/games/mame/`:
`lastmisn.zip`, `gondo.zip`, `srdarwin.zip`. Clone sets load from their
parent zip. No ROM data is included in this repository.

Which set to play: the World parents of Last Mission and Gondomania, and the
Japanese SRD, carry MCU programs that MAME marks as bad dumps (Gondomania's
is hand-made from the US one). The US sets of Last Mission (revisions 5 and
6) and Gondomania, Makyou Senshi and the World SRD have verified MCU dumps
and are the accuracy references. The bad-dump sets are offered because they
are the parent sets in MAME.

## Controls

| | Player 1 keys | Player 2 keys | Gamepad (J1) |
|---|---|---|---|
| Move | arrows | R F D G | d-pad |
| Button 1 | Left Ctrl | A | Button 1 |
| Button 2 | Left Alt | S | Button 2 |
| Button 3 (Last Mission) | Space | Q | Button 3 |
| Turn left / right (Gondomania) | Z / X | N / M | Turn Left / Turn Right |
| Start | 1 | 2 | Start |
| Coin | 5 | 6 | Coin |
| Service | 9 | | Service |
| Pause | P | | Pause |

The buttons are named per game in the MAME driver's terms: Last Mission
Shoot, Bomb, Select; Gondomania and SRD Button 1, Button 2.

Gondomania's 12-position rotary joystick works three ways at once, with no
setting to change: the Turn Left / Turn Right buttons or keys (one step per
press, repeating every 100 ms after 250 ms held), a spinner (OSD Spinner
speed: Normal, Fast, Slow), or a paddle (absolute position). Turn Right is
MAME's increment key (X), which lowers the position the game reads, as
MAME's reversed port does.

## OSD options

- DIP switches per set, every switch the MAME driver names, with MAME's
  defaults (see Accuracy notes for the operator manuals).
- Aspect ratio, Orientation (Vertical, Horizontal), Rotate (CCW, the MAME
  direction, or CW for monitors mounted for the other rotation),
  scandoubler effects, HDMI Scale (Normal, V-Integer, Narrower or Wider
  HV-Integer).
- Pause when the OSD is open (on by default).
- Volume: Normal, +6 dB, -6 dB, -12 dB.

Rotate only turns the HDMI picture (the frame buffer). On a CRT the picture
is not rotated: if your monitor is mounted for ROT90 games, set the Flip
Screen DIP switch to On for Gondomania or SRD, as on the original cabinet.
Last Mission has no Flip Screen switch.

The picture is 256 x 240, so the 216-line crop the other shmupfan cores
offer for 224-line games does not apply here.

## Accuracy notes

MAME 0.288 is the reference. Every part of the core was checked against it
in simulation: the video against 12,678 MAME frames (pixel-exact), the full
systems from power-on against MAME's I/O streams, RAM and images, and the
sound board against MAME's register streams and audio. Where MAME and the
hardware are likely to differ, the core follows the most plausible hardware
behaviour and the difference is logged as a research item in docs/PLAN.md.
The main ones:

- **i8751 interrupt timing** follows Intel's documented response (at least
  three machine cycles), where MAME enters the handler at the next
  instruction. Gondomania's random numbers in gameplay and SRD's MCU timing
  differ from MAME because of it (docs/m2_findings.md).
- **Sound CPU timing** follows the R65C02 data sheet for the instructions
  the sound programs use (docs/m3_findings.md 7.1); FM and OPL are mixed
  1:1 as both board schematics show.
- **Mid-screen writes** (palette, tiles, scroll) are drawn as the beam
  meets them; MAME draws each frame at once.
- **Gondomania's main CPU** runs at 3 MHz as in MAME. The board's schematic
  has a jumper for 3 MHz operation; which setting production boards used is
  open (R16).
- **DIP switches**: the Last Mission and Gondomania operator manuals
  (Data East USA) list the same switches as MAME, except three that MAME
  found in the program code and the manuals call unused: Last Mission's
  Invulnerability and Infinite Lives (SW1:7, SW1:8) and Gondomania's Swap
  Buttons (SW1:8). The core offers them as MAME does. The Last Mission
  manual gives the second bonus life setting as 40K/70K and every 90K; the
  program's tables in the World, US revision 6 and US revision 5 sets all
  give 40k, 90k and every 90k, as MAME lists it. No SRD manual was
  available.

## Building and verifying

- Simulation: Verilator 5.x and Python 3; the MAME reference captures need
  MAME 0.288 and the ROM sets. `sim/Makefile` lists the M0 to M3 targets,
  `sim/m4.mk` the board-level ones (MRA generation and check, the board
  run against the M2 reference, lint).
- Synthesis: Quartus 17 project at the repository root.

## License and credits

GPL-3.0-or-later for the combined work. Vendored components keep their own
licences and headers. The core relies on MAME's DEC8 driver (copyright
holders Bryan McPhail and Stephane Humbert).

Development used Anthropic's Claude as a coding tool.
