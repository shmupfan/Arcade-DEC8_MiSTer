#!/usr/bin/env python3
"""Graphics ROM layout for the DEC8 video RTL (PLAN M1, m1_findings 2).

The RTL reads graphics as 32-bit words, 8 pixels a word, from one ROM port.
MAME's layouts (dec8.cpp L1722-1817) are planar, with each bitplane in a
different ROM (or ROM half), so a word here is the plane bytes that cover
the same 8 pixels, side by side: something an MRA can build with a byte
interleave of the ROM files (M4), with no bit shuffling.

Byte layout of the graphics block (the RTL's ROM port addresses; M4 places
the block in SDRAM), word = 4 bytes, byte 0 = bits 31-24:

  lastmisn, gondo (machine 0, 1)
    0x000000  bg tiles  'tiles' 16x16 4bpp, region tiles1 (4 planes 0x20000
              apart): word i = {p0[i], p1[i], p2[i], p3[i]} with pN = byte at
              plane offset N*0x20000 (pN holds pen bit N); a tile row's
              pixels 0-7 are at i = code*32 + 16 + row, 8-15 at code*32 + row
    0x080000  sprites   the same layout from region sprites
    0x100000  fix chars 'chars_3bpp' 8x8 3bpp, region char (planes at 0x2000
              pen bit 0, 0x4000 bit 1, 0x6000 bit 2): word i = {c[0x2000+i],
              c[0x4000+i], c[0x6000+i], 0}, i = code*8 + row
  srdarwin (machine 2)
    0x000000  bg tiles  'srdarwin_tiles' 16x16 4bpp in 4 banks of 256 tiles
              (bank k at region offset 0x10000*k; planes P0 = byte+0x8000
              high nibble, P1 = byte+0x8000 low nibble, P2 = byte high
              nibble, P3 = byte low nibble; pixels 4-7 of each 8 at +0x2000):
              word k*0x2000 + o = {t[b+0x8000+o], t[b+o], t[b+0xa000+o],
              t[b+0x2000+o]}, b = 0x10000*k, o = tile*32 + row for pixels
              0-7 and tile*32 + 16 + row for pixels 8-15 (the opposite
              order to the 'tiles' and 'sr_sprites' layouts)
    0x080000  sprites   'sr_sprites' 16x16 3bpp (planes 0x00000 bit 0,
              0x20000 bit 1, 0x10000 bit 2): word i = {s[i], s[0x20000+i],
              s[0x10000+i], 0}, pixels 0-7 at code*32 + 16 + row
    0x100000  fix chars 'charlayout_16k' 8x8 2bpp: word i = {c[0x2000+i],
              c[i], 0, 0} (pixels 0-3 from the first byte: pen bit 1 = bit
              7-x, pen bit 0 = bit 3-x; pixels 4-7 from the second)

Pixel decode in the RTL (x = 0..7 within the word, MSB first): see
`decode_word` below; `--check` proves every element of every layout decodes
to the renderer's MAME decode (sim/oracle/d8_render.py).

Usage:
  gfx_layout.py <set>...        write sim/build/regions/<set>/gfx.bin
  gfx_layout.py --check <set>...  also verify against d8_render.decode
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REGIONS = ROOT / "sim" / "build" / "regions"
sys.path.insert(0, str(ROOT / "sim" / "oracle"))

SIZE = 0x108000
BASE = {"bg": 0x000000, "spr": 0x080000, "fix": 0x100000}


def region(setname, tag, size):
    p = REGIONS / setname / f"{tag}.bin"
    b = p.read_bytes() if p.exists() else b""
    return np.frombuffer((b + bytes(size))[:size], dtype=np.uint8)


def words(lanes):
    """[n, 4] uint8 lanes -> bytes, lane 0 first (bits 31-24)."""
    return np.ascontiguousarray(np.stack(lanes, axis=1).astype(np.uint8)).tobytes()


def build(setname):
    man = json.loads((REGIONS / setname / "manifest.json").read_text())
    machine = man["machine"]
    out = bytearray(SIZE)
    z = None
    if machine in ("lastmisn", "gondo"):
        for key, tag in (("bg", "tiles1"), ("spr", "sprites")):
            r = region(setname, tag, 0x80000)
            p = [r[n * 0x20000:(n + 1) * 0x20000] for n in range(4)]
            blk = words(p)
            out[BASE[key]:BASE[key] + len(blk)] = blk
        c = region(setname, "char", 0x8000)
        z = np.zeros(0x2000, dtype=np.uint8)
        blk = words([c[0x2000:0x4000], c[0x4000:0x6000], c[0x6000:0x8000], z])
        out[BASE["fix"]:BASE["fix"] + len(blk)] = blk
    else:
        t = region(setname, "tiles1", 0x40000)
        parts = []
        for k in range(4):
            b = 0x10000 * k
            parts.append(words([t[b + 0x8000:b + 0xa000], t[b:b + 0x2000],
                                t[b + 0xa000:b + 0xc000], t[b + 0x2000:b + 0x4000]]))
        blk = b"".join(parts)
        out[BASE["bg"]:BASE["bg"] + len(blk)] = blk
        s = region(setname, "sprites", 0x30000)
        z = np.zeros(0x10000, dtype=np.uint8)
        blk = words([s[0:0x10000], s[0x20000:0x30000], s[0x10000:0x20000], z])
        out[BASE["spr"]:BASE["spr"] + len(blk)] = blk
        c = region(setname, "char", 0x8000)
        z = np.zeros(0x2000, dtype=np.uint8)
        blk = words([c[0x2000:0x4000], c[0:0x2000], z, z])
        out[BASE["fix"]:BASE["fix"] + len(blk)] = blk
    (REGIONS / setname / "gfx.bin").write_bytes(bytes(out))
    return machine, bytes(out)


def decode_word(w, fmt):
    """The RTL's pixel decode of one 32-bit word (numpy array of words) ->
    [n, 8] pens. fmt: 'k4' (4 plane bytes), 'p3' (3 plane bytes: K chars
    and SR sprites), 'srt' (SRD tiles), 'src' (SRD chars)."""
    w = np.asarray(w, dtype=np.uint64)
    lane = [(w >> (24 - 8 * n)) & 0xFF for n in range(4)]
    out = np.zeros((len(w), 8), dtype=np.uint8)
    for x in range(8):
        b = 7 - x
        if fmt == "k4":
            pen = sum(((lane[n] >> b) & 1) << n for n in range(4))
        elif fmt == "p3":
            pen = sum(((lane[n] >> b) & 1) << n for n in range(3))
        elif fmt == "srt":
            a, c = (lane[0], lane[1]) if x < 4 else (lane[2], lane[3])
            xx = x & 3
            pen = (((a >> (7 - xx)) & 1) << 3) | (((a >> (3 - xx)) & 1) << 2) | \
                  (((c >> (7 - xx)) & 1) << 1) | ((c >> (3 - xx)) & 1)
        else:  # src
            a = lane[0] if x < 4 else lane[1]
            xx = x & 3
            pen = (((a >> (7 - xx)) & 1) << 1) | ((a >> (3 - xx)) & 1)
        out[:, x] = pen
    return out


def check(setname, machine, gfx):
    from d8_render import gfx as mame_gfx
    arr = np.frombuffer(gfx, dtype=">u4").astype(np.uint64)
    bad = []

    def tile16(base_word, fmt, ntiles, ref, left_off=16):
        # word for tile t row r: pixels 0-7 at +left_off, 8-15 at +(16 - left_off)
        t = np.arange(ntiles)[:, None]
        r = np.arange(16)[None, :]
        left = decode_word(arr[(base_word + t * 32 + left_off + r).ravel()], fmt).reshape(ntiles, 16, 8)
        right = decode_word(arr[(base_word + t * 32 + (16 - left_off) + r).ravel()], fmt).reshape(ntiles, 16, 8)
        got = np.concatenate([left, right], axis=2)
        return got, ref

    if machine in ("lastmisn", "gondo"):
        g, ref = tile16(BASE["bg"] // 4, "k4", 4096, mame_gfx(setname, "tiles1", "tiles"))
        if not np.array_equal(g, ref): bad.append("bg")
        g, ref = tile16(BASE["spr"] // 4, "k4", 4096, mame_gfx(setname, "sprites", "tiles"))
        if not np.array_equal(g, ref): bad.append("spr")
        c = np.arange(1024)[:, None] * 8 + np.arange(8)[None, :]
        g = decode_word(arr[BASE["fix"] // 4 + c.ravel()], "p3").reshape(1024, 8, 8)
        if not np.array_equal(g, mame_gfx(setname, "char", "chars_3bpp")): bad.append("fix")
    else:
        for k in range(4):
            g, ref = tile16(BASE["bg"] // 4 + k * 0x2000, "srt", 256,
                            mame_gfx(setname, "tiles1", "sr_tiles", 0x10000 * k), left_off=0)
            if not np.array_equal(g, ref): bad.append(f"bg{k}")
        g, ref = tile16(BASE["spr"] // 4, "p3", 2048, mame_gfx(setname, "sprites", "sr_sprites"))
        if not np.array_equal(g, ref): bad.append("spr")
        c = np.arange(1024)[:, None] * 8 + np.arange(8)[None, :]
        g = decode_word(arr[BASE["fix"] // 4 + c.ravel()], "src").reshape(1024, 8, 8)
        if not np.array_equal(g, mame_gfx(setname, "char", "chars_16k")): bad.append("fix")
    return bad


def main(argv):
    do_check = "--check" in argv
    sets = [a for a in argv if not a.startswith("--")]
    if not sets:
        sets = sorted(p.name for p in REGIONS.iterdir() if (p / "manifest.json").exists())
    rc = 0
    for s in sets:
        machine, g = build(s)
        msg = f"{s}: gfx.bin {len(g)} bytes ({machine})"
        if do_check:
            bad = check(s, machine, g)
            msg += ", decode check " + ("OK" if not bad else "FAIL " + ",".join(bad))
            rc |= bool(bad)
        print(msg)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
