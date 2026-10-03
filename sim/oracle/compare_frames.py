#!/usr/bin/env python3
"""Render oracle frame dumps with d8_render.py and diff them against MAME,
pixel for pixel.

Primary check: snap.png, MAME's snapshot of frame N. All three games are
ROT270, so the snapshot is the native frame rotated: snap = rot90(native, 1).
Secondary check: screen.argb (screen:pixels() captured one notifier later,
native orientation), used only when the palette did not change between the
two notifiers.

Palette: every entry the game has written (palette_written.bin) must decode
to MAME's pen (pens.bin) exactly. Entries never written show MAME's power-on
pens, a default pattern rather than hardware state; the renderer uses
MAME's pen for those so the rest of the frame can still be compared.

Usage: compare_frames.py <run_dir> [--diffdir DIR] [--quiet] [--stats CSV]
Exit status 0 only if every frame matches.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mame"))
from d8_render import render, palette_rgb  # noqa: E402
from frame_tools import load_argb  # noqa: E402


def to_snap(native):
    return np.rot90(native, 1)


def diff_report(tag, name, ours, ref, diffdir):
    neq = np.any(ours != ref, axis=-1)
    n = int(neq.sum())
    if n:
        ys, xs = np.nonzero(neq)
        print(f"DIFF  {name} [{tag}]: {n} px, first (x={xs[0]},y={ys[0]}) mame={tuple(int(v) for v in ref[ys[0], xs[0]])} "
              f"ours={tuple(int(v) for v in ours[ys[0], xs[0]])}, bbox x {xs.min()}-{xs.max()} y {ys.min()}-{ys.max()}")
        diffdir.mkdir(parents=True, exist_ok=True)
        vis = np.concatenate([ref, ours, (neq[..., None] * np.array([255, 0, 255])).astype(np.uint8)], axis=1)
        Image.fromarray(vis, "RGB").save(diffdir / f"{name}_{tag}.png")
    return n


def main(argv):
    run = Path(argv[0])
    diffdir = Path(argv[argv.index("--diffdir") + 1]) if "--diffdir" in argv else run / "diffs"
    statpath = Path(argv[argv.index("--stats") + 1]) if "--stats" in argv else run / "render_stats.csv"
    quiet = "--quiet" in argv
    frames = sorted(p for p in (run / "frames").iterdir() if p.is_dir())
    if not frames:
        print(f"no frames in {run}")
        return 1
    bad = 0
    checked = {"snap": 0, "pixels": 0}
    px = 0
    rows = []
    for fd in frames:
        st = json.loads((fd / "state.json").read_text())
        rgb, stats = render(fd)
        fail = 0
        ours_pal = palette_rgb((fd / "palette.bin").read_bytes(), (fd / "palette_ext.bin").read_bytes()).astype(np.uint8)
        mp = np.frombuffer((fd / "pens.bin").read_bytes(), dtype="<u4")
        mame_pal = np.stack([(mp >> 16) & 255, (mp >> 8) & 255, mp & 255], axis=-1).astype(np.uint8)
        wp = fd / "palette_written.bin"
        written = (np.frombuffer(wp.read_bytes(), dtype=np.uint8).astype(bool)[:len(mame_pal)]
                   if wp.exists() else np.ones(len(mame_pal), bool))
        bad_dec = np.nonzero(np.any(ours_pal[:len(mame_pal)] != mame_pal, axis=-1) & written)[0]
        if len(bad_dec):
            print(f"PALDEC {fd.name}: {len(bad_dec)} entries decode differently from MAME's pens (first {bad_dec[0]})")
            fail += 1
        snap = np.array(Image.open(fd / "snap.png").convert("RGB"))
        view = to_snap(rgb)
        if view.shape != snap.shape:
            print(f"SHAPE {fd.name}: ours {view.shape} snap {snap.shape}")
            fail += 1
        else:
            fail += bool(diff_report("snap", fd.name, view, snap, diffdir))
            checked["snap"] += 1
            px += snap.shape[0] * snap.shape[1]
        if (fd / "screen.argb").exists() and (fd / "palette_next.bin").exists():
            nxt = (fd / "palette_next.bin").read_bytes()
            cur = (fd / "palette.bin").read_bytes() + (fd / "palette_ext.bin").read_bytes()
            if nxt == cur:
                ref = load_argb(fd)
                if ref.shape == rgb.shape:
                    fail += bool(diff_report("pixels", fd.name, rgb, ref, diffdir))
                    checked["pixels"] += 1
        bad += bool(fail)
        rows.append([fd.name, st.get("sprites", -1), stats.get("sprites_drawn", -1), stats.get("unwritten_px", 0), int(fail == 0)])
        if not fail and not quiet:
            print(f"MATCH {fd.name}")
    with open(statpath, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["frame", "sprites_listed", "sprites_drawn", "unwritten_pen_px", "match"])
        wr.writerows(rows)
    print(f"{len(frames) - bad}/{len(frames)} frames pixel-exact "
          f"(snap checks {checked['snap']}, pixels() checks {checked['pixels']}, {px} snapshot px)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
