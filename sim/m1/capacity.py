#!/usr/bin/env python3
"""M1 sprites-per-line probe (not a gate): scenes with N sprites crossing
one line (all enabled, distinct x, random flips/colours/codes, every 4th
double height), N up to the whole list (Karnov 256, srdarwin 128), replayed
through the LIVE RTL with the pessimistic ROM model; prints the worst line's
render clocks (budget 6,144 at 96 MHz) and the overrun count, and checks
the picture against d8_render.py while no line overruns.

Usage: capacity.py [--intv N] [--lat N]
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_scenes import SETS, Scene  # noqa: E402


def main(argv):
    intv = argv[argv.index("--intv") + 1] if "--intv" in argv else "8"
    lat = argv[argv.index("--lat") + 1] if "--lat" in argv else "9"
    rng = np.random.default_rng(1)
    with tempfile.TemporaryDirectory(prefix="d8cap_") as td:
        td = Path(td)
        for machine, setname in SETS.items():
            sr = machine == "srdarwin"
            for n in ((32, 64, 96, 128) if sr else (32, 64, 96, 128, 192, 256)):
                s = Scene(machine, 0, rng)
                for k in range(n):
                    if sr:
                        s.srs(k, 120, int(rng.integers(0, 8)), int(rng.integers(0, 2)), int(k % 4 == 0),
                              int(rng.integers(1, 2048)), (k * 2) & 0xFF)
                    else:
                        s.krn(k, True, k % 4 == 0, 120, int(rng.integers(0, 2)), int(rng.integers(0, 2)),
                              (k * 2) & 0x1FF, int(rng.integers(0, 16)), int(rng.integers(0, 4096)))
                d = td / f"{machine}_{n}"
                s.write(d, setname, 1)
                p = subprocess.run([sys.executable, str(HERE / "replay.py"), str(d), "--jobs", "1",
                                    "--intv", intv, "--lat", lat, "--model_only"],
                                   capture_output=True, text=True)
                line = [ln for ln in p.stdout.splitlines() if ln.startswith("==")]
                print(f"{machine:8s} {n:3d} sprites on one line: {line[-1] if line else p.stderr[-200:]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
