#!/usr/bin/env python3
"""M2 boots: every capture in runs.txt run on the core from power-on with the
oracle's inputs (mame/out/<run>/inputs.csv), N at a time, into
build/m2/<run>/: io.txt (writes.csv classes), ints.txt (per-vblank
interrupt vector reads), and at every dump frame F the RAM dumps of vblank F
plus the displayed frames F-1 and F (rgbp + wlog), since MAME's snapshot at
vblank F shows the frame our displayed frame F-1 is.

Usage: m2/run_boots.py [--bin PATH] [--jobs N] [--frames N] [--promlat N] [run ...]
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
sys.path.insert(0, str(SIM / "mame"))
from run_captures import parse  # noqa: E402

OUT = SIM / "mame" / "out"
BUILD = SIM / "build"


def frames_of(spec):
    s = set()
    for tok in spec.split(","):
        if "/" in tok:
            ab, st = tok.split("/")
            a, b = ab.split("-")
            s.update(range(int(a), int(b) + 1, int(st)))
        elif "-" in tok:
            a, b = tok.split("-")
            s.update(range(int(a), int(b) + 1))
        else:
            s.add(int(tok))
    return s


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=str(BUILD / "m2" / "bin" / "Vd8_sys"))
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--frames", type=int, default=0, help="cap every run at N frames")
    ap.add_argument("--promlat", type=int, default=9)
    ap.add_argument("--tag", default="")
    ap.add_argument("runs", nargs="*")
    a = ap.parse_args(argv)
    lines = [ln.strip() for ln in (SIM / "runs.txt").read_text().splitlines() if ln.strip()]
    todo = [parse(ln) for ln in lines]
    if a.runs:
        todo = [t for t in todo if t[0] in a.runs]
    running = []
    while todo or running:
        while todo and len(running) < a.jobs:
            name, setname, spec, _extra = todo.pop(0)
            dumps = frames_of(spec)
            last = max(dumps)
            if a.frames:
                last = min(last, a.frames)
            d = BUILD / "m2" / (name + a.tag)
            if d.exists():
                shutil.rmtree(d)
            d.mkdir(parents=True)
            cap = sorted({f for f in dumps if f <= last} | {f - 1 for f in dumps if 1 <= f - 1 <= last})
            (d / "cap.txt").write_text("\n".join(map(str, cap)) + "\n")
            reg = BUILD / "regions" / setname
            cmd = [a.bin, f"+set={setname}", f"+sdram={reg / 'sdram.bin'}", f"+gfx={reg / 'gfx.bin'}",
                   f"+frames={last + 1}", f"+cap={d / 'cap.txt'}", f"+out={d}", f"+io={d / 'io.txt'}",
                   f"+ints={d / 'ints.txt'}", f"+inputs={OUT / name / 'inputs.csv'}", f"+promlat={a.promlat}"]
            log = open(d / "run.log", "w")
            p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            running.append((name, p, log, time.time()))
            print(f"start {name}{a.tag} ({setname}) to frame {last}", flush=True)
        time.sleep(5)
        for r in list(running):
            if r[1].poll() is not None:
                r[2].close()
                running.remove(r)
                print(f"done  {r[0]}{a.tag} rc={r[1].returncode} {time.time() - r[3]:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
