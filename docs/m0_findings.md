# M0 findings (DEC8: Last Mission, Gondomania, SRD)

Date: 2026-10-03. Oracle: MAME 0.288 (local), driver vendored in
`reference/mame/v0288/`. Reproduce: `cd sim && make m0` (about 15 minutes
with JOBS=4 on a loaded machine; output in `sim/mame/out`, gitignored).

## 1. Gate: PASS

| Check | Result |
|---|---|
| ROM sets (CRC32, SHA1, size, against the table generated from dec8.cpp) | 10/10 complete (`make roms-check`); `mame -verifyroms` OK for all 10. Expected notes: BAD_DUMP MCUs in lastmisn, lastmisnj, gondo, srdarwinj; NO_DUMP PALs (makyosen) and priority PROM (srdarwinb) |
| Regions rebuilt by `tools/build_regions.py` vs MAME's own region dumps | 10/10 byte-identical (`make mame-regions`). srdarwinb needs MAME's `init_srdarwinb` byte swap of the sprite ROMs (bytes 1 and 2 of every 4), now applied by the builder (`romdefs.INIT_TRANSFORMS`); its NO_DUMP PROM and makyosen's NO_DUMP PALs are skipped (MAME pattern-fills them) |
| Reference renderer `sim/oracle/d8_render.py` vs MAME snapshots | **12,678 / 12,678 frames pixel-exact**, plus the independent `screen:pixels()` check wherever the palette did not change between notifiers (10,768 frames) |

Captures (all from power-on, wiped cfg/nvram):

| Run | Set | Frames dumped | Content |
|---|---|---|---|
| lm_attract | lastmisn | 2,025 | 12,000-frame attract, every 8th, dense 3000-3599 |
| lm_play | lastmisn | 1,251 | coin, start, play (inputs from `tools/play_inputs.py`) |
| go_attract | gondo | 2,025 | attract, dense 2000-2599 |
| go_play | gondo | 1,326 | play |
| sr_attract | srdarwin | 2,025 | attract, dense 1000-1599 |
| sr_play | srdarwin | 1,326 | play |
| go_flip, sr_flip | gondo, srdarwin | 300 each | Flip Screen DIP on (lastmisn has no flip DIP: cocktail only) |
| clones | lastmisnu6, lastmisnu5, lastmisnj, gondou, makyosen, srdarwinj, srdarwinb | 300 each | every 30th frame to 9,000 |

Palette: 6 boot frames (frame 1 of five runs and gondo frame 9) show
palette entries the game had not yet written; MAME displays its power-on
default pens there (a pattern, not hardware state; real palette RAM powers
up with random contents). The oracle records which entries were written
(`palette_written.bin`), the renderer uses MAME's pen only for those, and
every written entry must decode to MAME's pen exactly (it does, in every
frame).

## 2. Findings that affect the RTL

**Timing.** 384 x 272 at 6 MHz, visible 256 x 240 (lines 8-247), 57.44 Hz
(spec section 3). MAME's notifier runs at line 248, confirmed by the oracle.
Flipping does not move the visible area in MAME 0.288.

**Scroll and flip.** Scroll registers are written at line 248 (vblank) in
almost every frame. Visible-area writes that change the effective scroll
or flip value (bank-only changes of shared registers excluded):

| Run | Frames |
|---|---|
| lastmisn attract / clones | 0 |
| lastmisn play | 1 (x and y) |
| gondo all runs | 0 (flip: 2 frames at boot in go_flip) |
| srdarwin attract / play / flip / clones | 4 / 8 / 2 (+1 flip) / 3-4 |

**Shared registers carry ROM banking.** srdarwin's 0x1805 (bank bits 5-7 +
scroll MSB) and gondo's 0x3830 (bank bits 4-7, NMI enable, SECCLR, flip)
are written many times per frame during the scan to switch ROM banks (gondo
about 60 writes a frame). The RTL must split those registers so banking
writes never disturb scroll or flip.

