#!/usr/bin/env python3
"""M2 comparison of a core boot (build/m2/<run>/) with MAME (mame/out/<run>/
and the MAINRAM rerun mame/out/m2ram_<run>/), after the 1945k III and Tecmo
16 M2 compare.py.

Checks, up to the last frame both sides cover:
  io     every logged write (writes.csv classes) per CPU, in order: address
         and value must be equal; the beam position difference of each pair
         (pixels, 384 per line) is summarised
  ints   per frame, the interrupt vector reads (frames.csv main_nmi,
         main_irq, main_firq, sub_irq, sub_firq) must be equal
  ram    at every dump frame F (vblank F): palette, palette ext, fix RAM,
         bg RAM, live sprite RAM, sprite buffer (M0 dump) and work RAM and
         MCU internal RAM (MAINRAM rerun) byte for byte; the two MAME runs'
         video RAM dumps must be identical (same execution)
  image  MAME's snapshot at dump frame F against our displayed frame F-1:
         exact; or "live": every differing pixel on a display line at or
         above the last visible-scan video write of that displayed frame + 2
         (MAME renders the frame once at vblank, the core races the beam,
         PLAN 5.2), the rest exact; else unexplained. Pixels of palette
         entries the game never wrote are excluded (MAME's power-on pens,
         m0_findings 1).
Prints a summary and writes build/m2/<run>/compare.txt.

Usage: m2/compare.py <run> [...] [--max N]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
OUT = SIM / "mame" / "out"
BUILD = SIM / "build" / "m2"
HTOT, VTOT, VBL = 384, 272, 248


def pos(line, hpos):
    return ((line - VBL) % VTOT) * HTOT + hpos


def read_mame_io(run):
    rows = {"main": [], "sub": []}
    with open(OUT / run / "writes.csv") as f:
        next(f)
        for ln in f:
            p = ln.rstrip("\n").split(",")
            rows[p[5]].append((int(p[0]), int(p[1]), int(p[2]), int(p[7], 16), int(p[8], 16)))
    return rows


def read_core_io(d):
    rows = {"main": [], "sub": []}
    with open(d / "io.txt") as f:
        for ln in f:
            p = ln.split()
            if len(p) != 6 or p[3] not in rows:
                continue   # a line still being written by a running boot
            rows[p[3]].append((int(p[0]), int(p[1]), int(p[2]), int(p[4], 16), int(p[5], 16)))
    return rows


def cmp_io(mame, core, last):
    res = {}
    for c in ("main", "sub"):
        m = [r for r in mame[c] if r[0] < last]
        k = [r for r in core[c] if r[0] < last]
        n = min(len(m), len(k))
        first = None
        deltas = []
        moves = []
        moved_at = set()
        for i in range(n):
            if m[i][3:] != k[i][3:]:
                # one write moved across others in the same frame (an
                # interrupt taken one instruction earlier or later, m2_findings
                # 3.9): same writes, same values, order differs locally
                mv = None
                for j in range(min(i + 16, n - 1), i, -1):   # longest move first
                    if (k[i][3:] == m[j][3:] and k[i][0] == m[j][0] and
                            [x[3:] for x in m[i:j]] == [x[3:] for x in k[i + 1:j + 1]]):
                        mv = ("core_earlier", j)
                        break
                    if (m[i][3:] == k[j][3:] and m[i][0] == k[j][0] and
                            [x[3:] for x in k[i:j]] == [x[3:] for x in m[i + 1:j + 1]]):
                        mv = ("core_later", j)
                        break
                if mv is None:
                    first = i
                    break
                kind, j = mv
                moves.append({"index": i, "kind": kind, "by": j - i, "frame": m[i][0],
                              "write": [hex(x) for x in (k[i] if kind == "core_earlier" else m[i])[3:]]})
                moved_at.add(j)
                if kind == "core_earlier":
                    k = k[:i] + k[i + 1:j + 1] + [k[i]] + k[j + 1:]
                else:
                    m = m[:i] + m[i + 1:j + 1] + [m[i]] + m[j + 1:]
            if i in moved_at:
                continue
            dm = m[i][0] * VTOT * HTOT + pos(m[i][1], m[i][2])
            dk = k[i][0] * VTOT * HTOT + pos(k[i][1], k[i][2])
            deltas.append(dk - dm)
        if first is None and len(m) != len(k):
            first = n
        r = {"mame": len(m), "core": len(k), "equal": first is None, "moved": moves,
             "first_diff": None if first is None else {
                 "index": first, "mame": m[first] if first < len(m) else None,
                 "core": k[first] if first < len(k) else None}}
        if deltas:
            a = np.array(deltas)
            r["delta_px"] = {"min": int(a.min()), "max": int(a.max()), "median": int(np.median(a))}
            r["delta_first_frame_over_100px"] = next((m[i][0] for i in range(len(deltas)) if abs(deltas[i]) > 100), None)
        res[c] = r
    return res


def cmp_ints(run, d, last):
    mame = {}
    with open(OUT / run / "frames.csv") as f:
        hdr = next(f).strip().split(",")
        ix = [hdr.index(k) for k in ("main_nmi", "main_irq", "main_firq", "sub_irq", "sub_firq")]
        for ln in f:
            p = ln.strip().split(",")
            mame[int(p[0])] = tuple(int(p[i]) for i in ix)
    core = {}
    with open(d / "ints.txt") as f:
        for ln in f:
            q = ln.split()
            if len(q) != 6:
                continue
            p = list(map(int, q))
            core[p[0]] = tuple(p[1:6])
    frames = [fr for fr in sorted(mame) if fr in core and fr < last]
    bad = [fr for fr in frames if mame[fr] != core[fr]]
    return {"frames": len(frames), "differ": len(bad), "first": bad[:5],
            "first_values": [(fr, mame[fr], core[fr]) for fr in bad[:3]]}


def rb(p, n=None):
    b = Path(p).read_bytes()
    return b if n is None else b[:n]


def cmp_ram(run, d, frames, machine):
    files = [("palette.bin", "pal", 1024), ("palette_ext.bin", "palx", 1024), ("fixram.bin", "fix", 2048),
             ("bgram.bin", "bg", 2048), ("spr_live.bin", "sprl", 2048), ("spr_buf.bin", "sprb", 2048)]
    sr = machine in ("srdarwin", "srdarwinb")
    res = {k: {"frames": 0, "bad": 0, "first": None} for _, k, _ in files}
    res.update({"ram": {"frames": 0, "bad": 0, "first": None, "bytes_max": 0},
                "mcu": {"frames": 0, "bad": 0, "first": None, "bytes_max": 0, "tick": 0, "persistent": 0},
                "oracle_runs_same": {"frames": 0, "bad": 0}})
    for fr in frames:
        md = OUT / run / "frames" / f"{fr:06d}"
        rd = OUT / f"m2ram_{run}" / "frames" / f"{fr:06d}"
        base = d / f"{fr:06d}"
        if not (md.exists() and Path(str(base) + ".ram").exists()):
            continue
        for mf, k, n in files:
            if sr and k == "pal":
                n = 144
            if sr and k == "palx":
                n = 144
            if sr and k in ("sprl", "sprb"):
                n = 512
            if sr and k == "bg":
                n = 1024
            mb = rb(md / mf, n)
            cb = rb(Path(str(base) + "." + k), n)
            res[k]["frames"] += 1
            if mb != cb:
                res[k]["bad"] += 1
                res[k].setdefault("bad_frames", []).append(fr)
                if res[k]["first"] is None:
                    diffs = [i for i in range(n) if mb[i] != cb[i]]
                    res[k]["first"] = {"frame": fr, "bytes": len(diffs), "at": diffs[:6]}
        if rd.exists():
            res["oracle_runs_same"]["frames"] += 1
            if any(rb(md / mf) != rb(rd / mf) for mf, _, _ in files):
                res["oracle_runs_same"]["bad"] += 1
            for k, mf, ext in (("ram", "ram.bin", ".ram"), ("mcu", "mcuram.bin", ".mcu")):
                if not (rd / mf).exists():
                    continue
                mb, cb = rb(rd / mf), rb(Path(str(base) + ext))
                res[k]["frames"] += 1
                if mb != cb:
                    diffs = [i for i in range(len(mb)) if mb[i] != cb[i]]
                    res[k]["bad"] += 1
                    res[k]["bytes_max"] = max(res[k]["bytes_max"], len(diffs))
                    if res[k]["first"] is None:
                        res[k]["first"] = {"frame": fr, "bytes": len(diffs), "at": [hex(x) for x in diffs[:8]]}
                    if k == "ram":
                        classify_ram(res, fr, diffs, json.loads((rd / "cpu.json").read_text()), machine,
                                     json.loads((md / "state.json").read_text())["set"])
                    else:
                        # srdarwin MCU clock (m2_findings 3.8): timer 0 tick
                        # counter 0x39 (with 0x3a/0x3b on a wrap) and tick flag
                        # bit 0x26 (byte 0x24 bit 6), the core one tick behind
                        tick = (machine == "srdarwin" and set(diffs) <= {0x24, 0x39, 0x3a, 0x3b} and
                                (0x24 not in diffs or (mb[0x24] ^ cb[0x24]) == 0x40) and
                                (0x39 not in diffs or (cb[0x39] - mb[0x39]) % 256 in (1, 0xed)))
                        res[k]["tick" if tick else "persistent"] = res[k].get("tick" if tick else "persistent", 0) + 1
    # video RAM files: a dump that differs while the dumps before and after
    # are equal is transient (boot memory tests writing at the vblank instant)
    order = list(frames)
    pos_of = {fr: i for i, fr in enumerate(order)}
    for _, k, _ in files:
        bf = set(res[k].pop("bad_frames", []))
        pers = [fr for fr in sorted(bf) if not (0 < pos_of[fr] < len(order) - 1 and
                order[pos_of[fr] - 1] not in bf and order[pos_of[fr] + 1] not in bf)]
        res[k]["transient"] = len(bf) - len(pers)
        res[k]["persistent"] = len(pers)
        res[k]["persistent_frames"] = pers[:10]
    # "other" work RAM bytes: transient if the byte is equal at the dump
    # before and the dump after (a write landing either side of the vblank
    # instant), persistent otherwise
    c = res.get("ram_class")
    if c:
        order = [fr for fr in frames]
        pos_of = {fr: i for i, fr in enumerate(order)}
        trans, pers = 0, {}
        for a, frs in c.get("other_addrs", {}).items():
            s_frs = set(frs)
            for fr in frs:
                i = pos_of.get(fr)
                isolated = (i is not None and 0 < i < len(order) - 1 and
                            order[i - 1] not in s_frs and order[i + 1] not in s_frs)
                if isolated:
                    trans += 1
                else:
                    pers.setdefault(a, []).append(fr)
        c["other_transient"] = trans
        c["other_persistent"] = sum(len(v) for v in pers.values())
        c["persistent_addrs"] = {a: (v[:6] + (["..."] if len(v) > 6 else []), len(v)) for a, v in pers.items()}
        c["other_addrs"] = {a: (v[:6] + (["..."] if len(v) > 6 else []), len(v)) for a, v in c["other_addrs"].items()}
    return res


def ram_cpu_addr(idx, machine):
    """d8_sys work RAM index -> CPU address (oracle MAINRAM layout)."""
    if machine == "lastmisn":
        return idx if idx < 0x1000 else 0x3000 + (idx - 0x1000)
    if machine == "gondo":
        return idx
    return idx if idx < 0x600 else 0x1000 + (idx - 0x1800)


STACK_SPAN = 0x40   # bytes below / above S treated as the stack's dead / live part


_IDLE = {}


def idle_counters(setname):
    """Direct-page bytes incremented by an idle loop "INC <xx ; BRA -4"
    (0C xx 20 FC) anywhere in the main CPU's ROM (fixed and banked): the
    count of spare CPU cycles between interrupts, which moves with any
    cycle-level timing difference (m2_findings 5). DP is 0 in these
    programs at those loops (checked in the traces)."""
    if setname not in _IDLE:
        sd = (SIM / "build" / "regions" / setname / "sdram.bin").read_bytes()
        rom = sd[0x8000:0x10000] + sd[0x10000:0x50000]
        found = set()
        for i in range(len(rom) - 3):
            if rom[i] == 0x0C and rom[i + 2] == 0x20 and rom[i + 3] == 0xFC:
                found.add(rom[i + 1])
        _IDLE[setname] = found
    return _IDLE[setname]


def classify_ram(res, fr, diffs, cpu, machine, setname=None):
    """Work RAM differences by kind: dead stack (below a CPU's S at the
    dump, within STACK_SPAN), live stack (S .. S + STACK_SPAN), other. The
    "other" addresses are listed with the frames they differ in."""
    c = res.setdefault("ram_class", {"dead_stack": 0, "live_stack": 0, "other": 0, "other_addrs": {}})
    ss = [cpu[k] for k in ("main_s", "sub_s") if k in cpu and cpu[k] > 0]
    for i in diffs:
        a = ram_cpu_addr(i, machine)
        if setname and a in idle_counters(setname):
            c["idle_counter"] = c.get("idle_counter", 0) + 1
            c.setdefault("idle_addrs", set()).add(hex(a))
        elif any(sv - STACK_SPAN <= a < sv for sv in ss):
            c["dead_stack"] += 1
        elif any(sv <= a < sv + STACK_SPAN for sv in ss):
            c["live_stack"] += 1
        else:
            c["other"] += 1
            c["other_addrs"].setdefault(hex(a), []).append(fr)


def wlog_last_line(path):
    last = -1
    if path.exists():
        for ln in path.read_text().splitlines():
            line = int(ln.split()[0])
            if 8 <= line <= 247:
                last = max(last, line)
    return last


def cmp_images(run, d, frames):
    res = {"frames": 0, "exact": 0, "live": 0, "unexplained": 0, "missing": 0, "list_live": [], "list_bad": []}
    for fr in frames:
        snap = OUT / run / "frames" / f"{fr:06d}" / "snap.png"
        ours = d / f"{fr - 1:06d}.rgbp"
        if not snap.exists() or not ours.exists():
            res["missing"] += 1
            continue
        # ROT270: the snapshot is the native frame rotated, snap = rot90(native, 1)
        # (oracle/compare_frames.py)
        m = np.rot90(np.asarray(Image.open(snap).convert("RGB"), dtype=np.uint8), -1)
        c = np.frombuffer(ours.read_bytes(), dtype=np.uint8).reshape(240, 256, 5)
        pen = c[:, :, 3].astype(np.int32) | (c[:, :, 4].astype(np.int32) << 8)
        written = np.frombuffer(rb(OUT / run / "frames" / f"{fr:06d}" / "palette_written.bin"), dtype=np.uint8)
        valid = written[np.clip(pen, 0, len(written) - 1)] != 0
        diff = np.any(m != c[:, :, :3], axis=2) & valid
        res["frames"] += 1
        if not diff.any():
            res["exact"] += 1
            continue
        rows = np.nonzero(diff.any(axis=1))[0]
        last_w = wlog_last_line(d / f"{fr - 1:06d}.wlog")
        if last_w >= 0 and rows.max() + 8 <= last_w + 2:
            res["live"] += 1
            res["list_live"].append((fr, int(rows.min() + 8), int(rows.max() + 8), last_w))
        else:
            res["unexplained"] += 1
            res["list_bad"].append((fr, int(rows.min() + 8), int(rows.max() + 8), int(diff.sum()), last_w))
    return res


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--max", type=int, default=0, help="compare frames below N only")
    ap.add_argument("--tag", default="", help="core run directory suffix (run_boots.py --tag)")
    a = ap.parse_args(argv)
    ok_all = True
    for run in a.runs:
        d = BUILD / (run + a.tag)
        st = json.loads((next((OUT / run / "frames").iterdir()) / "state.json").read_text())
        machine = st["machine"]
        core_last = sum(1 for _ in open(d / "ints.txt"))
        last = core_last if not a.max else min(core_last, a.max)
        cap = [int(x) for x in (d / "cap.txt").read_text().split()]
        dumps = sorted(int(p.name) for p in (OUT / run / "frames").iterdir() if int(p.name) <= last)
        io = cmp_io(read_mame_io(run), read_core_io(d), last)
        ints = cmp_ints(run, d, last)
        ram = cmp_ram(run, d, dumps, machine)
        img = cmp_images(run, d, [f for f in dumps if f - 1 in cap])
        rep = {"run": run, "machine": machine, "frames": last, "io": io, "ints": ints, "ram": ram,
               "image": {k: v for k, v in img.items() if not k.startswith("list_")},
               "image_live": img["list_live"][:40], "image_unexplained": img["list_bad"][:40]}
        txt = json.dumps(rep, indent=1, default=str)
        (d / "compare.txt").write_text(txt + "\n")
        ok = (io["main"]["equal"] and io["sub"]["equal"] and ints["differ"] == 0 and img["unexplained"] == 0 and
              ram.get("ram_class", {}).get("other_persistent", 0) == 0 and
              all(v.get("persistent", v.get("bad", 0)) == 0 for k, v in ram.items() if k not in ("ram", "ram_class")))
        ok_all &= ok
        print(f"{run}: frames {last} io main {io['main']['mame']}/{io['main']['core']} "
              f"{'eq' if io['main']['equal'] else 'DIFF@' + str(io['main']['first_diff']['index'])} "
              f"moved {len(io['main']['moved'])}+{len(io['sub']['moved'])} "
              f"sub {io['sub']['mame']}/{io['sub']['core']} {'eq' if io['sub']['equal'] else 'DIFF'} | "
              f"ints {ints['differ']}/{ints['frames']} differ | ram bad " +
              " ".join(f"{k}:{v['bad']}/{v['frames']}" for k, v in ram.items() if 'bad' in v) +
              f" | ram classes {ram.get('ram_class', {}).get('dead_stack', 0)} dead / "
              f"{ram.get('ram_class', {}).get('live_stack', 0)} live / {ram.get('ram_class', {}).get('idle_counter', 0)} idle / "
              f"{ram.get('ram_class', {}).get('other_transient', 0)} transient / "
              f"{ram.get('ram_class', {}).get('other_persistent', 0)} persistent"
              f" | mcu tick {ram['mcu']['tick']} other {ram['mcu']['persistent']}"
              f" | img exact {img['exact']} live {img['live']} unexpl {img['unexplained']} of {img['frames']}"
              f" -> {'PASS' if ok else 'CHECK'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
