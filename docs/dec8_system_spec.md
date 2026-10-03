# DEC8 system specification (Last Mission, Gondomania, SRD: Super Real Darwin)

Source of truth: MAME 0.288 `dataeast/dec8.cpp`, `dec8_v.cpp`, `dec8.h`,
`deckarn.cpp`, `decrmc3.cpp`, `deco222.cpp`, vendored in
`reference/mame/v0288/` (the local oracle is MAME 0.288). MAME master has
since split the driver into `ghostb.cpp` (Gondomania), `lastmisn.cpp` and
`srdarwin.cpp` (`reference/mame/master/`, commit e5a5a102, 2026-10-03);
section 12 lists what changed. Line numbers are 0.288's unless marked
"master". Every fact below is MAME's model; where MAME says it is unsure,
the item is listed in section 13 and in `docs/PLAN.md` as a research item.

## 1. Sets

| Set | Parent | Machine | Title | MCU dump |
|---|---|---|---|---|
| lastmisn | | lastmisn | Last Mission (World revision 8) | BAD_DUMP (L2550, "not verified to be the same data as the A MCU dump") |
| lastmisnu6 | lastmisn | lastmisn | Last Mission (US revision 6) | good |
| lastmisnu5 | lastmisn | lastmisn | Last Mission (US revision 5) | good |
| lastmisnj | lastmisn | lastmisn | Last Mission (Japan) | BAD_DUMP |
| gondo | | gondo | Gondomania (World) | BAD_DUMP (L2784, "hand-crafted from the US version") |
| gondou | gondo | gondo | Gondomania (US) | good |
| makyosen | gondo | gondo | Makyou Senshi (Japan) | good (PALs NO_DUMP) |
| srdarwin | | srdarwin | SRD: Super Real Darwin (World) | good |
| srdarwinj | srdarwin | srdarwin | SRD: Super Real Darwin (Japan) | BAD_DUMP |
| srdarwinb | srdarwin | srdarwinb | SRD (Japan, bootleg) | no MCU (bootleg) |

GAME lines L4115-4141. All ROT270. Region sizes are checked by
`tools/build_regions.py`; the full ROM table (names, offsets, CRC32, SHA1,
lines) is generated with `tools/check_roms.py --table`.

## 2. Clocks and CPUs

| Machine | Main | Second | Sound | MCU | Source |
|---|---|---|---|---|---|
| lastmisn | MC6809E 1.5 MHz (12 MHz / 8) | MC6809E 1.5 MHz (sub) | R65C02 1.5 MHz | i8751 8 MHz | L1983-1997 |
| gondo | HD6309E 3 MHz ("HD63C09EP") | | R65C02 1.5 MHz | i8751 8 MHz | L2103-2111 |
| srdarwin | MC6809E 1.5 MHz ("MC68A09EP or HD63?09EP") | | DECO 222 1.5 MHz | i8751 8 MHz ("unknown frequency") | L2417-2426 |
| srdarwinb | as srdarwin | | as srdarwin | none | L2467-2474 |

DECO 222 = a 6502 whose opcode fetches have bits 5 and 6 swapped
(`deco222.cpp`, `bitswap<8>(v,7,5,6,4,3,2,1,0)` on `read_sync` only; data
reads are plain).

## 3. Video timing

`set_screen_raw_params` (L1977-1981): 12 MHz / 2 = 6 MHz pixel clock,
384 pixels per line (visible 0-255), 272 lines per frame (visible 8-247),
57.444853 Hz. Comment: "DECO video CRTC, matches PCB measurements". The
oracle confirms MAME's frame notifier runs at line 248 (vblank start).

`driver_device::flip_screen_set` flips every tilemap (TILEMAP_FLIPX |
TILEMAP_FLIPY). The visible area stays 0-255 x 8-247 when flipped (the
oracle dumps it every frame: identical in all 600 flipped frames), so a
flipped tilemap pixel at screen (x, y) is the logical pixel
((scroll_x + 255 - x) mod width, (scroll_y + 255 - y) mod height), with
256 = visarea min + max + 1 in both directions.

## 4. Memory maps (main CPU)

### lastmisn (L301-326; sub CPU L328-350)

