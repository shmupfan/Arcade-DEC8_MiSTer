#!/usr/bin/env python3
"""M4: a board run (d8_board: ioctl download, d8_sdram, SDRAM model) against
the M2 harness run of the same game (d8_sys with C++ ROM models, same RTL),
file by file.

Every capture file (.rgbp .wlog .pal .palx .fix .bg .sprl .sprb .ram .mcu
.snd .regs) is compared byte for byte, and io.txt (every logged CPU write
with its beam position), ints.txt (interrupt vector reads per vblank) and
sndlog.csv (every sound latch, chip and vector access with its time) line by
line. Identical means the board reproduces M2's core exactly, so every M2/M3
result (the comparisons with MAME, m2_findings, m3_findings) holds for the
board.

Usage: compare_m2.py <board run dir> <m2 run dir>
"""
import sys
from pathlib import Path

EXTS = ("rgbp", "wlog", "pal", "palx", "fix", "bg", "sprl", "sprb", "ram", "mcu", "snd", "regs")
STREAMS = ("io.txt", "ints.txt", "sndlog.csv")


def compare(a, b):
    a, b = Path(a), Path(b)
    fa = {f.name for f in a.iterdir() if f.suffix[1:] in EXTS}
    fb = {f.name for f in b.iterdir() if f.suffix[1:] in EXTS}
    common = sorted(fa & fb)
    diff = [f for f in common if (a / f).read_bytes() != (b / f).read_bytes()]
    ok = not diff and fa == fb and common
    print(f"  vs M2: {len(common)} capture files compared, {len(common) - len(diff)} identical"
          + (f", {len(diff)} differ (first {diff[:5]})" if diff else "")
          + (f"; {len(fa ^ fb)} without a counterpart" if fa != fb else ""))
    for s in STREAMS:
        pa, pb = a / s, b / s
        if not (pa.exists() and pb.exists()):
            print(f"  vs M2: {s} missing")
            ok = False
            continue
        la, lb = pa.read_text().split("\n"), pb.read_text().split("\n")
        if la == lb:
            print(f"  vs M2: {s} identical ({len(la) - 1} lines)")
        else:
            ok = False
            n = min(len(la), len(lb))
            first = next((i for i in range(n) if la[i] != lb[i]), n)
            print(f"  vs M2: {s} differs from line {first}: {la[first] if first < len(la) else '-'} / "
                  f"{lb[first] if first < len(lb) else '-'} ({len(la) - 1} / {len(lb) - 1} lines)")
    return bool(ok)


if __name__ == "__main__":
    sys.exit(0 if compare(sys.argv[1], sys.argv[2]) else 1)
