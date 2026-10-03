#!/usr/bin/env python3
"""M1 synthetic scenes for the d8_video RTL, checked against d8_render.py.

Writes <out>/<machine>_flip<F>/frames/NNNNNN/ dirs in the oracle dump format
(state.json + RAM images), one scene set per machine and flip setting so
each harness process keeps one machine. Graphics come from the real ROM
regions of lastmisn, gondo and srdarwin. Palette RAM is fully random and
marked written (no palette_written.bin), so every pixel is checked.

Scroll values stay within what the hardware can latch (spec 4: lastmisn and
gondo keep one bit in m_scroll[0] and m_scroll[2], srdarwin four bits in
m_scroll[0] and no y scroll).

Scenes (per machine x flip):
  random    random palette, tile RAMs, scroll and a dense sprite list
            (random enable/extra/flip/colour/code/x/y; srdarwin random bytes
            with some code-0 and y-0xf8 entries)
  overlap   stacks of sprites on the same spot (the highest-numbered entry
            must win, with its behind flag)
  priority  gondo colour bit 3 / srdarwin colour 0 sprites over bg tiles of
            every colour, pens 0-15
  wrap      sprites straddling x 0/255 and y 0/255 at every 9-bit position
            band (Karnov: x, y 0-511; srdarwin: bytes 0-255)
  ends      tile, char and sprite codes at the region ends (bg 0xfff,
            fix 0x3ff-0xfff (wrapping at 1,024), Karnov 0xffe/0xfff with
            extra, srdarwin 0x7ff with double height: code + 1 wraps)
  scroll    every scroll at 0, 0xff, 0x100, 0x1ff and random
  load      many sprites crossing one line (Karnov 32 and 64, srdarwin 32
            and 64, double-height mixed in); the probe beyond is capacity.py
Usage: make_scenes.py <outdir> [--seed N] [--krnflip]
  --krnflip: Karnov machines only, flipped scenes carry krn_flip = 1 (the
             model then flips the sprites as the KRN_FLIP=1 RTL build does)
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np

SETS = {"lastmisn": "lastmisn", "gondo": "gondo", "srdarwin": "srdarwin"}


class Scene:
    def __init__(self, machine, flip, rng, krnflip=False):
        self.machine, self.flip, self.rng = machine, flip, rng
        self.krnf = krnflip and flip and machine != "srdarwin"
        npal = 144 if machine == "srdarwin" else 1024
        self.pal = rng.integers(0, 256, npal, dtype=np.int64)
        self.palx = rng.integers(0, 256, npal, dtype=np.int64)
        self.fix = rng.integers(0, 256, 2048, dtype=np.int64)
        self.bg = rng.integers(0, 256, 2048, dtype=np.int64)
        if machine == "srdarwin":
            self.spr = np.zeros(512, dtype=np.int64)
            self.spr[0::4] = 0xF8                      # all off
            self.scroll = [int(rng.integers(0, 16)), int(rng.integers(0, 256)), 0, 0]
        else:
            self.spr = np.zeros(2048, dtype=np.int64)
            self.scroll = [int(rng.integers(0, 2)), int(rng.integers(0, 256)),
                           int(rng.integers(0, 2)), int(rng.integers(0, 256))]

    # Karnov entry k: words d0..d3 (big-endian in the buffer)
    def krn(self, k, en, extra, y, fy, fx, x, colour, code):
        d0 = (0x8000 if en else 0) | (0x0800 if extra else 0) | (y & 0x1FF)
        d1 = 1 | (fy << 1) | (fx << 2)
        d2 = x & 0x1FF
        d3 = ((colour & 15) << 12) | (code & 0xFFF)
        for i, d in enumerate((d0, d1, d2, d3)):
            self.spr[8 * k + 2 * i] = d >> 8
            self.spr[8 * k + 2 * i + 1] = d & 0xFF

    # srdarwin entry k: bytes b0 (y), b1 (colour/flip/double/code hi), b2 (x), b3 (code lo)
    def srs(self, k, y, colour, fx, multi, code, x):
        b1 = (colour & 3) | ((colour & 4) << 1) | (fx << 2) | (multi << 4) | (((code >> 8) & 7) << 5)
        self.spr[4 * k:4 * k + 4] = [y & 0xFF, b1, x & 0xFF, code & 0xFF]

    def write(self, d, setname, frame):
        fd = d / "frames" / f"{frame:06d}"
        fd.mkdir(parents=True, exist_ok=True)
        st = {"set": setname, "machine": self.machine, "frame": frame, "width": 256, "height": 240,
              "vis_min_y": 8, "visarea": [0, 255, 8, 247], "htotal": 384, "vtotal": 272,
              "scroll": self.scroll, "flip_x": 1 if self.flip else 0, "flip_y": 1 if self.flip else 0,
              "krn_flip": 1 if self.krnf else (-1 if self.machine == "srdarwin" else 0),
              "bank_data": -1, "sprites": 0}
        (fd / "state.json").write_text(json.dumps(st))
        (fd / "palette.bin").write_bytes(bytes(self.pal.astype(np.uint8)))
        (fd / "palette_ext.bin").write_bytes(bytes(self.palx.astype(np.uint8)))
        (fd / "fixram.bin").write_bytes(bytes(self.fix.astype(np.uint8)))
        (fd / "bgram.bin").write_bytes(bytes(self.bg.astype(np.uint8)))
        (fd / "spr_buf.bin").write_bytes(bytes(self.spr.astype(np.uint8)))
        (fd / "spr_live.bin").write_bytes(bytes(self.spr.astype(np.uint8)))


def rb(rng, p=0.5):
    return int(rng.random() < p)


def scenes(machine, flip, rng, krnflip):
    sr = machine == "srdarwin"
    out = []

    def new():
        return Scene(machine, flip, rng, krnflip)

    # random
    for _ in range(10):
        s = new()
        if sr:
            for k in range(128):
                code = int(rng.integers(0, 2048)) if rng.random() > 0.1 else 0
                y = int(rng.integers(0, 256)) if rng.random() > 0.1 else 0xF8
                s.srs(k, y, int(rng.integers(0, 8)), rb(rng), rb(rng), code, int(rng.integers(0, 256)))
        else:
            for k in range(256):
                s.krn(k, rng.random() < 0.35, rb(rng, 0.3), int(rng.integers(0, 512)), rb(rng), rb(rng),
                      int(rng.integers(0, 512)), int(rng.integers(0, 16)), int(rng.integers(0, 4096)))
                if rng.random() < 0.05:            # word 1 bit 0 clear: skipped (krn:58)
                    s.spr[8 * k + 3] &= 0xFE
        out.append(("random", s))
    # overlap: stacks on one spot, the highest entry must win
    for _ in range(3):
        s = new()
        for k in range(48):
            if sr:
                s.srs(k, 100 + (k % 3), int(rng.integers(0, 8)), rb(rng), rb(rng),
                      int(rng.integers(1, 2048)), 120 + (k % 5))
            else:
                s.krn(k, True, rb(rng, 0.3), 140 + (k % 3), rb(rng), rb(rng), 120 + (k % 5),
                      int(rng.integers(0, 16)), int(rng.integers(0, 4096)))
        out.append(("overlap", s))
    # priority: behind-colour sprites over every bg colour
    s = new()
    if sr:
        s.bg[0::2] = (np.arange(1024) % 4) << 4 | (s.bg[0::2] & 0x03)      # group = colour bits 12-13
        for k in range(100):
            s.srs(k, 16 + (k // 10) * 22, (k % 2) * int(rng.integers(0, 8)), rb(rng), 0,
                  int(rng.integers(1, 2048)), 10 + (k % 10) * 24)
    else:
        for k in range(200):
            s.krn(k, True, 0, (k // 14) * 17, rb(rng), rb(rng), (k % 14) * 18,
                  8 + (k % 8) if k % 2 else (k % 8), int(rng.integers(0, 4096)))
    out.append(("priority", s))
    # wrap: positions across every band
    for band in range(4):
        s = new()
        for k in range(64):
            if sr:
                s.srs(k, (band * 64 + k * 4 + 250) & 0xFF, int(rng.integers(0, 8)), rb(rng), rb(rng),
                      int(rng.integers(1, 2048)), (band * 64 + k * 4 + 240) & 0xFF)
            else:
                s.krn(k, True, rb(rng), (band * 128 + k * 8 + 230) & 0x1FF, rb(rng), rb(rng),
                      (band * 128 + k * 8 + 220) & 0x1FF, int(rng.integers(0, 16)), int(rng.integers(0, 4096)))
        out.append(("wrap", s))
    # region ends
    s = new()
    s.bg[0::2] = (s.bg[0::2] & 0xF0) | 0x0F
    s.bg[1::2] = 0xFF - (np.arange(1024) % 3)
    if sr:
        s.bg[0::2] = (s.bg[0::2] & 0x30) | 0x03
        s.fix[:] = 0xFF - (np.arange(2048) % 7)
        for k in range(40):
            s.srs(k, 20 + 5 * k, int(rng.integers(0, 8)), rb(rng), 1, 0x7FF - (k % 2), 6 * k)
    else:
        s.fix[0::2] = (s.fix[0::2] & 0xF0) | (0x0F - (np.arange(1024) % 13))
        s.fix[1::2] = 0xFF
        for k in range(40):
            s.krn(k, True, k % 2, 20 + 5 * k, rb(rng), rb(rng), 6 * k, int(rng.integers(0, 16)), 0xFFF - (k % 2))
    out.append(("ends", s))
    # scroll extremes
    for v in (0x000, 0x0FF, 0x100, 0x1FF, -1):
        s = new()
        if v < 0:
            v = int(rng.integers(0, 0x200))
        if sr:
            s.scroll = [(v >> 8) | (int(rng.integers(0, 8)) << 1), v & 0xFF, 0, 0]
        else:
            s.scroll = [v >> 8, v & 0xFF, (v >> 8) ^ 1, (v * 7) & 0xFF]
        out.append(("scroll", s))
    # line load
    for count in (32, 64):
        s = new()
        for k in range(count):
            if sr:
                s.srs(k, 120, int(rng.integers(0, 8)), rb(rng), k % 4 == 0, int(rng.integers(1, 2048)),
                      (k * 7) & 0xFF)
            else:
                s.krn(k, True, k % 4 == 0, 120, rb(rng), rb(rng), (k * 7) & 0x1FF, int(rng.integers(0, 16)),
                      int(rng.integers(0, 4096)))
        out.append(("load", s))
    return out


def main(argv):
    out = Path(argv[0])
    seed = int(argv[argv.index("--seed") + 1]) if "--seed" in argv else 8
    krnflip = "--krnflip" in argv
    if out.exists():
        shutil.rmtree(out)
    rng = np.random.default_rng(seed)
    n = 0
    for machine, setname in SETS.items():
        if krnflip and machine == "srdarwin":
            continue
        for flip in (0, 1):
            d = out / f"{machine}_flip{flip}"
            kinds = {}
            for i, (kind, s) in enumerate(scenes(machine, flip, rng, krnflip)):
                s.write(d, setname, i + 1)
                kinds[f"{i + 1:06d}"] = kind
                n += 1
            (d / "kinds.json").write_text(json.dumps(kinds))
    print(f"wrote {n} scenes in {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
