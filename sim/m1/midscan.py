#!/usr/bin/env python3
"""M1 mid-scan replay (after Tecmo 16's): every captured frame whose
visible scan (lines 8-247) contains palette, fix RAM, bg RAM, scroll or
flip writes or a sprite buffer copy, replayed through the RTL with those
writes applied at their beam position, and every difference from MAME
classified.

Input: the M0 frame dumps (sim/mame/out/<run>/frames) and the VISLOG rerun
of the same capture (sim/mame/out/vislog/<run>/vislog.csv and copies/,
written by mame/vislog_runs.py, which checks the rerun executed
identically). A dump is the state at vblank start (line 248), after the
visible scan. The state at the start of the visible scan:
  RAMs       the dump with that frame's visible writes undone, newest first
             (vislog records each byte's value before the write)
  registers  MAME's m_scroll[0..3] and flip before the first visible
             register write (or the dump's, if none)
  sprites    the buffer before the first visible copy and the live sprite
             RAM that copy takes (copies/<n>.buf, .live), or the dump's
The writes the RTL gets: each RAM byte write; each register write as the
change of m_scroll / flip it caused (state before the next register write,
or the dump's for the last); each copy as the live RAM bytes that changed
since the previous copy, then the copy strobe.

Per frame, three images:
  MAME   the snapshot: MAME draws the frame once at vblank, so every
         visible-scan write shows on the whole frame (spec 3)
  INIT   d8_render.py of the state at the start of the visible scan
  LIVE   the RTL (default build) with the writes at (line, hpos): a line
         renderer reads tile RAM, scroll, flip and the sprite buffer for
         line L during line L-1 and the palette while line L is shown
  LATCH  the RTL LATCH build (tile RAM, palette, scroll, flip snapshot at
         line 6; the sprite buffer copies stay live in both builds)
Classes (LIVE):
  exact      LIVE == MAME
  explained  LIVE differs from MAME only on lines up to the last value-
             changing write's line + 1 (+ 2 after a sprite copy, which
             takes up to 2,048 clocks), and equals INIT above the first
             value-changing write's line
  UNEXPLAINED anything else (the gate requires none)
LATCH must equal INIT on every line of every frame without a visible
sprite copy (checked) and above the first copy line otherwise.
Pixels whose palette entry the game never wrote are excluded everywhere
(MAME's power-on pens, m0_findings 1).

Usage: midscan.py <run>... [--jobs N] [--limit N]
Writes build/m1/midscan_<run>.csv and prints a summary per run.
"""
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
sys.path.insert(0, str(SIM / "oracle"))
sys.path.insert(0, str(HERE))
from d8_render import render  # noqa: E402
from replay import BIN, LBIN, REGIONS, TARGET, load_out, make_d8f, written_mask  # noqa: E402

OUT = SIM / "mame" / "out"
FILE_OF = {"pal": "palette.bin", "palx": "palette_ext.bin", "fixram": "fixram.bin", "bgram": "bgram.bin"}
BASES = {
    "lastmisn": {"pal": 0x1000, "palx": 0x1400, "fixram": 0x2000, "bgram": 0x3800},
    "gondo": {"pal": 0x2800, "palx": 0x2C00, "fixram": 0x1800, "bgram": 0x2000},
    "srdarwin": {"pal": 0x2800, "palx": 0x3000, "fixram": 0x0800, "bgram": 0x1400},
}
BASES["srdarwinb"] = BASES["srdarwin"]
SIZES = {"palette.bin": 1024, "palette_ext.bin": 1024, "fixram.bin": 2048, "bgram.bin": 2048}


def read_vislog(run):
    by = {}
    with open(OUT / "vislog" / run / "vislog.csv") as f:
        for r in csv.DictReader(f):
            by.setdefault(int(r["scan_frame"]), []).append(r)
    return by


