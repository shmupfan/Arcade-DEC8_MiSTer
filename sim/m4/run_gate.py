#!/usr/bin/env python3
"""M4 gate: the same runs on the M2 harness (d8_sys with C++ ROM models,
rebuilt from the current RTL: the reference) and on the board harness
(d8_board: ioctl download of the MRA's stream, d8_sdram, SDRAM model), then
every output compared byte for byte (compare_m2.py).

  run_gate.py ref|board [--jobs N] RUN:SET:FRAMES ...
  run_gate.py compare RUN:SET:FRAMES ...

Outputs in sim/build/m4/gate/{ref,board}/<run>/. Captures: frames 1-60 and
every 20th frame. Inputs from the MAME oracle (mame/out/<run>/inputs.csv).
Simulators run under nice -n 15.
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
GATE = SIM / "build" / "m4" / "gate"
BIN = {"ref": SIM / "build" / "m4" / "ref_obj" / "Vd8_sys",
       "board": SIM / "build" / "m4" / "board_obj" / "Vtb_board"}


def cmd_for(kind, run, setname, frames, d):
    reg = SIM / "build" / "regions" / setname
    cap = sorted(set(range(1, 61)) | set(range(20, frames + 1, 20)))
    (d / "cap.txt").write_text("\n".join(map(str, cap)) + "\n")
    c = ["nice", "-n", "15", str(BIN[kind]), f"+set={setname}", f"+frames={frames}", f"+cap={d / 'cap.txt'}",
         f"+out={d}", f"+io={d / 'io.txt'}", f"+ints={d / 'ints.txt'}", f"+snd={d / 'sndlog.csv'}"]
    inp = SIM / "mame" / "out" / run / "inputs.csv"
    if inp.exists():
        c.append(f"+inputs={inp}")
    if kind == "ref":
        c += [f"+sdram={reg / 'sdram.bin'}", f"+gfx={reg / 'gfx.bin'}"]
    else:
        c += [f"+stream={reg / 'stream.bin'}"]
    return c


def run(kind, specs, jobs):
    todo = [s.split(":") for s in specs]
    running = []
    while todo or running:
        while todo and len(running) < jobs:
            r, setname, frames = todo.pop(0)
            d = GATE / kind / r
            d.mkdir(parents=True, exist_ok=True)
            for f in d.iterdir():
                f.unlink()
            log = open(d / "run.log", "w")
            p = subprocess.Popen(cmd_for(kind, r, setname, int(frames), d), stdout=log, stderr=subprocess.STDOUT)
            running.append((r, p, log, time.time()))
            print(f"start {kind} {r}", flush=True)
        time.sleep(5)
        for x in list(running):
            if x[1].poll() is not None:
                x[2].close()
                running.remove(x)
                print(f"done  {kind} {x[0]} rc={x[1].returncode} {time.time() - x[3]:.0f}s", flush=True)


def main(argv):
    mode = argv[0]
    jobs = 3
    if "--jobs" in argv:
        i = argv.index("--jobs")
        jobs = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    specs = argv[1:]
    if mode in BIN:
        run(mode, specs, jobs)
        return 0
    sys.path.insert(0, str(HERE))
    from compare_m2 import compare
    rc = 0
    for s in specs:
        r = s.split(":")[0]
        print(f"== {r}")
        for ln in (GATE / "board" / r / "run.log").read_text().splitlines():
            if ln.startswith(("download", "PRE-RUN", "DONE", "SDRAM")):
                print("  " + ln)
        rc |= not compare(GATE / "board" / r, GATE / "ref" / r)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
