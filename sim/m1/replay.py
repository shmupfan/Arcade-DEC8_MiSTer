#!/usr/bin/env python3
"""M1 video parity: replay oracle frame dumps through the d8_video RTL
(Verilator harness sim/m1/tb_video.cpp) and compare every frame.

References per frame:
  - MAME's snapshot (snap.png; all three games are ROT270, so snap =
    rot90(native, 1)) when the frame dir has one: the M1 gate. Palette
    entries the game never wrote show MAME's power-on pens there (a default
    pattern, not hardware state, m0_findings 1); the RTL shows whatever the
    palette RAM holds. Pixels whose palette index (the RTL's own o_dbg_pen)
    is an unwritten entry are excluded from the snapshot check and counted;
    their palette index is still checked below.
  - always: the Python reference renderer sim/oracle/d8_render.py, both the
    RGB (written entries) and the palette index of every pixel.

Usage:
  replay.py <run_dir>... [--jobs N] [--batch N] [--lat N] [--intv N]
            [--limit N] [--quiet] [--latch] [--krnflip]
run_dir holds frames/NNNNNN/ (sim/mame/out/<run> or a synthetic scene dir).
Exit 0 only if every frame matches and no line overran its budget.
"""
import json
import os
import struct
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "oracle"))
from d8_render import render  # noqa: E402

BIN = HERE.parent / "build" / "m1" / "obj_dir" / "Vd8_video"
LBIN = HERE.parent / "build" / "m1_latch" / "obj_dir" / "Vd8_video"
KBIN = HERE.parent / "build" / "m1_krnflip" / "obj_dir" / "Vd8_video"
REGIONS = ROOT / "sim" / "build" / "regions"
MACHINE = {"lastmisn": 0, "gondo": 1, "srdarwin": 2, "srdarwinb": 2}
RAM_FILES = [("palette.bin", 1024), ("palette_ext.bin", 1024), ("fixram.bin", 2048), ("bgram.bin", 2048),
             ("spr_buf.bin", 2048), ("spr_live.bin", 2048)]
TARGET = {"pal": 0, "palx": 1, "fixram": 2, "bgram": 3, "spr": 4, "copy": 5,
          "scroll0": 8, "scroll1": 9, "scroll2": 10, "scroll3": 11, "flip": 16}


def ram(fd, name, nbytes, override=None):
    if override is not None and name in override:
        b = override[name]
    else:
        p = fd / name
        b = p.read_bytes() if p.exists() else b""
    return (b + bytes(nbytes))[:nbytes]


def make_d8f(fd, path, st=None, override=None, writes=()):
    """writes: list of (line, hcnt, target, addr, data)."""
    st = st or json.loads((fd / "state.json").read_text())
    sc = [int(v) & 0xFF for v in st["scroll"]]
    hdr = (b"D8F1" + bytes([MACHINE[st["machine"]], 1 if st["flip_x"] else 0])
           + struct.pack("<I", len(writes)) + bytes(sc) + b"\0\0")
    body = b"".join(ram(fd, n, sz, override) for n, sz in RAM_FILES)
    wl = b"".join(struct.pack("<HHBBH", ln, h, t, d & 0xFF, a & 0xFFFF) for ln, h, t, a, d in writes)
    path.write_bytes(hdr + body + wl)
    return st


def load_out(out_path):
    raw = np.frombuffer(out_path.read_bytes(), dtype=np.uint8)
    pen_p = Path(str(out_path) + ".pen")
    pen = np.frombuffer(pen_p.read_bytes(), dtype="<u2") if pen_p.exists() else np.zeros(0)
    if raw.size != 256 * 240 * 3 or pen.size != 256 * 240:
        return None, None
    return raw.reshape(240, 256, 3).copy(), pen.reshape(240, 256).copy()


def written_mask(fd, npal):
    p = fd / "palette_written.bin"
    if not p.exists():
        return np.ones(1024, dtype=bool)
    w = np.frombuffer(p.read_bytes(), dtype=np.uint8).astype(bool)
    out = np.zeros(1024, dtype=bool)
    out[:len(w)] = w
    return out


