#!/usr/bin/env python3
"""M1 mid-scan input: rerun every M0 capture of runs.txt with VISLOG=1 and
NO_DUMP=1 into mame/out/vislog/<run>/ (same frames, inputs and DIP fields,
each run in its own MAME runtime dir), then check the rerun executed
identically to the M0 capture: frames.csv (per-frame scroll, flip, sprite
buffer and interrupt trace) must be byte-identical.

Usage (from sim/): python3 mame/vislog_runs.py [--jobs N]
"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
OUT = HERE / "out"
sys.path.insert(0, str(HERE))
from run_captures import parse  # noqa: E402


def one(r):
    name, setname, frames, extra = r
    d = OUT / "vislog" / name
    if d.exists():
        subprocess.run(["rm", "-rf", str(d)], check=True)
    env = dict(os.environ, RT_TAG=f"vislog_{name}", DUMP_DIR=str(d), DUMP_FRAMES=frames, VISLOG="1",
               NO_DUMP="1", NO_SNAP="1", **extra)
    with open(OUT / "vislog" / f"{name}.log", "w") as log:
        rc = subprocess.run([str(HERE / "run_mame.sh"), setname, str(HERE / "d8_oracle.lua")],
                            cwd=SIM, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    a, b = d / "frames.csv", OUT / name / "frames.csv"
    same = a.exists() and a.read_bytes() == b.read_bytes()
    rows = sum(1 for _ in open(d / "vislog.csv")) - 1 if (d / "vislog.csv").exists() else -1
    return name, rc, same, rows


def main(argv):
    jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 4
    runs = [parse(ln.strip()) for ln in (SIM / "runs.txt").read_text().splitlines() if ln.strip()]
    (OUT / "vislog").mkdir(parents=True, exist_ok=True)
    bad = 0
    with ThreadPoolExecutor(jobs) as ex:
        for name, rc, same, rows in ex.map(one, runs):
            ok = rc == 0 and same and rows >= 0
            bad += not ok
            print(f"{name}: rc {rc}, frames.csv identical to M0 run: {same}, vislog rows {rows}", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
