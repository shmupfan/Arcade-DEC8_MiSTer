#!/usr/bin/env python3
"""M3: compare the core's sound event log (m2/tb_sys.cpp +snd) with MAME's
(d8_oracle.lua SNDLOG=1 sndlog.csv).

Both logs: t,frame,kind,addr,data. Kinds: L main latch write, Y YM2203
write, P OPL write, R 6502 read of the latch or a chip, U other unmapped
access, N / I interrupt vector read (NMI / IRQ entry).

Checks, up to frame --upto (default: the shorter log):
  - the event streams in order (kind, addr, data): first difference
  - timing: the core's time of each event against MAME's, after removing
    the constant offset of the first event (the core's clock starts at
    reset release); max |delta| and its distribution in microseconds
  - per kind counts

Usage: compare_snd.py core.csv mame.csv [--upto F] [--kinds YPLRNIU]
"""
import argparse
import sys


def load(path, upto, kinds):
    ev = []
    with open(path) as f:
        next(f)
        for ln in f:
            parts = ln.rstrip("\n").split(",")
            if len(parts) != 5 or not ln.endswith("\n"):
                break  # a log still being written ends mid-line
            t, fr, k, a, d = parts
            fr = int(fr)
            if upto is not None and fr > upto:
                break
            if k in kinds:
                ev.append((float(t), fr, k, int(a, 16), int(d, 16)))
    return ev


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("core")
    ap.add_argument("mame")
    ap.add_argument("--upto", type=int, default=None)
    ap.add_argument("--kinds", default="YPLRNIU")
    ap.add_argument("--show", type=int, default=8)
    a = ap.parse_args(argv)
    c = load(a.core, a.upto, a.kinds)
    m = load(a.mame, a.upto, a.kinds)
    if a.upto is None:
        last = min(c[-1][1] if c else 0, m[-1][1] if m else 0)
        c = [e for e in c if e[1] <= last]
        m = [e for e in m if e[1] <= last]
        a.upto = last
    counts = {}
    for e in c:
        counts.setdefault(e[2], [0, 0])[0] += 1
    for e in m:
        counts.setdefault(e[2], [0, 0])[1] += 1
    print(f"up to frame {a.upto}: core {len(c)} events, MAME {len(m)}")
    for k in sorted(counts):
        print(f"  {k}: core {counts[k][0]} MAME {counts[k][1]}")
    n = min(len(c), len(m))
    first = None
    for i in range(n):
        if c[i][2:] != m[i][2:]:
            first = i
            break
    if first is None and len(c) != len(m):
        first = n
    off = (c[0][0] - m[0][0]) if n else 0.0
    upto = first if first is not None else n
    deltas = [((c[i][0] - m[i][0]) - off) * 1e6 for i in range(upto)]
    if deltas:
        ad = [abs(x) for x in deltas]
        ad_sorted = sorted(ad)
        p = lambda q: ad_sorted[min(len(ad_sorted) - 1, int(q * len(ad_sorted)))]
        print(f"timing (core - MAME - {off * 1e6:.3f} us) over {len(deltas)} equal events: "
              f"max {max(ad):.3f} us, p50 {p(0.5):.3f}, p99 {p(0.99):.3f}, mean signed {sum(deltas) / len(deltas):+.3f}")
        imax = ad.index(max(ad))
        print(f"  largest at event {imax}: frame {m[imax][1]} {m[imax][2]} {m[imax][3]:x} {m[imax][4]:x}"
              f" core t {c[imax][0]:.9f} MAME t {m[imax][0]:.9f}")
    if first is None:
        print("streams: IDENTICAL")
        return 0
    print(f"streams: first difference at event {first} (frame {m[first][1] if first < len(m) else '-'}):")
    for i in range(max(0, first - 3), min(max(len(c), len(m)), first + a.show)):
        ce = c[i] if i < len(c) else None
        me = m[i] if i < len(m) else None
        fmt = lambda e: f"f{e[1]} {e[2]} {e[3]:04x} {e[4]:02x} t={e[0]:.9f}" if e else "-"
        mark = "  " if (ce and me and ce[2:] == me[2:]) else "! "
        print(f"  {mark}{i}: core {fmt(ce):45s} MAME {fmt(me)}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
