#!/usr/bin/env python3
"""M2 gate table: one Markdown row per run from build/m2/<run>/compare.txt
(written by compare.py) and run.log (gate counters).
Usage (from sim/): python3 m2/gate_table.py run ..."""
import json
import sys
from pathlib import Path

B = Path(__file__).resolve().parent.parent / "build" / "m2"
print("| Run | Frames | I/O writes main / sub | Moved | Beam delta px (min / median / max) | Interrupt frames differ | Images exact / live / unexplained | Work RAM byte differences summed over dumps (dead stack / idle counter / transient / other persistent) | MCU RAM (tick / other) | Video RAM persistent | Counters | Result |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for run in sys.argv[1:]:
    r = json.loads((B / run / "compare.txt").read_text())
    io, ints, ram, img = r["io"], r["ints"], r["ram"], r["image"]
    last = [l for l in (B / run / "run.log").read_text().splitlines() if l.startswith("DONE")]
    cnt = last[-1].split("cycles")[1].split(None, 1)[1] if last else "?"
    cnt = " ".join(f"{k} {v}" for k, v in zip(cnt.split()[0::2], cnt.split()[1::2]) if k != "maxcyc")

    def eq(c):
        x = io[c]
        return f"{x['mame']}" + ("" if x["equal"] else f" (first diff #{x['first_diff']['index']})")
    d = io["main"].get("delta_px", {})
    rc = ram.get("ram_class", {}) or {}
    vid = sum(v.get("persistent", 0) for k, v in ram.items() if k not in ("ram", "mcu", "ram_class", "oracle_runs_same"))
    ok = (io["main"]["equal"] and io["sub"]["equal"] and ints["differ"] == 0 and img["unexplained"] == 0 and
          rc.get("other_persistent", 0) == 0 and vid == 0 and ram["mcu"].get("persistent", 0) == 0)
    print(f"| {run} | {r['frames'] - 1} | {eq('main')} / {eq('sub')} | {len(io['main']['moved']) + len(io['sub']['moved'])} | "
          f"{d.get('min', '-')} / {d.get('median', '-')} / {d.get('max', '-')} | {ints['differ']} | "
          f"{img['exact']} / {img['live']} / {img['unexplained']} | "
          f"{rc.get('dead_stack', 0)} / {rc.get('idle_counter', 0)} / {rc.get('other_transient', 0)} / {rc.get('other_persistent', 0)} | "
          f"{ram['mcu'].get('tick', 0)} / {ram['mcu'].get('persistent', 0)} | {vid} | {cnt} | {'PASS' if ok else 'see 3.x'} |")
