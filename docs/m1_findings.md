# M1 findings (DEC8 video RTL)

Date: 2026-10-03. RTL: `rtl/d8_video.sv` (+ `d8_snapram.sv`, `d8_dpram.sv`,
`d8_fifo.sv`, copied from the Tecmo 16 core with PROVENANCE in their
headers). Reproduce: `cd sim && make m1` (needs `make regions` and the M0
captures; `make m1-vislog` for the mid-scan input).

## 1. Gate: PASS

| Check | Result |
|---|---|
| RTL (LIVE, default) vs MAME snapshots, every M0 capture frame, all 10 sets | **12,678 / 12,678 exact** (palette index also equal to `d8_render.py` on every pixel) |
| RTL LATCH build, same frames | 12,678 / 12,678 exact |
| Synthetic scenes vs `d8_render.py` (random, overlap, priority, wrap, region ends, scroll extremes, line load; each machine, flip off and on) | 156 / 156 exact |
| KRN_FLIP = 1 build vs the model with the sprite chip's flip on (R7 switch) | 104 / 104 exact |
| Line overruns, snapshot engine errors | 0, 0 in every run |
| Graphics ROM layout (`tools/gfx_layout.py --check`): every element of every layout decodes to MAME's | 10 / 10 sets |
| VISLOG reruns: per-frame trace identical to the M0 capture | 15 / 15 runs |
| Mid-scan classification (section 3) | 10,558 frames with visible-scan writes: 10,446 exact, 112 explained, 0 unexplained |

The 6 boot frames that show palette entries the game had not yet written
(m0_findings 1) are checked on their palette index; the RGB of those pixels
is MAME's power-on pen pattern, not hardware state.

## 2. Design

- Raster: 384 x 272 at 6 MHz (96 MHz / 16), visible 256 x 240 at lines
  8-247, vblank from line 248, MAME's power-on phase (first line 248).
  Sync positions are not in the driver (inside the blanking, not checked).
- CPU side: byte-wide RAMs as the 6809 sees them; palette {ext, RAM}
  1,024 entries; fix, bg and sprite RAM 2 KB each. The sprite buffer is a
  snapshot copy with copy-before-write (snapram MODE 1, about 4,100 clocks
  at 96 MHz); MAME copies instantly (R3).
- Registers: MAME's four scroll bytes and flip. The system (M2) maps each
  machine's writes onto them: lastmisn 0x180d bits 5/6 to bytes 0/2 and
  0x1809/0x180b to 1/3; gondo 0x3818/0x3820/0x3828; srdarwin 0x1805 low
  bits and 0x1806. Bank bits never reach the video, so the many bank
  writes per frame (gondo 0x3830, srdarwin 0x1805 high bits, M0) cannot
  disturb scroll or flip.
- Line renderer: during line L-1 the bg pass (17 tiles x 2 words), the fix
  pass (32 words) and the sprite pass (2 words per sprite crossing the
  line) build line L into three double line buffers; scan-out mixes them
  and looks up the palette (DECO RM-C3 weights 0x0e, 0x1f, 0x43, 0x8f).
- Sprite order: in both sprite models the visible pixel is the
  highest-numbered entry's (Karnov without priority callback: later over
  earlier; Karnov with callback and srdarwin: drawn last-to-first, first
  opaque pixel wins), so one walk from entry 0 up with "last opaque write
  wins" in the line buffer reproduces both, behind flag included.
- Priority: lastmisn bg, sprites, fix; gondo sprites with colour bit 3
  behind bg pens 8-15; srdarwin colour-0 sprites behind bg group 3 and
  groups 1-2 pens 8-15 (MAME's fixed rules; the priority PROMs, R2, are
  not decoded yet).
- Parameters: LATCH (0 default, PLAN 5.2), LATCH_LINE (6), KRN_FLIP (0
  default = MAME, PLAN 5.4).
- Graphics ROM: one 32-bit word = the plane bytes of 8 pixels side by side
  (`tools/gfx_layout.py`); an MRA can build it with byte interleaves in M4.
  SRD tiles store pixels 0-7 before 8-15, the opposite of the other two
  layouts (found by the decode check).

## 3. Mid-scan writes (LIVE vs MAME)

`sim/m1/midscan.py` replays every captured frame whose visible scan
(lines 8-247) has palette, fix, bg, scroll or flip writes or a sprite
buffer copy: the initial state is the dump with the frame's writes undone
(VISLOG records each value before the write, and the sprite RAM and buffer
at each visible copy), and the RTL gets every write at its beam position.

