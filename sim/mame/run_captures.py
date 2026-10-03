#!/usr/bin/env python3
"""Run the oracle captures listed in runs.txt, N at a time.

runs.txt lines: <name> <set> <dump_frames> [KEY=value ...]; a value runs to
the end of the line (INPUTS and FIELDS hold spaces). Each run writes
mame/out/<name>/ and mame/out/<name>.log, with its own MAME runtime dir
(RT_TAG=<name>) so parallel runs of one set never share cfg/nvram.

Usage: run_captures.py runs.txt [jobs]
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def parse(line):
    name, setname, frames, *rest = line.split(" ", 3) + [""] * 0
    env = {}
    rest = rest[0] if rest else ""
    for m in re.finditer(r"(INPUTS|FIELDS)=(.*?)(?=\s+(?:INPUTS|FIELDS)=|$)", rest):
        env[m.group(1)] = m.group(2)
    return name, setname, frames, env


def main(argv):
    lines = [ln.strip() for ln in Path(argv[0]).read_text().splitlines() if ln.strip()]
    jobs = int(argv[1]) if len(argv) > 1 else 4
    pending = [parse(ln) for ln in lines]
    running = []
    while pending or running:
        while pending and len(running) < jobs:
            name, setname, frames, extra = pending.pop(0)
            env = dict(os.environ, DUMP_DIR=str(OUT / name), DUMP_FRAMES=frames, RT_TAG=name, **extra)
            log = open(OUT / f"{name}.log", "w")
            p = subprocess.Popen([str(HERE / "run_mame.sh"), setname, str(HERE / "d8_oracle.lua")],
                                 env=env, stdout=log, stderr=subprocess.STDOUT)
            running.append((name, p, log, time.time()))
            print(f"start {name} ({setname})", flush=True)
        time.sleep(2)
        for r in list(running):
            if r[1].poll() is not None:
                r[2].close()
                running.remove(r)
                print(f"done  {r[0]} rc={r[1].returncode} {time.time() - r[3]:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