def plan(fd, st, rows, run):
    """Initial state and the RTL write list for one frame."""
    mach = st["machine"]
    bases = BASES[mach]
    rams = {n: bytearray((fd / n).read_bytes()) for n in FILE_OF.values()}
    eff_lines, copy_lines = [], []
    # RAM writes, undone newest first
    for r in reversed(rows):
        if r["kind"] == "ram":
            b = rams[FILE_OF[r["class"]]]
            i = int(r["addr"], 16) - bases[r["class"]]
            if 0 <= i < len(b):
                b[i] = int(r["old"], 16)
    # register states: before each register write, then the dump's
    regs = [r for r in rows if r["kind"] == "reg"]
    dump_reg = ([int(v) & 0xFF for v in st["scroll"]], 1 if st["flip_x"] else 0)
    before = [([int(r[f"sc{k}"]) for k in range(4)], int(r["flip"])) for r in regs]
    after = before[1:] + [dump_reg]
    st0 = dict(st)
    if regs:
        st0["scroll"], st0["flip_x"] = before[0][0], before[0][1]
        st0["flip_y"] = st0["flip_x"]
    # sprites
    copies = [r for r in rows if r["kind"] == "reg" and r["copy"]]
    override = {n: bytes(b) for n, b in rams.items()}
    cdir = OUT / "vislog" / run / "copies"
    live = None
    if copies:
        k0 = copies[0]["copy"]
        buf0 = (cdir / f"{k0}.buf").read_bytes()
        live = bytearray(((cdir / f"{k0}.live").read_bytes() + bytes(2048))[:2048])
        override["spr_buf.bin"] = buf0
        override["spr_live.bin"] = bytes(live)
    # harness writes in time order
    hw = []
    ri = 0
    for r in rows:
        line, hpos = int(r["line"]), int(r["hpos"])
        if r["kind"] == "ram":
            a = int(r["addr"], 16) - bases[r["class"]]
            d, o = int(r["data"], 16), int(r["old"], 16)
            hw.append((line, hpos, TARGET[r["class"]], a, d))
            if d != o:
                eff_lines.append(line)
        else:
            (sb, fb), (sa, fa) = before[ri], after[ri]
            ri += 1
            for k in range(4):
                if sa[k] != sb[k]:
                    hw.append((line, hpos, TARGET[f"scroll{k}"], 0, sa[k]))
            if fa != fb:
                hw.append((line, hpos, TARGET["flip"], 0, fa))
            if sa != sb or fa != fb:
                eff_lines.append(line)
            if r["copy"]:
                new = ((cdir / f"{r['copy']}.live").read_bytes() + bytes(2048))[:2048]
                oldbuf = (cdir / f"{r['copy']}.buf").read_bytes()
                for a in range(2048):
                    if new[a] != live[a]:
                        hw.append((line, hpos, TARGET["spr"], a, new[a]))
                        live[a] = new[a]
                hw.append((line, hpos, TARGET["copy"], 0, 0))
                nb = len(oldbuf)
                newbuf = new[:nb] if mach.startswith("srdarwin") else new
                if newbuf != oldbuf:
                    eff_lines.append(line)
                    copy_lines.append(line)
    return st0, override, hw, eff_lines, copy_lines


def run_harness(binp, setname, items):
    with tempfile.TemporaryDirectory(prefix="d8ms_") as td:
        td = Path(td)
        lst = []
        for k, (fd, st, override, hw) in enumerate(items):
            inp, outp = td / f"{k}.d8f", td / f"{k}.rgb"
            make_d8f(fd, inp, st=st, override=override, writes=hw)
            lst.append((inp, outp))
        (td / "list.txt").write_text("".join(f"{a} {b}\n" for a, b in lst))
        p = subprocess.run([str(binp), f"+sdram={REGIONS / setname / 'gfx.bin'}", f"+list={td / 'list.txt'}"],
                           capture_output=True, text=True)
        outs = [load_out(o) if o.exists() else (None, None) for _, o in lst]
        return p.returncode, outs, p.stderr[-300:]


def lines_of(mask):
    return sorted({8 + y for y in np.nonzero(mask.any(axis=-1) if mask.ndim == 3 else mask)[0].tolist()})


