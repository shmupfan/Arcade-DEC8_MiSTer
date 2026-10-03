#!/usr/bin/env python3
"""M3 runs: the six sound captures, MAME (oracle) and/or the core.

  m3/run_m3.py oracle [run ...]   MAME with SNDLOG=1 and -wavwrite (48 kHz),
                                  sound RAM dumps every 100 frames, into
                                  mame/out/m3_<run>/
  m3/run_m3.py core [run ...]     the core (build/m3/obj_dir/Vd8_sys) with
                                  +snd, +aud and the same inputs, into
                                  build/m3/<run>/

Runs (frames): the M2 captures' inputs (runs.txt), cut at FRAMES below.
Gondomania stops before its first random choice (m2_findings 4.1: the MCU
interrupt timing splits it from MAME at go_play 1748 / go_attract 2705).
Every process runs at nice 15, at most JOBS (3) at once.
"""
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
FRAMES = {"lm_attract": 3600, "lm_play": 3600, "go_attract": 2700, "go_play": 1740,
          "sr_attract": 3600, "sr_play": 3600}
JOBS = int(os.environ.get("JOBS", "3"))


def runs(only):
    out = []
    for ln in (SIM / "runs.txt").read_text().splitlines():
        if not ln.strip():
            continue
        name, setname, _frames, extra = parse(ln.strip())
        if name in FRAMES and (not only or name in only):
            out.append((name, setname, extra))
    return out


def launch(mode, name, setname, extra):
    n = FRAMES[name]
    if mode == "oracle":
        d = OUT / f"m3_{name}"
        if d.exists():
            shutil.rmtree(d)
        env = dict(os.environ, DUMP_DIR=str(d), DUMP_FRAMES=f"100-{n}/100", TOTAL=str(n), RT_TAG=f"m3_{name}",
                   SNDLOG="1", NO_SNAP="1", **extra)
        d.mkdir(parents=True)
        cmd = ["nice", "-n", "15", str(SIM / "mame" / "run_mame.sh"), setname, str(SIM / "mame" / "d8_oracle.lua"),
               "-wavwrite", str(d / "mame.wav"), "-samplerate", "48000"]
        log = open(OUT / f"m3_{name}.log", "w")
        return subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT), log
    d = BUILD / "m3" / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    cap = list(range(100, n + 1, 100))
    (d / "cap.txt").write_text("\n".join(map(str, cap)) + "\n")
    reg = BUILD / "regions" / setname
    cmd = ["nice", "-n", "15", str(BUILD / "m3" / "obj_dir" / "Vd8_sys"), f"+set={setname}",
           f"+sdram={reg / 'sdram.bin'}", f"+gfx={reg / 'gfx.bin'}", f"+frames={n + 1}", f"+cap={d / 'cap.txt'}",
           f"+out={d}", f"+inputs={OUT / ('m3_' + name) / 'inputs.csv'}", f"+snd={d / 'sndlog.csv'}",
           f"+aud={d / 'aud.raw'}"]
    log = open(d / "run.log", "w")
    return subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), log


def main(argv):
    mode, only = argv[0], set(argv[1:])
    todo = runs(only)
    running = []
    while todo or running:
        while todo and len(running) < JOBS:
            name, setname, extra = todo.pop(0)
            p, log = launch(mode, name, setname, extra)
            running.append((name, p, log, time.time()))
            print(f"start {mode} {name} ({setname}) {FRAMES[name]} frames", flush=True)
        time.sleep(5)
        for r in list(running):
            if r[1].poll() is not None:
                r[2].close()
                running.remove(r)
                print(f"done  {mode} {r[0]} rc={r[1].returncode} {time.time() - r[3]:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