| Address | Main | Sub |
|---|---|---|
| 0x0000-0x0fff | RAM shared with sub ("share1") | same |
| 0x1000-0x13ff / 0x1400-0x17ff | palette (R,G) / palette ext (B), RM-C3 | same |
| 0x1800-0x1804 read | IN0, IN1, IN2, DSW0, DSW1 | same |
| 0x1800 / 01 / 02 / 03 / 04 write | sub IRQ off / main IRQ off / both FIRQ off / main IRQ on / sub IRQ on | same |
| 0x1805 | sprite buffer copy (buffer_spriteram16_w, L83-90) | same |
| 0x1806 / 0x1807 read | MCU return hi / lo | same |
| 0x1807 write | flip screen | same |
| 0x1809 / 0x180b | scroll x LSB / scroll y LSB | (not mapped) |
| 0x180c | sound latch (6502 NMI on data pending) | same |
| 0x180d | control: bank (bits 0-3), x/y scroll MSB (bits 5/6), sub CPU reset (bit 7) (dec8_v.cpp L93-120) | (not mapped) |
| 0x180e / 0x180f | MCU value hi (asserts MCU INT1 if P2.1 high) / lo | same |
| 0x2000-0x27ff | fix (text) RAM | same |
| 0x2800-0x2fff | sprite RAM | same (write only) |
| 0x3000-0x37ff | RAM shared with sub ("share2") | same |
| 0x3800-0x3fff | bg tile RAM | same |
| 0x4000-0x7fff | ROM bank (16 KB, "mainbank") | sub ROM |
| 0x8000-0xffff | fixed ROM | sub ROM |

There is no vblank interrupt: IN0 bit 7 reads vblank; interrupts come from
the CPUs writing each other's IRQ lines and from the MCU (P2.2 rise = FIRQ
to both CPUs, L732-766). Coins go to the MCU (INT0 through an input merger,
L1886-1891).

### gondo (L427-447)

| Address | Use |
|---|---|
| 0x0000-0x17ff | RAM |
| 0x1800-0x1fff | fix RAM |
| 0x2000-0x27ff | bg tile RAM |
| 0x2800-0x2bff / 0x2c00-0x2fff | palette / palette ext |
| 0x3000-0x37ff | sprite RAM |
| 0x3800 / 0x3801 | DSW0 / DSW1 |
| 0x380a-0x380b / 0x380c-0x380d | player 1 / 2: rotary (12 positions, one-hot) + joystick (player_io_r, L115-129) |
| 0x380e / 0x380f | IN3 (starts) / IN2 (buttons) |
| 0x3810 | sound latch + 6502 NMI for 4 audio cycles (L233-238) |
| 0x3818-0x382f | scroll: +0x00 x LSB, +0x08 y LSB, +0x10 bit 0 x MSB, bit 1 y MSB, bit 2 sprite buffer strobe (rising edge copies) (dec8_v.cpp L132-147) |
| 0x3830 | bank: bit 0 SECCLR (clears main IRQ), bit 1 NMI enable, bit 3 flip, bits 4-7 ROM bank (L191-213) |
| 0x3838 / 0x3839 | MCU return hi / lo |
| 0x383a / 0x383b | MCU value hi (MCU INT1, cleared after 4 ticks of 1.5 MHz, L174-180) / lo |
| 0x4000-0x7fff / 0x8000-0xffff | bank / fixed ROM |

NMI = vblank AND the bank register's NMI enable (input merger, L2131-2135),
applied one CPU quantum after the enable write (L204-206, the ghostb TODO
note at the top of the file). Vblank also drives MCU INT0. MCU P2.2 rise
raises the main IRQ while SECCLR is high (L709-730).

### srdarwin (L562-584; srdarwinb L586-592)

| Address | Use |
|---|---|
| 0x0000-0x05ff | RAM |
| 0x0600-0x07ff | sprite RAM (512 bytes) |
| 0x0800-0x0fff | fix RAM (one byte per tile; the 32x32 tilemap uses 0x0800-0x0bff) |
| 0x1000-0x13ff | RAM |
| 0x1400-0x17ff | bg tile RAM |
| 0x1800 / 0x1801 | MCU value hi / lo |
| 0x1803 | write ignored |
| 0x1804 | sprite buffer copy (buffered_spriteram8 write) |
| 0x1805 | bits 5-7 ROM bank, bits 0-3 scroll x MSB (dec8_v.cpp L78-91) |
| 0x1806 | scroll x LSB |
| 0x2000 | read MCU return hi / write sound latch |
| 0x2001 | read MCU return lo (srdarwinb: COIN port) / write flip |
| 0x2800-0x288f / 0x3000-0x308f | palette / palette ext (144 entries) |
| 0x3800-0x3803 | DSW0, IN0, IN1, DSW1 |
| 0x4000-0x7fff / 0x8000-0xffff | bank / fixed ROM |

