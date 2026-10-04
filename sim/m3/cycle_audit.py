#!/usr/bin/env python3
"""R17 cycle audit: per-instruction 6502 cycle counts in the core against the
Rockwell R65C02 data sheet (R65C00 family, instruction set op code matrix,
p. 1-11), using a MAME debugger trace for the instruction sequence.

  m3/cycle_audit.py MAME_TRACE CORE_TRACE

MAME_TRACE: "PC: mnemonic operand" lines (d8_oracle.lua SNDTRACE).
CORE_TRACE: "t,addr,byte" program reads (tb_sys.cpp +sndtrace, needs +snd
first on the command line: Verilator plusargs prefix-match).
Each instruction's length in the core = time between its opcode fetch and the
next instruction's opcode fetch x 1.5 MHz. Interrupt entries are skipped.
"""
import re
import sys
from collections import Counter, defaultdict

# Rockwell R65C02 data sheet cycle counts (base; + page/branch rules below)
DS = {
    'nop': 2, 'rts': 6, 'rti': 6, 'pha': 3, 'pla': 4, 'php': 3, 'plp': 4,
    'txa': 2, 'tax': 2, 'tya': 2, 'tay': 2, 'dex': 2, 'dey': 2, 'inx': 2, 'iny': 2,
    'clc': 2, 'sec': 2, 'cli': 2, 'sei': 2, 'asl a': 2, 'lsr a': 2, 'rol a': 2, 'ror a': 2,
}


def mode_cycles(mn, opnd):
    """data sheet cycles for load/store/ALU by addressing mode"""
    o = opnd.strip()
    if o.startswith('#'):
        return 2
    if re.fullmatch(r'\$[0-9a-f]{2}', o):
        return 3
    if re.fullmatch(r'\$[0-9a-f]{2}, ?[xy]', o):
        return 4
    if re.fullmatch(r'\$[0-9a-f]{4}', o):
        return 3 if mn == 'jmp' else 4
    if re.fullmatch(r'\$[0-9a-f]{4}, ?[xy]', o):
        return 4  # +1 if page crossed (data sheet *)
    if re.fullmatch(r'\(\$[0-9a-f]{2}\), ?y', o):
        return 5  # +1 if page crossed
    if re.fullmatch(r'\(\$[0-9a-f]{2}, ?x\)', o):
        return 6
    if re.fullmatch(r'\(\$[0-9a-f]{2}\)', o):
        return 5
    if re.fullmatch(r'\(\$[0-9a-f]{4}\)', o):
        return 6
    return None


def expected(mn, opnd):
    if mn == 'jsr':
        return 6
    key = (mn + ' ' + opnd).strip()
    if key in DS:
        return DS[key]
    if mn in DS and not opnd:
        return DS[mn]
    if mn in ('inc', 'dec', 'asl', 'lsr', 'rol', 'ror'):
        b = mode_cycles(mn, opnd)
        if b is None:
            return None
        # data sheet: zp 5, zp,x 6, abs 6, abs,x 7
        return b + (3 if re.fullmatch(r'\$[0-9a-f]{4}, ?x', opnd.strip()) else 2)
    if mn == 'sta' and re.fullmatch(r'\$[0-9a-f]{4}, ?[xy]', opnd.strip()):
        return 5  # data sheet 9D/99: 3 5 (no page-cross dependence)
    if mn == 'sta' and re.fullmatch(r'\(\$[0-9a-f]{2}\), ?y', opnd.strip()):
        return 6  # data sheet 91: 2 6
    if mn in ('bpl', 'bmi', 'bvc', 'bvs', 'bcc', 'bcs', 'bne', 'beq', 'bra'):
        return 'branch'
    return mode_cycles(mn, opnd)


def main(mt, ct):
    ins = []
    for ln in open(mt):
        m = re.match(r'^([0-9A-F]{4}): (\S+)\s*(.*)$', ln.rstrip())
        if m:
            ins.append((int(m.group(1), 16), m.group(2), m.group(3)))
        elif 'interrupted' in ln:
            ins.append((None, 'INT', ln.strip()))
    rows = []
    for ln in open(ct):
        p = ln.strip().split(',')
        if len(p) == 3:
            rows.append((float(p[0]), int(p[1], 16)))
    # start at the first core row whose address equals the first MAME pc
    j = 0
    times = []
    for pc, mn, op in ins:
        if pc is None:
            times.append(None)
            continue
        while j < len(rows) and rows[j][1] != pc:
            j += 1
        if j >= len(rows):
            break
        times.append(rows[j][0])
        j += 1
    stats = defaultdict(Counter)
    bad = Counter()
    for k in range(len(times) - 1):
        if times[k] is None or times[k + 1] is None:
            continue
        pc, mn, op = ins[k]
        cyc = round((times[k + 1] - times[k]) * 1.5e6)
        npc = ins[k + 1][0]
        e = expected(mn, op)
        if e == 'branch':
            tgt = int(op.strip()[1:], 16) if op.strip().startswith('$') else None
            taken = npc == tgt
            e = 2 if not taken else (3 if (tgt >> 8) == ((pc + 2) >> 8) else 4)
        key = f'{mn} {op}'.strip()
        stats[key][cyc] += 1
        if e is not None and cyc != e and abs(cyc - e) < 20:
            bad[(key, e, cyc)] += 1
    print('instruction: core cycle histogram')
    for key in sorted(stats, key=lambda k: -sum(stats[k].values())):
        print(f'  {key:28s} {dict(stats[key])}  data sheet {expected(*key.split(" ", 1)) if " " in key else expected(key, "")}')
    print('mismatches vs data sheet (instruction, expected, core, count):')
    for (key, e, c), n in bad.most_common(30):
        print(f'  {key:28s} ds {e} core {c} x{n}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