| Run | Frames with visible writes | Value-changing | Sprite copy | LIVE exact | LIVE explained | LATCH differs from MAME |
|---|---|---|---|---|---|---|
| lm_attract | 1,484 | 193 | 0 | 1,425 | 59 | 144 |
| lm_play | 1,009 | 141 | 0 | 993 | 16 | 140 |
| go_attract | 2,023 | 4 | 0 | 2,023 | 0 | 0 |
| go_play | 1,326 | 7 | 0 | 1,325 | 1 | 3 |
| sr_attract | 1,671 | 324 | 2 | 1,669 | 2 | 295 |
| sr_play | 866 | 13 | 1 | 863 | 3 | 9 |
| go_flip | 299 | 299 | 0 | 299 | 0 | 0 |
| sr_flip | 228 | 227 | 0 | 228 | 0 | 2 |
| lastmisnu6 / u5 / j | 224 / 224 / 215 | 41 / 41 / 38 | 0 | 215 / 215 / 203 | 9 / 9 / 12 | 31 / 31 / 29 |
| gondou / makyosen | 300 / 300 | 59 / 8 | 0 | 300 / 300 | 0 | 6 / 6 |
| srdarwinj / srdarwinb | 190 / 199 | 20 / 34 | 0 | 190 / 198 | 0 / 1 | 17 / 27 |
| **total** | **10,558** | | | **10,446** | **112** | |

"Explained" = LIVE differs from MAME only on lines up to the last
value-changing write + 1 (+ 2 after a sprite copy) and equals the state at
the start of the scan above the first one: the picture switches from the
old state to MAME's between the first and the last write, line by line.
The 112 frames are fix RAM writes (96, the text layer: score, messages),
bg RAM writes (72, often together with fix), palette (10) and one scroll
write; median 23 differing pixels per frame, at most 60,374 (a whole-screen
fade at a scene change). Most visible-scan writes (go_flip all 299, the
gondo runs almost all) land below the beam or rewrite the same value, so
LIVE is exact there.

Which side is believed accurate: the core. MAME renders each frame once
at vblank from the final state, a simplification; a line-based CRTC reads
VRAM as the beam passes, so a write lands from the next line drawn.
Unconfirmed against a PCB (R5, decision 5.2). LATCH (one snapshot at line
6) would differ from MAME on 740 frames, more than LIVE, because it moves
every write of a frame to the next one.

Visible sprite buffer copies (srdarwin, 3 frames with a changed list, the
copy at lines 18 and 52 found in M0): LIVE shows the new list from the line
after the copy. MAME shows it on the whole frame. Same class as the 1945k
III core's mid-scan copies (R3: copy timing on the PCB).

## 4. Line budget

| Load | Worst line (render clocks of 6,144 at 96 MHz) |
|---|---|
| Any game frame (all 12,678) | 1,169 (lm_attract) |
| Synthetic scenes (64 sprites on a line) | 1,677 |
| 128 / 256 Karnov sprites on one line | 2,588 / 4,636 |
| 128 srdarwin sprites (the whole list) on one line | 2,588 |

ROM model: one 32-bit read accepted per 8 clocks, data 9 clocks later (the
Dooyong M1 pessimistic port). The whole sprite list fits on one line on
every machine, so the core never drops a sprite on its own; the PCB's
sprites-per-line limit (if any) is unknown and not modelled (new R12).
Games peak at 29 sprites crossing a line (m0_findings 2).

## 5. Lessons applied from the other cores

- Timing: the sprite walker registers the computed positions in one state
  and does the hit test on the registered values in the next (the Tecmo 16
  compile-1 failure was the list RAM to hit-test chain in one clock), and
  the ROM request address is muxed only between registered sources. Not
  yet compiled (M4).
- Copy-before-write sprite buffer from the start (1945k III M2 bug).

## 6. Decisions for Lee

None new. Recorded (PLAN 5.3-5.5): good-dump MCU clones as accuracy
references; Karnov sprite flip = MAME by default behind KRN_FLIP (a
research task is looking for PCB 1CC footage, R7); Gondomania rotary as
spinner/paddle and buttons (M4).

## 7. New or updated research items

- R12: does the PCB limit sprites per line? The core draws all 256
  (Karnov) or 128 (srdarwin) on one line.
- R5 (live rendering) now has numbers: 112 frames in the M0 captures
  differ from MAME because of it.
- R2 (priority PROMs): still to decode before M5.

## 8. Files

`rtl/d8_video.sv`, `rtl/d8_snapram.sv`, `rtl/d8_dpram.sv`, `rtl/d8_fifo.sv`;
`tools/gfx_layout.py`; `sim/m1/tb_video.cpp`, `replay.py`, `make_scenes.py`,
`midscan.py`, `capacity.py`; `sim/mame/d8_oracle.lua` (VISLOG and NO_DUMP
modes), `sim/mame/vislog_runs.py`; `sim/oracle/d8_render.py` (pens output
for the replay); `sim/Makefile` (m1 targets); `docs/PLAN.md` (decisions
5.3-5.5).
