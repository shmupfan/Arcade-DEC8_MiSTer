#!/usr/bin/env python3
"""M3: the 6502's RAM (0000-05FF) in the core against MAME at every dump frame.

Core: build/m3/<run>/NNNNNN.snd (m2/tb_sys.cpp at vblank N). MAME:
mame/out/m3_<run>/frames/NNNNNN/snd.bin (d8_oracle.lua SNDLOG=1 at the
frame-N notifier, the same instant). The 6502 stack page (0100-01FF) holds
interrupted context and is reported separately: below the stack pointer it
is dead, above it the frames of whatever the vblank interrupted.
A byte that differs on three consecutive dumps is persistent.

Usage: compare_sndram.py <run> [--upto F]
"""
import argparse
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parent.parent


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--upto", type=int, default=None)
    a = ap.parse_args(argv)
    core = SIM / "build" / "m3" / a.run
    mame = SIM / "mame" / "out" / f"m3_{a.run}" / "frames"
    frames = sorted(int(p.stem) for p in core.glob("*.snd"))
    if a.upto:
        frames = [f for f in frames if f <= a.upto]
    hist = {}
    rows = []
    for f in frames:
        mp = mame / f"{f:06d}" / "snd.bin"
        if not mp.exists():
            continue
        c, m = (core / f"{f:06d}.snd").read_bytes(), mp.read_bytes()
        diff = [i for i in range(0x600) if c[i] != m[i]]
        data = [i for i in diff if not (0x100 <= i < 0x200)]
        stack = [i for i in diff if 0x100 <= i < 0x200]
        rows.append((f, data, stack))
        for i in data:
            hist.setdefault(i, []).append(f)
    persistent = set()
    fl = [r[0] for r in rows]
    for i, fs in hist.items():
        s = set(fs)
        for k in range(len(fl) - 2):
            if fl[k] in s and fl[k + 1] in s and fl[k + 2] in s:
                persistent.add(i)
    nd = sum(1 for r in rows if r[1])
    ns = sum(1 for r in rows if r[2])
    print(f"{a.run}: {len(rows)} dumps; data bytes differ on {nd}, stack page on {ns}; "
          f"persistent data bytes: {sorted(hex(i) for i in persistent) or 'none'}")
    for f, d, s in rows:
        if d:
            print(f"  frame {f}: data {[hex(i) for i in d[:12]]}{' ...' if len(d) > 12 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