NMI = vblank (L2440). The MCU has no interrupt path to the main CPU
("P22: maincpu has no IRQ/FIRQ handler", L768-790).

### Sound CPU maps

| Map | Used by | YM2203 | OPL | Latch read | Lines |
|---|---|---|---|---|---|
| ym3526_s_map | lastmisn | 0x0800 | YM3526 0x1000 | 0x3000 | L651-658 |
| oscar_s_map | gondo | 0x2000 | YM3526 0x4000 | 0x6000 | L635-641 |
| dec8_s_map | srdarwin | 0x2000 | YM3812 0x4000 | 0x6000 | L625-631 |

RAM 0x0000-0x05ff, ROM 0x8000-0xffff in all three. Sound IRQ = YM2203 IRQ
OR OPL IRQ (input merger). Mix: YM2203 SSG channels 0.20 each, FM 0.40,
OPL 0.80 (gondo 0.50) (L2032-2041, L2147-2156, L2453-2463).

## 5. i8751 (MCU) protocol

The main CPU writes a 16-bit value (hi, lo); the MCU reads it through two
LS374 latches on P0/P1, enabled by P2.4/P2.5 falling edges, and returns 16
bits through P2.6/P2.7 (L689-790, schematic notes L680-688). P3 holds the
coin inputs. INT1 = "SECIRQ" from the main CPU's value write; per-machine
differences:

| Machine | INT1 assert | INT1 clear | MCU to main |
|---|---|---|---|
| lastmisn | value hi write when P2.1 is high (L156-163) | P2.1 low | P2.2 rise: FIRQ to both 6809s; P2.0 low clears INT0 (coin) |
| gondo | value hi write, edge (L174-180) | timer, 4 ticks of 12 MHz / 8 | P2.2 rise: main IRQ (if SECCLR) |
| srdarwin | value hi write when P2.1 is high | P2.1 low | none; P0 only (single port) |

## 6. Graphics decode (dec8.cpp L1722-1871)

| Layout | Size | Planes (bit offsets) | Used for |
|---|---|---|---|
| chars_3bpp | 8x8, 1024 | 0x6000*8, 0x4000*8, 0x2000*8 | lastmisn, gondo fix |
| charlayout_16k | 8x8, 1024, 2bpp | 0, 4 (packed, x halves 0x2000 apart) | srdarwin fix |
| tiles | 16x16, 4096, 4bpp | 0x60000*8, 0x40000*8, 0x20000*8, 0 | lastmisn, gondo bg and sprites |
| sr_sprites | 16x16, 2048, 3bpp | 0x10000*8, 0x20000*8, 0 | srdarwin sprites |
| srdarwin_tiles | 16x16, 256, 4bpp | 0x8000*8, 0x8000*8+4, 0, 4 | srdarwin bg, 4 banks at 0x10000 |

Colour bases: lastmisn fix 0 (4 x 8), bg 768 (16 x 16), sprites 256
(16 x 16); gondo fix 0 (16 x 8), bg 768, sprites 256 (32 x 16); srdarwin bg
0 (8 x 16), sprites 64 (8 x 8), fix 128 (4 x 4).

Palette (decrmc3.cpp L186-224): entry = RAM[i] | EXT[i] << 8, R = bits 0-3,
G = 4-7, B = 8-11, each 4-bit value weighted 0x0e, 0x1f, 0x43, 0x8f (the
DECO RM-C3 resistor pack). 1024 entries (srdarwin 144).

## 7. Layers

### lastmisn (dec8_v.cpp L334-345, L359-398)
- bg: 32x32 16x16 tiles (512 x 512), memory order by `lastmisn_scan_rows`
  (four 16x16-tile quadrants), word = RAM[2i] << 8 | RAM[2i+1], colour =
  bits 12-15, code bits 0-11; x scroll 9 bits (control bit 5 + 0x1809),
  y scroll 9 bits (control bit 6 + 0x180b); drawn opaque.
- sprites: Karnov sprite chip model (section 8), no priority callback.
- fix: 32x32 8x8, colour bits 14-15, code bits 0-11 (wraps at 1024), pen 0
  transparent, no scroll.

### gondo (L462-480, L494-524)
- bg as lastmisn but plain row order; pens 0-7 = layer 1 (priority 1),
  pens 8-15 = layer 0 (priority 2) (transmask 0x00ff / 0xff00).
