#!/usr/bin/env python3
"""Summarise oracle write logs and per-frame video use for the M0 findings.

For each run directory (sim/mame/out/<run>):
  - register writes (scroll, control, bank, flip, sprite buffer, MCU latch,
    sound latch, interrupt control, ROM-space writes): beam lines, how many
    land in the visible area (lines 8-247), visible-area writes that change
    a scroll value MAME only uses at vblank
  - interrupt entries per frame (main NMI/IRQ/FIRQ, sub IRQ/FIRQ)
  - per-class RAM write timing (palette, sprite, tile RAM): share of writes
    in the visible area
  - per dumped frame (spr_buf.bin = the list MAME drew): sprites drawn,
    sprites crossing one visible line

Usage: tools/analyze_writes.py <run_dir> [<run_dir> ...]
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

VIS_Y0, VIS_Y1 = 8, 248
REGS = ("scrollx", "scrolly", "scroll", "control", "bank", "flip", "spr_buffer", "mcu_hi", "mcu_lo",
        "soundlatch", "irq_sub_off", "irq_main_off", "firq_off", "irq_main_on", "irq_sub_on",
        "w1803", "romw")
SCROLL_CLASSES = ("scrollx", "scrolly", "scroll", "control")


def karnov_lines(buf):
    w = np.frombuffer(buf, dtype=">u2").astype(int)
    per = np.zeros(272, dtype=int)
    n = 0
    for offs in range(0, 0x400, 4):
        d0, d1 = w[offs], w[offs + 1]
        if not (d0 >> 15) & 1 or not d1 & 1:
            continue
        n += 1
        extra = (d0 >> 11) & 1
        y = d0 & 0x1ff
        if extra:
            y += 16
        y = 256 - ((y + 16) & 0x1ff)
        h = 32 if extra else 16
        for ln in range(max(y, 0), min(y + h, 272)):
            per[ln] += 1
    return n, per[VIS_Y0:VIS_Y1]


def sr_lines(buf):
    per = np.zeros(272, dtype=int)
    n = 0
    for offs in range(0, 0x200, 4):
        b0, b1, b3 = buf[offs], buf[offs + 1], buf[offs + 3]
        code = b3 + ((b1 & 0xe0) << 3)
        if not code or b0 == 0xf8:
            continue
        n += 1
        h = 32 if b1 & 0x10 else 16
        for ln in range(b0, min(b0 + h, 272)):
            per[ln] += 1
    return n, per[VIS_Y0:VIS_Y1]


def effective_scroll(wr, machine):
    """Replay register writes in order; count visible-area writes that change
    the scroll value or the flip state the renderer uses (bank-only changes
    of a shared register are not counted)."""
    st = dict(xm=0, xl=0, ym=0, yl=0, flip=0)
    changes = Counter()
    frames = defaultdict(set)
    for w in wr:
        c, a, d = w["class"], int(w["addr"], 16), int(w["data"], 16)
        old = (st["xm"] << 8 | st["xl"], st["ym"] << 8 | st["yl"], st["flip"])
        if machine == "lastmisn":
            if c == "control":
                st["xm"], st["ym"] = (d >> 5) & 1, (d >> 6) & 1
            elif c == "scrollx":
                st["xl"] = d
            elif c == "scrolly":
                st["yl"] = d
            elif c == "flip":
                st["flip"] = d & 1
        elif machine == "gondo":
            if c == "scroll":
                o = a - 0x3818
                if o == 0x0:
                    st["xl"] = d
                elif o == 0x8:
                    st["yl"] = d
                elif o == 0x10:
                    st["xm"], st["ym"] = d & 1, (d >> 1) & 1
            elif c == "bank":
                st["flip"] = (d >> 3) & 1
        else:
            if c == "control" and a == 0x1805:
                st["xm"] = d & 0xf
            elif c == "control" and a == 0x1806:
                st["xl"] = d
            elif c == "flip":
                st["flip"] = d & 1
        new = (st["xm"] << 8 | st["xl"], st["ym"] << 8 | st["yl"], st["flip"])
        if w["visible"] == "1" and new != old:
            for name, i in (("scroll_x", 0), ("scroll_y", 1), ("flip", 2)):
                if new[i] != old[i]:
                    changes[name] += 1
                    frames[name].add(int(w["scan_frame"]))
    return changes, {k: len(v) for k, v in frames.items()}


def analyze(run):
    out = []
    p = lambda s="": out.append(s)
    p(f"### {run.name}")
    summ = (run / "summary.txt").read_text().splitlines()
    p("  " + summ[0] + "; " + summ[1])

    wr = list(csv.DictReader(open(run / "writes.csv")))
    for cls in REGS:
        n = [w for w in wr if w["class"] == cls]
        if not n:
            continue
        vis = [w for w in n if w["visible"] == "1"]
        lines = Counter(int(w["line"]) for w in n).most_common(4)
        cpus = Counter(w["cpu"] for w in n)
        vals = Counter(w["data"] for w in n).most_common(4)
        p(f"  {cls}: {len(n)} writes ({dict(cpus)}), visible {len(vis)}, top lines {lines}, values {vals}")
    last = {}
    changed = Counter()
    vis_frames = defaultdict(set)
    for w in wr:
        if w["class"] not in SCROLL_CLASSES:
            continue
        key = (w["class"], w["addr"])
        val = int(w["data"], 16)
        if w["visible"] == "1" and key in last and last[key] != val:
            changed[w["class"]] += 1
            vis_frames[w["class"]].add(int(w["scan_frame"]))
        last[key] = val
    machine = json.loads(next((run / "frames").iterdir()).joinpath("state.json").read_text())["machine"]
    ch, chf = effective_scroll(wr, "srdarwin" if machine.startswith("srdarwin") else machine)
    p(f"  visible-area writes that change the effective scroll or flip: {dict(ch) or 'none'}; frames {chf}")
    p(f"  visible-area writes that change a scroll/control register byte: {dict(changed) or 'none'}"
      + (f"; frames {[(k, len(v)) for k, v in vis_frames.items()]}" if vis_frames else ""))
    bufw = [w for w in wr if w["class"] in ("spr_buffer",) or (w["class"] == "scroll" and w["addr"] == "3828")
            or (w["class"] == "bank")]
    if bufw:
        p(f"  sprite-buffer / bank write lines: {Counter(int(w['line']) for w in bufw).most_common(5)}")

    fr = list(csv.DictReader(open(run / "frames.csv")))
    for k in ("main_nmi", "main_irq", "main_firq", "sub_irq", "sub_firq"):
        c = Counter(int(r[k]) for r in fr)
        if set(c) != {0}:
            p(f"  {k} per frame {c.most_common(6)}")
    sch = sum(int(r["sprbuf_changed"]) for r in fr)
    p(f"  frames whose sprite buffer changed since the previous notifier: {sch}/{len(fr)}; "
      f"max sprites listed {max(int(r['sprites']) for r in fr)}")

    hs = defaultdict(lambda: [0, 0])
    for r in csv.DictReader(open(run / "heavy_summary.csv")):
        hs[r["class"]][0] += int(r["count"])
        hs[r["class"]][1] += int(r["visible_count"])
    visf = defaultdict(set)
    for r in csv.DictReader(open(run / "heavy_summary.csv")):
        if int(r["visible_count"]) > 0:
            visf[r["class"]].add(int(r["frame"]) + 1)
    p(f"  frames with visible-area RAM writes: { {k: len(v) for k, v in sorted(visf.items())} } of {len(fr)}")
    p("  RAM writes (total / in visible area): " +
      ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(hs.items())))

    frames = sorted(d for d in (run / "frames").iterdir() if d.is_dir())
    mx = mxl = 0
    for fd in frames:
        st = json.loads((fd / "state.json").read_text())
        buf = (fd / "spr_buf.bin").read_bytes()
        n, per = (sr_lines(buf) if st["machine"].startswith("srdarwin") else karnov_lines(buf))
        mx = max(mx, n)
        mxl = max(mxl, int(per.max()))
    p(f"  dumped frames {len(frames)}: max sprites drawn {mx}, max sprites crossing one visible line {mxl}")
    return "\n".join(out)


def main(argv):
    for r in argv:
        print(analyze(Path(r)))
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