def classify_batch(run, setname, batch, vl):
    items, meta = [], []
    tmp = Path(tempfile.mkdtemp(prefix="d8init_"))
    try:
        for fd in batch:
            st = json.loads((fd / "state.json").read_text())
            rows = vl[int(fd.name)]
            st0, override, hw, eff, cop = plan(fd, st, rows, run)
            idir = tmp / fd.name
            shutil.copytree(fd, idir)
            for n, b in override.items():
                (idir / n).write_bytes(b)
            (idir / "state.json").write_text(json.dumps(st0))
            items.append((fd, st0, override, hw))
            meta.append((fd, st, idir, rows, eff, cop))
        rc, live, err = run_harness(BIN, setname, items)
        rcl, latch, errl = run_harness(LBIN, setname, items)
        res = []
        for (fd, st, idir, rows, eff, cop), (lv, lvp), (lt, ltp) in zip(meta, live, latch):
            r = {"frame": fd.name, "writes": len(rows), "effective": len(eff),
                 "first_line": min(eff) if eff else -1, "last_line": max(eff) if eff else -1,
                 "copies": len(cop), "classes": "+".join(sorted({w["class"] for w in rows}))}
            if lv is None or lt is None:
                r["class"] = "UNEXPLAINED"
                r["note"] = f"no output rc {rc}/{rcl} {err}{errl}"
                res.append(r)
                continue
            wm = written_mask(fd, 1024)
            mask = wm[lvp] & wm[ltp]
            mame = np.rot90(np.array(Image.open(fd / "snap.png").convert("RGB")), -1)
            init, _ = render(idir)
            d_live = np.any(lv != mame, axis=-1) & mask
            d_init_latch = np.any(lt != init, axis=-1) & mask
            d_latch = np.any(lt != mame, axis=-1) & mask
            ll = lines_of(d_live)
            r["live_lines"] = f"{ll[0]}-{ll[-1]}" if ll else ""
            r["live_px"] = int(d_live.sum())
            r["latch_px"] = int(d_latch.sum())
            if cop:
                c0 = min(cop)
                r["latch_ok"] = int(not d_init_latch[:max(0, c0 - 8)].any())
            else:
                r["latch_ok"] = int(not d_init_latch.any())
            if not d_live.any():
                r["class"] = "exact"
            elif not eff:
                r["class"] = "UNEXPLAINED"
                r["note"] = "no value-changing write but LIVE differs"
            else:
                f0, f1 = min(eff), max(eff)
                slack = 2 if cop else 1
                below = all(y <= f1 + slack for y in ll)
                top_ok = not np.any((np.any(lv != init, axis=-1) & mask)[:max(0, f0 - 8)])
                r["class"] = "explained" if (below and top_ok) else "UNEXPLAINED"
                if r["class"] != "explained":
                    r["note"] = f"lines beyond last write+{slack}: {not below}; top differs from INIT: {not top_ok}"
            if not r["latch_ok"]:
                r["class"] = "UNEXPLAINED"
                r["note"] = (r.get("note", "") + " LATCH != INIT").strip()
            res.append(r)
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 4
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 0
    runs = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or not argv[i - 1].startswith("--"))]
    outdir = SIM / "build" / "m1"
    outdir.mkdir(parents=True, exist_ok=True)
    rc = 0
    tot = {}
    for run in runs:
        vl = read_vislog(run)
        frames = sorted(p for p in (OUT / run / "frames").iterdir()
                        if p.is_dir() and int(p.name) in vl and (p / "snap.png").exists())
        if limit:
            frames = frames[:limit]
        nframes = sum(1 for p in (OUT / run / "frames").iterdir() if p.is_dir())
        if not frames:
            print(f"== {run}: {nframes} captured frames, none with visible-scan writes", flush=True)
            continue
        setname = json.loads((frames[0] / "state.json").read_text())["set"]
        batches = [frames[k:k + 30] for k in range(0, len(frames), 30)]
        results = []
        with ThreadPoolExecutor(jobs) as ex:
            for res in ex.map(lambda b: classify_batch(run, setname, b, vl), batches):
                results += res
        keys = ["frame", "class", "writes", "effective", "first_line", "last_line", "copies", "classes",
                "live_lines", "live_px", "latch_px", "latch_ok", "note"]
        with open(outdir / f"midscan_{run}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in results:
                w.writerow({k: r.get(k, "") for k in keys})
        cnt = {}
        for r in results:
            cnt[r["class"]] = cnt.get(r["class"], 0) + 1
            tot[r["class"]] = tot.get(r["class"], 0) + 1
        latch_diff = sum(1 for r in results if r.get("latch_px"))
        print(f"== {run}: {nframes} captured frames, {len(frames)} with visible-scan writes, "
              f"{sum(1 for r in results if r['effective'])} with value-changing ones, "
              f"{sum(1 for r in results if r['copies'])} with a sprite copy; LIVE {cnt}; "
              f"LATCH differs from MAME on {latch_diff}", flush=True)
        for r in results:
            if r["class"] == "UNEXPLAINED":
                print(f"   UNEXPLAINED {run}/{r['frame']}: {r.get('note', '')} lines {r.get('live_lines')}")
        if cnt.get("UNEXPLAINED"):
            rc = 1
    print(f"== total {tot}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
