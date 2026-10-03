#!/usr/bin/env python3
"""Reference renderer for DEC8 frames (Last Mission, Gondomania, SRD),
written from MAME 0.288's dec8.cpp / dec8_v.cpp / deckarn.cpp / decrmc3.cpp
(reference/mame/v0288, line numbers below). It renders one oracle frame
dump (sim/mame/d8_oracle.lua) to RGB, pixel for pixel as MAME does, so the
RTL can later be checked against this model and MAME's snapshots.

Model, per machine (screen_update functions in dec8_v.cpp):
  lastmisn  bg tilemap opaque (L334-345), Karnov sprites in list order,
            later entries over earlier (deckarn.cpp L31-34, no colpri
            callback), fix tilemap pen 0 transparent.
  gondo     bg layer 1 (pens 0-7) at priority 1, bg layer 0 (pens 8-15) at
            priority 2 (transmask group 0: 0x00ff / 0xff00, L517-524), Karnov
            sprites with gondo_colpri_cb (L462-467): colour bit 3 = behind
            priority 2; first opaque sprite pixel wins (MAME pdrawgfx sets
            the priority pixel to 31); fix tilemap on top.
  srdarwin  bg 512 x 256, x scroll only (L412-422, L434-445); tile groups =
            colour with transmasks L447-460; layer 1 at priority 1, layer 0 at 2;
            sprites from 0x1fc down to 0, colour 0 behind priority 2, first
            opaque pixel wins (L159-205); fix tilemap 8x8, one byte a tile.

Tilemap scroll and flip follow tilemap.cpp: unflipped, pixmap x = screen x
+ scroll (mod width); flipped (driver_device::flip_screen_set flips every
tilemap), the logical x = (scroll + sw - 1 - x) mod width with sw =
visarea min_x + max_x + 1 = 256, likewise for y (the visible area does not
move when flipped in MAME 0.288; the dump records it per frame). Sprites
use the coordinates each sprite routine computes, clipped to the visible
area.

Graphics are decoded from the gfx_layout definitions (dec8.cpp L1722-1817)
with MAME's bit addressing (MSB first, plane 0 = most significant pen bit);
an element index past the layout's total wraps (code % elements), as
gfx_element::get_data and tilemap tile_info do.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REGIONS = ROOT / "sim" / "build" / "regions"

# ---------------------------------------------------------------- layouts
# (width, height, total, planes, xoffs, yoffs, charincrement) in bits
CHARS_3BPP = (8, 8, 1024, (0x6000 * 8, 0x4000 * 8, 0x2000 * 8),
              tuple(range(8)), tuple(i * 8 for i in range(8)), 64)
CHARS_16K = (8, 8, 1024, (0, 4),
             (0x2000 * 8 + 0, 0x2000 * 8 + 1, 0x2000 * 8 + 2, 0x2000 * 8 + 3, 0, 1, 2, 3),
             tuple(i * 8 for i in range(8)), 64)
SR_SPRITES = (16, 16, 2048, (0x10000 * 8, 0x20000 * 8, 0x00000 * 8),
              tuple([16 * 8 + i for i in range(8)] + list(range(8))),
              tuple(i * 8 for i in range(16)), 256)
SR_TILES = (16, 16, 256, (0x8000 * 8, 0x8000 * 8 + 4, 0, 4),
            (0, 1, 2, 3, 1024 * 64 + 0, 1024 * 64 + 1, 1024 * 64 + 2, 1024 * 64 + 3,
             128 + 0, 128 + 1, 128 + 2, 128 + 3, 128 + 1024 * 64 + 0, 128 + 1024 * 64 + 1,
             128 + 1024 * 64 + 2, 128 + 1024 * 64 + 3),
            tuple(i * 8 for i in range(16)), 256)
TILES = (16, 16, 4096, (0x60000 * 8, 0x40000 * 8, 0x20000 * 8, 0x00000 * 8),
         tuple([16 * 8 + i for i in range(8)] + list(range(8))),
         tuple(i * 8 for i in range(16)), 256)


def decode(data, layout, start=0):
    """All elements of a layout as uint8 pens [n, h, w]."""
    w, h, total, planes, xo, yo, inc = layout
    src = np.frombuffer(data, dtype=np.uint8)
    nbits = len(src) * 8
    bits = np.unpackbits(src)              # MSB first, MAME's readbit order
    off = (np.array(yo)[:, None] + np.array(xo)[None, :])        # [h, w]
    base = start * 8 + np.arange(total)[:, None, None] * inc     # [n,1,1]
    out = np.zeros((total, h, w), dtype=np.uint8)
    np_ = len(planes)
    for p, po in enumerate(planes):
        idx = base + po + off[None]
        valid = idx < nbits
        b = np.where(valid, bits[np.minimum(idx, nbits - 1)], 0)
        out |= (b << (np_ - 1 - p)).astype(np.uint8)
    return out


@lru_cache(maxsize=16)
def gfx(setname, region, layout_name, start=0):
    data = (REGIONS / setname / f"{region}.bin").read_bytes()
    return decode(data, LAYOUTS[layout_name], start)


LAYOUTS = {"chars_3bpp": CHARS_3BPP, "chars_16k": CHARS_16K, "sr_sprites": SR_SPRITES,
           "sr_tiles": SR_TILES, "tiles": TILES}

# ---------------------------------------------------------------- palette
W4 = np.array([0x0e, 0x1f, 0x43, 0x8f])


def _weight(v):
    return (((v >> 0) & 1) * 0x0e + ((v >> 1) & 1) * 0x1f + ((v >> 2) & 1) * 0x43
            + ((v >> 3) & 1) * 0x8f)


def palette_rgb(pal, ext):
    """DECO RM-C3 (decrmc3.cpp L214-224): entry = pal[i] | ext[i] << 8,
    r = bits 0-3, g = 4-7, b = 8-11, custom resistor weights."""
    p = np.frombuffer(pal, dtype=np.uint8).astype(np.int32)
    e = np.frombuffer(ext, dtype=np.uint8).astype(np.int32)
    r, g, b = _weight(p & 0xf), _weight(p >> 4), _weight(e & 0xf)
    return np.stack([r, g, b], axis=-1)


# ---------------------------------------------------------------- tilemaps
def tilemap_pixmap(codes, colors, elems, colorbase, gran, cols, rows, tw, th):
    """Logical pen-index pixmap [rows*th, cols*tw] (palette index) and raw pen."""
    tiles = elems[codes % len(elems)]                      # [rows, cols, th, tw]
    pens = tiles.transpose(0, 2, 1, 3).reshape(rows * th, cols * tw)
    col = np.repeat(np.repeat(colors, th, axis=0), tw, axis=1)
    return pens, colorbase + col * gran + pens


def sample(pixmap, scrollx, scrolly, flip, vis, ys, xs):
    """Map screen coordinates to logical pixmap coordinates (tilemap.cpp
    effective_rowscroll/colscroll + draw_instance)."""
    H, W = pixmap.shape
    if not flip:
        lx = (xs + scrollx) % W
        ly = (ys + scrolly) % H
    else:
        sw = vis[0] + vis[1] + 1
        sh = vis[2] + vis[3] + 1
        lx = (scrollx + sw - 1 - xs) % W
        ly = (scrolly + sh - 1 - ys) % H
    return pixmap[np.ix_(ly, lx)]


# ---------------------------------------------------------------- sprites
def blit(dst_pen, dst_pri, elem, colorbase, sx, sy, fx, fy, vis, pmask, prio):
    """drawgfx transpen (prio=False: later overwrites) or prio_transpen
    (prio=True: drawn only if (1 << pri) & pmask == 0; the priority pixel
    becomes 31 for every opaque source pixel, so the first sprite wins)."""
    h, w = elem.shape
    e = elem[::-1] if fy else elem
    e = e[:, ::-1] if fx else e
    x0, x1 = max(sx, vis[0]), min(sx + w, vis[1] + 1)
    y0, y1 = max(sy, vis[2]), min(sy + h, vis[3] + 1)
    if x0 >= x1 or y0 >= y1:
        return
    src = e[y0 - sy:y1 - sy, x0 - sx:x1 - sx].astype(np.int32)
    opaque = src != 0
    reg = (slice(y0, y1), slice(x0, x1))
    if prio:
        pri = dst_pri[reg]
        ok = opaque & (((1 << (pri.astype(np.int64) & 0x1f)) & (pmask | (1 << 31))) == 0)
        dst_pen[reg] = np.where(ok, colorbase + src, dst_pen[reg])
        dst_pri[reg] = np.where(opaque, 31, pri)
    else:
        dst_pen[reg] = np.where(opaque, colorbase + src, dst_pen[reg])


PMASK_2 = 0xcccc   # GFX_PMASK_2


def karnov_sprites(pen, pri, buf, elems, colorbase, gran, vis, flip_dev, colpri):
    """deco_karnovsprites_device::draw_sprites (deckarn.cpp L31-125)."""
    words = np.frombuffer(buf, dtype=">u2").astype(np.int64)
    size = 0x400
    order = range(size - 4, -4, -4) if colpri else range(0, size, 4)
    n = 0
    for offs in order:
        d0 = int(words[offs])
        if not (d0 >> 15) & 1:
            continue
        y = d0 & 0x1ff
        d3 = int(words[offs + 3])
        colour = d3 >> 12
        pmask = 0
        if colpri:
            if colour & 8:
                pmask |= PMASK_2
        sprite = d3 & 0xfff
        x = int(words[offs + 2]) & 0x1ff
        d1 = int(words[offs + 1])
        if not d1 & 1:
            continue
        n += 1
        extra = (d0 >> 11) & 1
        fy = (d1 >> 1) & 1
        fx = (d1 >> 2) & 1
        if extra:
            y += 16
            sprite &= 0xffe
        x = (x + 16) & 0x1ff
        y = (y + 16) & 0x1ff
        x = 256 - x
        y = 256 - y
        if flip_dev:
            y = 240 - y
            x = 240 - x
            fx, fy = 1 - fx, 1 - fy
            if extra:
                y -= 16
        if extra and fy:
            sprite2 = sprite
            sprite |= 1
        else:
            sprite2 = sprite | 1
        cb = colorbase + colour * gran
        blit(pen, pri, elems[sprite % len(elems)], cb, x, y, fx, fy, vis, pmask, colpri)
        if extra:
            blit(pen, pri, elems[sprite2 % len(elems)], cb, x, y + 16, fx, fy, vis, pmask, colpri)
    return n


def srdarwin_sprites(pen, pri, buf, elems, vis, flip):
    """srdarwin_state::draw_sprites (dec8_v.cpp L159-205)."""
    b = buf
    n = 0
    for offs in range(0x200 - 4, -4, -4):
        b1 = b[offs + 1]
        color = (b1 & 0x03) + ((b1 & 0x08) >> 1)
        pmask = PMASK_2 if color == 0 else 0
        code = b[offs + 3] + ((b1 & 0xe0) << 3)
        if not code:
            continue
        sy = b[offs]
        if sy == 0xf8:
            continue
        n += 1
        sx = 241 - b[offs + 2]
        fx = 1 if b1 & 0x04 else 0
        multi = b1 & 0x10
        if flip:
            sy = 240 - sy
            sx = 240 - sx
            fx = 1 - fx
            sy2 = sy - 16
        else:
            sy2 = sy + 16
        cb = 64 + color * 8
        blit(pen, pri, elems[code % len(elems)], cb, sx, sy, fx, flip, vis, pmask, True)
        if multi:
            blit(pen, pri, elems[(code + 1) % len(elems)], cb, sx, sy2, fx, flip, vis, pmask, True)
    return n


# ---------------------------------------------------------------- frame
def render(frame_dir, regions_set=None, pens=False):
    """Return (rgb [240, 256, 3] of the visible area, stats dict), plus the
    palette index of every pixel [240, 256] when pens=True (M1 replay)."""
    d = Path(frame_dir)
    st = json.loads((d / "state.json").read_text())
    setname = regions_set or st["set"]
    mach = st["machine"]
    vis = st.get("visarea", [0, 255, 8, 247])
    flip = bool(st["flip_x"])
    sc = st["scroll"]
    fix = (d / "fixram.bin").read_bytes()
    bg = (d / "bgram.bin").read_bytes()
    spr = (d / "spr_buf.bin").read_bytes()
    pal = palette_rgb((d / "palette.bin").read_bytes(), (d / "palette_ext.bin").read_bytes())
    pw = d / "palette_written.bin"
    if pw.exists():
        # entries the game never wrote show MAME's power-on pens (a default
        # pattern, not hardware state: real palette RAM powers up random)
        written = np.frombuffer(pw.read_bytes(), dtype=np.uint8).astype(bool)[:len(pal)]
        mp = np.frombuffer((d / "pens.bin").read_bytes(), dtype="<u4")[:len(pal)]
        mame = np.stack([(mp >> 16) & 255, (mp >> 8) & 255, mp & 255], axis=-1)
        pal = np.where(written[:, None], pal, mame)

    H, W = 272, 384
    pen = np.zeros((H, W), dtype=np.int32)
    pri = np.zeros((H, W), dtype=np.int32)
    ys = np.arange(vis[2], vis[3] + 1)
    xs = np.arange(vis[0], vis[1] + 1)
    win = (slice(vis[2], vis[3] + 1), slice(vis[0], vis[1] + 1))

    fb = np.frombuffer(fix, dtype=np.uint8).astype(np.int64)
    bb = np.frombuffer(bg, dtype=np.uint8).astype(np.int64)
    stats = {}

    if mach in ("lastmisn", "gondo"):
        # fix layer: 32x32 8x8 rows, word = ram[2i] << 8 | ram[2i+1]
        fw = (fb[0:2048:2] << 8) | fb[1:2048:2]
        if mach == "lastmisn":
            fcol = (fw & 0xc000) >> 14          # get_lastmisn_fix_tile_info L379-386
        else:
            fcol = (fw & 0x7000) >> 12          # get_gondo_fix_tile_info L494-501
        fcode = fw & 0xfff
        fx_pens, fx_pix = tilemap_pixmap(fcode.reshape(32, 32), fcol.reshape(32, 32),
                                         gfx(setname, "char", "chars_3bpp"), 0, 8, 32, 32, 8, 8)
        # bg layer: 32x32 16x16
        bw = (bb[0:2048:2] << 8) | bb[1:2048:2]
        if mach == "lastmisn":
            col, row = np.meshgrid(np.arange(32), np.arange(32))
            mem = (col & 0x0f) + ((row & 0x0f) << 4) + ((col & 0x10) << 4) + ((row & 0x10) << 5)
            bw = bw[mem]                        # lastmisn_scan_rows L359-363
        else:
            bw = bw.reshape(32, 32)
        bcode, bcol = bw & 0xfff, bw >> 12
        bg_pens, bg_pix = tilemap_pixmap(bcode, bcol, gfx(setname, "tiles1", "tiles"), 768, 16, 32, 32, 16, 16)
        sx = (sc[0] << 8) + sc[1]
        sy = (sc[2] << 8) + sc[3]
        bpen = sample(bg_pens, sx, sy, flip, vis, ys, xs)
        bpix = sample(bg_pix, sx, sy, flip, vis, ys, xs)
        pen[win] = bpix
        if mach == "gondo":
            pri[win] = np.where(bpen >= 8, 2, 1)
        sp_el = gfx(setname, "sprites", "tiles")
        stats["sprites_drawn"] = karnov_sprites(pen, pri, spr, sp_el, 256, 16, vis,
                                                bool(st.get("krn_flip", 0) > 0), mach == "gondo")
        fpen = sample(fx_pens, 0, 0, flip, vis, ys, xs)
        fpix = sample(fx_pix, 0, 0, flip, vis, ys, xs)
        pen[win] = np.where(fpen != 0, fpix, pen[win])
    else:
        # srdarwin bg: 32 cols x 16 rows of 16x16, word = ram[2i] << 8 | ram[2i+1]
        bw = ((bb[0:1024:2] << 8) | bb[1:1024:2]).reshape(16, 32)
        bcol = (bw >> 12) & 3
        code = bw & 0x3ff
        banks = [gfx(setname, "tiles1", "sr_tiles", 0x10000 * k) for k in range(4)]
        tiles = np.stack([banks[c >> 8][c & 0xff] for c in code.ravel()]).reshape(16, 32, 16, 16)
        bg_pens = tiles.transpose(0, 2, 1, 3).reshape(256, 512)
        grp = np.repeat(np.repeat(bcol, 16, axis=0), 16, axis=1)
        bg_pix = grp * 16 + bg_pens
        sx = ((sc[0] << 8) + sc[1])
        bpen = sample(bg_pens, sx, 0, flip, vis, ys, xs)
        bgrp = sample(grp, sx, 0, flip, vis, ys, xs)
        bpix = sample(bg_pix, sx, 0, flip, vis, ys, xs)
        # transmasks (video_start L447-460): group 0 all in layer 1, group 3 all in
        # layer 0, groups 1-2 pens 0-7 layer 1 and pens 8-15 layer 0
        layer0 = (bgrp == 3) | (((bgrp == 1) | (bgrp == 2)) & (bpen >= 8))
        pen[win] = bpix
        pri[win] = np.where(layer0, 2, 1)
        sp_el = gfx(setname, "sprites", "sr_sprites")
        stats["sprites_drawn"] = srdarwin_sprites(pen, pri, spr, sp_el, vis, flip)
        ch = np.frombuffer(fix[:1024], dtype=np.uint8).astype(np.int64).reshape(32, 32)
        fx_pens, fx_pix = tilemap_pixmap(ch, np.zeros_like(ch), gfx(setname, "char", "chars_16k"),
                                         128, 4, 32, 32, 8, 8)
        fpen = sample(fx_pens, 0, 0, flip, vis, ys, xs)
        fpix = sample(fx_pix, 0, 0, flip, vis, ys, xs)
        pen[win] = np.where(fpen != 0, fpix, pen[win])

    pidx = np.clip(pen[win], 0, len(pal) - 1)
    if pw.exists():
        stats["unwritten_px"] = int((~written[pidx]).sum())
    rgb = pal[pidx].astype(np.uint8)
    if pens:
        return rgb, stats, pidx
    return rgb, stats


if __name__ == "__main__":
    import sys
    from PIL import Image
    rgb, s = render(sys.argv[1])
    Image.fromarray(rgb).save(sys.argv[2] if len(sys.argv) > 2 else "render.png")
    print(s)