- sprites: Karnov with `gondo_colpri_cb`: colour bit 3 puts the sprite
  behind bg pens 8-15 (MAME comment: "all tiles with *pens* 8-15 appear over
  sprites with palettes 8-15").
- fix: colour bits 12-14.

### srdarwin (L412-460, sprites L159-205)
- bg: 32 x 16 tiles of 16x16 (512 x 256), x scroll only (12 bits),
  colour = bits 12-13, code = bits 0-9 (bank = code / 256 + 2), tile group =
  colour: group 0 = all pens behind sprites, group 3 = all pens in front
  (priority 2), groups 1-2 = pens 0-7 behind, 8-15 in front.
- sprites (512-byte list, 128 entries, drawn from the last to the first;
  the first opaque pixel wins): byte 0 y (0xf8 = off), byte 1 colour (bits
  0-1, 3), flip x (bit 2), double height (bit 4), code bits 8-10 (bits 5-7),
  byte 2 x (screen x = 241 - x), byte 3 code bits 0-7; code 0 = off; colour
  0 sprites go behind priority 2; no wrap (MAME TODO: "srdarwin 'double'
  sprites appearing from the top of the screen are clipped").
- fix: 32x32 8x8, one byte per tile, colour 0 only, pen 0 transparent.

## 8. Karnov sprite chip model (deckarn.cpp)

Four words per sprite, 256 sprites (0x400 words, copied from the 8-bit
sprite RAM as big-endian words by `buffer_spriteram16_w`, dec8.cpp L83-90):
word 0 bit 15 enable, bit 11 double height, bits 0-8 y; word 1 bit 0 must
be set, bit 1 flip y, bit 2 flip x; word 2 bits 0-8 x; word 3 bits 12-15
colour, bits 0-11 code. Screen position x = 256 - ((x + 16) & 0x1ff), same
for y. With a priority callback (gondo) the list is drawn from the last
entry to the first; without (lastmisn) from the first to the last, later
over earlier. In dec8.cpp nothing sets the sprite chip's own flip flag
(`m_flip_screen` of `:spritegen_krn`), so in MAME the Karnov sprites are
never flipped even when the screen is (section 13, R7).

## 9. Sprite buffering

| Machine | Copy trigger | Source |
|---|---|---|
| lastmisn | any write to 0x1805 (main or sub) | buffer_spriteram16_w L83-90 |
| gondo | rising edge of 0x3828 bit 2 | dec8_v.cpp L142-146, L93-100 |
| srdarwin | any write to 0x1804 | buffered_spriteram8 |

MAME copies instantly. The real copy is a DMA of some duration (research
item R3).

## 10. Inputs

lastmisn: IN0/IN1 8-way + 3 buttons per player, IN2 starts, COIN to the
MCU. gondo: 8-way stick plus a 12-position rotary per player (PORT_POSITIONAL
AN0/AN1), 2 buttons, starts on IN3. srdarwin: 8-way, 2 buttons, starts on
IN0. DIP switch tables are in the INPUT_PORTS blocks (L824-1060, L1552-1642)
and will be generated into the MRAs from the driver, as in the other cores.

## 11. Priority PROMs

lastmisn `dl-14.9c`, gondo `ds-23.b10`, srdarwin `dy_11.c11` (MAME:
"Priority (Not yet used)"). MAME implements priority with fixed rules
(section 7); the real boards decode it through these PROMs (R2).

## 12. MAME 0.288 vs master

Master moved Gondomania to `ghostb.cpp`, Last Mission to `lastmisn.cpp`
and SRD to `srdarwin.cpp`; the bootleg is now `srdarwinjbl` with its own
init. Behavioural differences that matter to the oracle are re-checked when
the core reaches M2 (oracle stays 0.288, matching the other cores).

## 13. MAME uncertainties and TODOs

| # | Item | Where |
|---|---|---|
| T1 | srdarwin double sprites at the top are clipped (should wrap?) | TODO L44 |
| T2 | gondo second coin does not work, "probably due to hacked MCU ROM" | TODO L46 |
| T3 | gondo/ghostb NMI needs "1 more opcode" after enabling it | TODO L48-63, L204-206 |
| T4 | gondo MCU INT1 auto-clear after 4 ticks; ghostb uses 64 ("not confirmed") | L165-180 |
| T5 | srdarwin MCU clock "unknown frequency"; CPU type "MC68A09EP or HD63?09EP" | L2419-2426 |
| T6 | priority PROMs unused | ROM comments |
| T7 | Karnov sprites never flipped in dec8 | section 8 |
| T8 | srdarwin fix colour "?" (always 0) | dec8_v.cpp L424-432 |
