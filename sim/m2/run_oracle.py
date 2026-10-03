#!/usr/bin/env python3
"""M2 oracle reruns: every capture in runs.txt again with MAINRAM=1 (work
RAM, MCU internal RAM and CPU state per dump frame, d8_oracle.lua) and
NO_SNAP=1, into mame/out/m2ram_<run>/. MAME runs the same inputs from power-on,
so these are the same frames as the M0 captures (compare.py checks the video
RAM dumps of both runs are identical on every shared frame).

Usage: m2/run_oracle.py [jobs] [run ...]
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
sys.path.insert(0, str(SIM / "mame"))
from run_captures import parse  # noqa: E402

OUT = SIM / "mame" / "out"


def main(argv):
    jobs = int(argv[0]) if argv else 3
    only = set(argv[1:])
    lines = [ln.strip() for ln in (SIM / "runs.txt").read_text().splitlines() if ln.strip()]
    pending = [parse(ln) for ln in lines]
    pending = [p for p in pending if not only or p[0] in only]
    running = []
    while pending or running:
        while pending and len(running) < jobs:
            name, setname, frames, extra = pending.pop(0)
            out = OUT / f"m2ram_{name}"
            env = dict(os.environ, DUMP_DIR=str(out), DUMP_FRAMES=frames, RT_TAG=f"m2ram_{name}",
                       MAINRAM="1", NO_SNAP="1", **extra)
            log = open(OUT / f"m2ram_{name}.log", "w")
            p = subprocess.Popen([str(SIM / "mame" / "run_mame.sh"), setname, str(SIM / "mame" / "d8_oracle.lua")],
                                 env=env, stdout=log, stderr=subprocess.STDOUT)
            running.append((name, p, log, time.time()))
            print(f"start m2ram_{name} ({setname})", flush=True)
        time.sleep(2)
        for r in list(running):
            if r[1].poll() is not None:
                r[2].close()
                running.remove(r)
                print(f"done  m2ram_{r[0]} rc={r[1].returncode} {time.time() - r[3]:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