def check(fd, st, out_path, diffdir, model_only=False):
    """Return (ok, message, details)."""
    rgb, pen = load_out(out_path)
    if rgb is None:
        return False, f"size {out_path.stat().st_size}", {}
    ref_rgb, _, ref_pen = render(fd, pens=True)
    wm = written_mask(fd, 1024)
    unw = ~wm[pen]
    msgs = []
    det = {"unwritten_px": int(unw.sum())}
    neq_p = pen != ref_pen
    if neq_p.any():
        ys, xs = np.nonzero(neq_p)
        msgs.append(f"pen {int(neq_p.sum())} px, first x={xs[0]} y={ys[0]} ref={int(ref_pen[ys[0], xs[0]])} "
                    f"rtl={int(pen[ys[0], xs[0]])}")
    neq_m = np.any(rgb != ref_rgb, axis=-1) & ~unw
    det["model_rows"] = sorted(set(np.nonzero(neq_m)[0].tolist()))
    if neq_m.any():
        ys, xs = np.nonzero(neq_m)
        msgs.append(f"model rgb {int(neq_m.sum())} px, first x={xs[0]} y={ys[0]}")
    snap_p = fd / "snap.png"
    tag = "model"
    if snap_p.exists() and not model_only:
        view, vskip = np.rot90(rgb, 1), np.rot90(unw, 1)
        ref = np.array(Image.open(snap_p).convert("RGB"))
        tag = "snap"
        if view.shape != ref.shape:
            return False, f"shape {view.shape} vs {ref.shape}", det
        neq = np.any(view != ref, axis=-1) & ~vskip
        n = int(neq.sum())
        det["snap_rows"] = sorted(set(np.nonzero(np.rot90(neq, -1))[0].tolist()))
        if n:
            ys, xs = np.nonzero(neq)
            msgs.append(f"snap {n} px, first x={xs[0]} y={ys[0]} ref={tuple(int(v) for v in ref[ys[0], xs[0]])} "
                        f"rtl={tuple(int(v) for v in view[ys[0], xs[0]])}")
            diffdir.mkdir(parents=True, exist_ok=True)
            vis = np.concatenate([ref, view, (neq[..., None] * np.array([255, 0, 255])).astype(np.uint8)], axis=1)
            Image.fromarray(vis, "RGB").save(diffdir / f"{fd.name}_{tag}.png")
    if det["unwritten_px"]:
        tag += "+unwritten"
    return (not msgs), ("; ".join(msgs) if msgs else tag), det


def harness(td, items, setname, args, binp=None):
    (td / "list.txt").write_text("".join(f"{a} {b}\n" for a, b in items))
    cmd = [str(binp or BIN), f"+sdram={REGIONS / setname / 'gfx.bin'}", f"+list={td / 'list.txt'}",
           f"+lat={args['lat']}", f"+intv={args['intv']}"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    stats = {"overruns": 0, "maxcyc": 0, "err": 0}
    for ln in p.stdout.splitlines():
        if ln.startswith("FRAME"):
            f = ln.split()
            stats["overruns"] += int(f[3])
            stats["maxcyc"] = max(stats["maxcyc"], int(f[5]))
            stats["err"] = max(stats["err"], int(f[7]))
    return p.returncode, p.stdout, p.stderr, stats


def binary(args):
    return LBIN if args.get("latch") else KBIN if args.get("krnflip") else BIN


def run_batch(batch, setname, args, diffdir):
    with tempfile.TemporaryDirectory(prefix="d8m1_") as td:
        td = Path(td)
        items, states = [], []
        for fd in batch:
            inp, outp = td / f"{fd.name}.d8f", td / f"{fd.name}.rgb"
            states.append(make_d8f(fd, inp))
            items.append((inp, outp))
        rc, _, err, stats = harness(td, items, setname, args, binary(args))
        if rc not in (0, 1):
            return [(fd, False, f"harness rc {rc}: {err[-300:]}") for fd in batch], stats
        res = []
        for fd, st, (_, outp) in zip(batch, states, items):
            if not outp.exists():
                res.append((fd, False, "no output"))
                continue
            ok, msg, _ = check(fd, st, outp, diffdir, model_only=args.get("model_only", False))
            res.append((fd, ok, msg))
        return res, stats


def main(argv):
    opts = {"jobs": max(1, (os.cpu_count() or 4) // 3), "batch": 40, "lat": 9, "intv": 8, "limit": 0}
    runs, quiet = [], False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--quiet":
            quiet = True
        elif a in ("--latch", "--krnflip", "--model_only"):
            opts[a[2:]] = True
        elif a.startswith("--"):
            opts[a[2:]] = int(argv[i + 1])
            i += 1
        else:
            runs.append(Path(a))
        i += 1
    if not binary(opts).exists():
        sys.exit(f"missing {binary(opts)}; run make m1-build")
    rc = 0
    total = good_all = 0
    for run in runs:
        frames = sorted(p for p in (run / "frames").iterdir() if p.is_dir())
        if opts["limit"]:
            frames = frames[:opts["limit"]]
        groups = {}
        for fd in frames:
            st = json.loads((fd / "state.json").read_text())
            groups.setdefault((st["set"], MACHINE[st["machine"]]), []).append(fd)
        batches = [(s, fs[k:k + opts["batch"]]) for (s, _), fs in groups.items() for k in range(0, len(fs), opts["batch"])]
        diffdir = run / "m1_diffs"
        good = over = maxcyc = err = 0
        tags = {}
        with ThreadPoolExecutor(max_workers=opts["jobs"]) as ex:
            for res, stats in ex.map(lambda b: run_batch(b[1], b[0], opts, diffdir), batches):
                over += stats["overruns"]
                maxcyc = max(maxcyc, stats["maxcyc"])
                err = max(err, stats["err"])
                for fd, ok, msg in res:
                    good += ok
                    if ok:
                        tags[msg] = tags.get(msg, 0) + 1
                    if not ok or not quiet:
                        print(f"{'MATCH' if ok else 'DIFF '} {run.name}/{fd.name}: {msg}", flush=True)
        print(f"== {run.name}: {good}/{len(frames)} frames exact ({tags}); line overruns {over}; snapshot errors {err}; "
              f"max render clocks/line {maxcyc} (budget 6144; ROM 1 req / {opts['intv']} clk, latency {opts['lat']})",
              flush=True)
        total += len(frames)
        good_all += good
        if good != len(frames) or over or err:
            rc = 1
    if len(runs) > 1:
        print(f"== total {good_all}/{total}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
