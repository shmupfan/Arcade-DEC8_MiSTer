#!/usr/bin/env python3
"""Compare a MAME debugger trace (PC: mnemonic lines) with the core's
+pctrace for one CPU. mc6809i flags both bytes of a prefixed opcode (0x10,
0x11) as opcode fetches, so a core entry at the previous entry + 1 is the
second byte of the same instruction and is skipped. Aligned at the first
occurrence of --align (a PC both traces pass once).
Usage: trace_cmp.py mame.tr core.tr cpu ALIGN_PC [context]"""
import re
import sys

mt, ct, cpu, al = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4], 16)
ctx = int(sys.argv[5]) if len(sys.argv) > 5 else 12
m = [(int(l.split(':')[0], 16), l.strip()) for l in open(mt) if re.match(r'^[0-9A-F]{4}:', l)]
raw = [l.split() for l in open(ct) if l.split()[3] == cpu]
o = []
for x in raw:
    a = int(x[4], 16)
    if o and a == o[-1][0] + 1 and o[-1][2] in ("10", "11"):
        continue
    o.append((a, x[:3], None))
# the prefix byte is known from MAME's mnemonic list: an entry whose MAME
# instruction is a long branch / page 2-3 op; simpler: drop core entries at
# prev+1 when MAME's next PC is not prev+1
mm = [x[0] for x in m]
mi = mm.index(al)
oi = next(i for i, x in enumerate(o) if x[0] == al)
k = 0
j = oi
i = mi
diffs = 0
while i < len(mm) and j < len(o):
    if mm[i] == o[j][0]:
        i += 1; j += 1; continue
    if j > 0 and o[j][0] == o[j - 1][0] + 1:   # prefix second byte
        j += 1; continue
    print(f"first diff: mame {mm[i]:04x} ({m[i][1][:40]}) core {o[j][0]:04x} at {' '.join(o[j][1])}")
    for t in range(-ctx, 4):
        a = i + t
        b = j + t
        print("   ", (m[a][1][:40] if 0 <= a < len(m) else "").ljust(42),
              (f"{o[b][0]:04x} {' '.join(o[b][1])}" if 0 <= b < len(o) else ""))
    diffs = 1
    break
print(f"compared {i - mi} mame instructions, {'DIFF' if diffs else 'equal'}")