**Tile and palette RAM written during the scan.** Frames with visible-area
writes (attract runs): lastmisn fix RAM 8,956 / 11,994, bg RAM 842,
palette 51; gondo fix 424, bg 45, palette 14; srdarwin fix 4,866, bg 178,
palette 11. MAME renders each frame once at vblank; the live RTL (decision
5.2) will differ from MAME on the subset of these frames where a write
changes visible pixels above the beam. M1 must classify each such frame as
Tecmo 16's M1 did.

**Sprite buffers.** lastmisn copies at line 248 every frame (0x1805);
gondo strobes 0x3828 bit 2 at line 248; srdarwin copies at line 248 but
also 11 times in the attract run at lines 18 and 52 (value 0xf8), which in
MAME shows the new list for the whole frame (same class as 1945k III's
mid-scan copies). Sprite RAM itself is written mostly during the scan
(srdarwin 93%), which only matters to the RTL's buffer copy (copy-before-
write, as 1945k III).

**Sprite load.**

| Machine | Max sprites drawn in a frame | Max sprites crossing one visible line |
|---|---|---|
| lastmisn (256-entry Karnov list) | 41 | 29 |
| gondo (256-entry Karnov list) | 53 (gondou clone; 48 parent) | 24 |
| srdarwin (128-entry list) | 52 | 25 |

**Interrupts per frame** (vector-fetch taps): lastmisn main FIRQ (MCU P2.2)
about once a frame (9,559 of 11,994 frames; up to 3), sub IRQ from the main
CPU about once a frame, main IRQ from the sub CPU rarely (41 frames), no
NMI. The main CPU talks to the MCU early in the scan (lines 9-32: value
write, FIRQ acknowledge). gondo: NMI and IRQ once a frame. srdarwin: NMI
once a frame (vblank), no MCU interrupt.

**CPU type (gondo).** A 2,930-frame attract trace of the HD6309 (36.1 M
instructions, streamed through a FIFO by `sim/mame/trace/trace_mnemonics.sh`,
counts in `docs/gondo_attract_mnemonics.txt`) contains only 6809 mnemonics and no LDMD: the program stays in
6809 emulation mode, where the 6309's timing is the 6809's. A cycle-exact
6809 core can run it if a gameplay trace agrees (R4).

**Priority.** MAME uses fixed rules (gondo: sprites with colour bit 3 behind
bg pens 8-15; srdarwin: tile groups by colour, colour-0 sprites behind
group-split pens 8-15) and ignores the boards' priority PROMs (R2). The
renderer reproduces MAME's rules exactly; M1 should decode the PROMs and
compare them with these rules before choosing.

**Karnov sprite flip.** Nothing in dec8.cpp sets the sprite chip's flip
flag, so in MAME the gondo/lastmisn sprites are drawn unflipped while the
tilemaps flip; the go_flip frames match MAME with this model (R7).

## 3. Uncertain or open

- BAD_DUMP MCUs on three sets (R1); gondo's second coin fails in MAME
  ("probably due to hacked MCU ROM").
- Real priority PROM behaviour (R2), sprite DMA duration (R3), live vs
  frame-at-once rendering (R5), srdarwin top-edge sprite wrap (R6), Karnov
  flip (R7), gondo NMI-enable latency and MCU INT1 clear time (R8).
- Gondomania's rotary joystick (12 positions per player) needs a MiSTer
  input mapping in M4 (paddle, spinner or two buttons).
- `mc6809i` licence (R11) before vendoring.

## 4. Files

- `docs/dec8_system_spec.md`, `docs/PLAN.md`, this file.
- `reference/mame/v0288/` (oracle sources), `reference/mame/master/`
  (current split driver), `reference/mame/PROVENANCE.md`.
- `tools/romdefs.py`, `check_roms.py`, `build_regions.py`,
  `compare_regions.py`, `play_inputs.py`, `analyze_writes.py`.
- `sim/Makefile`, `sim/mame/d8_oracle.lua`, `run_mame.sh`,
  `run_captures.py`, `dump_regions.lua`, `frame_tools.py`,
  `sim/oracle/d8_render.py`, `sim/oracle/compare_frames.py`.
