#!/usr/bin/env python3
"""M4: generate the MRA files and prove each one reproduces the ROM stream
the board expects (rtl/d8_board.sv, docs/m4_findings.md 2):

  0x000000-0x087FFF  sim/build/regions/<set>/sdram.bin bytes 0-0x87FFF
                     (tools/build_regions.py SDRAM_SLOTS: maincpu, mainbank,
                     sub, audiocpu, mcu, proms)
  0x088000-0x0FFFFF  zero fill
  0x100000-0x207FFF  sim/build/regions/<set>/gfx.bin (tools/gfx_layout.py)

srdarwinb is the one exception: its sprite ROMs are streamed as dumped
(bytes 1 and 2 of each 4-byte group swapped, MAME init_srdarwinb) and the
board swaps the sprite word address bits 0 and 1 instead; the check applies
that address swap to the assembled stream before comparing.

The generator records where every stream byte comes from (file + position,
or a fill value) by replaying the ROM_START loads with tools/romdefs.py
semantics and applying gfx_layout.layout() to those provenance codes, then
encodes the sequence as MRA parts (as the 1945k III generator):
  linear run from one file      <part name crc offset length/>
  2- or 4-byte lane interleave  <interleave output="16|32"> one part per
                                run of lanes with consecutive positions in
                                one file (the same file may give several
                                parts at different offsets; a lane may be
                                inline fill data), map nibble k = which byte
                                of the part's group lands in output byte k
  fill                          <part repeat="N">VV</part>
assemble() replays the MRA with Main_MiSTer's mra_loader.cpp rules (map
nibble k = output byte k of the unit, rightmost nibble = lowest address;
offset/length/repeat/crc per part) from the zips and compares; the verified
stream is written to sim/build/regions/<set>/stream.bin for the board
simulation (sim/m4).

DIP switches come from the driver's INPUT_PORTS blocks (never typed by hand,
PORT_INCLUDE / PORT_MODIFY followed): every PORT_DIPNAME of DSW0 and DSW1
becomes a <dip>; PORT_DIPUNUSED switches are left out (both operator
manuals list them as not used, docs/m4_findings.md 5); the default bytes
are the ports' default values. MRA byte 0 = DSW0 (SW1), byte 1 = DSW1 (SW2).

Usage: tools/make_mra.py [set ...]      (default: every set in the driver)
Writes releases/<Title>.mra (parents) and releases/_alternatives/_<Game>/
(clones); exit 0 only if every MRA verifies.
"""
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from romdefs import ROOT, DRIVER, parse_driver                 # noqa: E402
from build_regions import SDRAM_SLOTS, OUT as REGIONS          # noqa: E402
from gfx_layout import layout, SIZE as GFX_SIZE, BASE as GFX_BASE   # noqa: E402

RBF = "dec8"                     # matches releases/Arcade-DEC8_YYYYMMDD.rbf
PROG_END = 0x088000              # program area of the stream
GFX_AT = 0x100000                # graphics block in the stream
MACHINE_ID = {"lastmisn": 0, "gondo": 1, "srdarwin": 2, "srdarwinb": 2 | 4}
OUTDIR = ROOT / "releases"
PARENT_GAME = {"lastmisn": "Last Mission", "gondo": "Gondomania", "srdarwin": "SRD Super Real Darwin"}
SPR_SWAP = {"srdarwinb"}         # sprite word address bits 0/1 swapped by the board

FILL = -1                        # file index value for fill bytes (position = value)


# ------------------------------------------------------------------ sources
def region_codes(region, fid):
    """Provenance code per byte of one region as loaded (no driver init):
    (file << 32) | position, or -1 - value for fill bytes."""
    code = np.full(region.size, -1, dtype=np.int64)          # zero fill
    for ld in region.loads:
        if ld.no_dump:
            continue
        if ld.kind == "FILL":
            code[ld.offset:ld.offset + ld.length] = -1 - int(ld.crc, 16)
            continue
        f = fid(ld.crc, ld.name)
        for kind, ofs, length, pos in ld.pieces:
            k = np.arange(length, dtype=np.int64)
            assert kind == "LOAD", kind                       # the only kind DEC8 uses
            code[ofs + k] = (f << 32) | (pos + k)
    return code


def stream_codes(rs):
    """Provenance codes of the whole stream, plus the file table."""
    crcs, names = [], []

    def fid(crc, name):
        if crc not in crcs:
            crcs.append(crc)
            names.append(name)
        return crcs.index(crc)

    regs = {r.tag: region_codes(r, fid) for r in rs.regions}
    code = np.full(GFX_AT + GFX_SIZE, -1, dtype=np.int64)
    for tag, (base, cap) in SDRAM_SLOTS.items():
        if base >= PROG_END or tag not in regs:
            continue
        c = regs[tag]
        assert len(c) <= cap and base + len(c) <= PROG_END, tag
        code[base:base + len(c)] = c

    def get(tag, size):
        c = regs.get(tag, np.zeros(0, dtype=np.int64))
        return np.concatenate([c, np.full(max(0, size - len(c)), -1, dtype=np.int64)])[:size]

    code[GFX_AT:] = layout(rs.machine, get, np.int64(-1))
    return code, crcs, names


def split(code):
    fidx = np.where(code >= 0, code >> 32, FILL)
    fpos = np.where(code >= 0, code & 0xFFFFFFFF, -1 - code)
    return fidx.astype(np.int64), fpos.astype(np.int64)


# ------------------------------------------------------------------ encoder
def _linear_len(fidx, fpos, p):
    """Length of the run at p: one file at consecutive positions, or one
    fill value."""
    n = len(fidx)
    f = fidx[p]
    if f == FILL:
        same = (fidx[p:] == FILL) & (fpos[p:] == fpos[p])
    else:
        same = (fidx[p:] == f) & (fpos[p:] == fpos[p] + np.arange(n - p))
    bad = np.flatnonzero(~same)
    return int(bad[0]) if len(bad) else n - p


def _lanes(fidx, fpos, p, unit):
    """One unit at p as lane groups: [(file, [(lane, pos), ...]), ...], each
    group a run of lanes with consecutive positions in one file, plus
    {lane: fill value}."""
    groups, fills = [], {}
    for i in range(unit):
        f, q = int(fidx[p + i]), int(fpos[p + i])
        if f == FILL:
            fills[i] = q
            continue
        for g in groups:
            if g[0] == f and g[1][-1][1] == q - 1:
                g[1].append((i, q))
                break
        else:
            groups.append((f, [(i, q)]))
    return groups, fills


def _interleave_len(fidx, fpos, p, unit):
    groups, fills = _lanes(fidx, fpos, p, unit)
    n_units = (len(fidx) - p) // unit
    ok = np.ones(n_units, dtype=bool)
    k = np.arange(n_units, dtype=np.int64)
    for f, lanes in groups:
        m = len(lanes)
        for i, q in lanes:
            idx = p + unit * k + i
            ok &= (fidx[idx] == f) & (fpos[idx] == q + m * k)
    for i, v in fills.items():
        idx = p + unit * k + i
        ok &= (fidx[idx] == FILL) & (fpos[idx] == v)
    bad = np.flatnonzero(~ok)
    return (int(bad[0]) if len(bad) else n_units), (groups, fills)


def encode(fidx, fpos):
    """-> list of ('lin', f, pos, n) | ('fill', v, n) | ('il', unit, k, groups, fills)."""
    out = []
    p, n = 0, len(fidx)
    while p < n:
        run = _linear_len(fidx, fpos, p)
        if fidx[p] == FILL and run >= 16:
            out.append(("fill", int(fpos[p]), run))
            p += run
            continue
        if fidx[p] != FILL and run >= 64:
            out.append(("lin", int(fidx[p]), int(fpos[p]), run))
            p += run
            continue
        best = None
        for unit in (2, 4):          # the narrower form when it covers as much
            if p % unit or p + unit > n:
                continue
            k, d = _interleave_len(fidx, fpos, p, unit)
            if k >= 2 and (best is None or k * unit > best[0] * best[1]):
                best = (k, unit, d)
        if best:
            k, unit, (groups, fills) = best
            out.append(("il", unit, k, groups, fills))
            p += k * unit
        elif fidx[p] == FILL:
            out.append(("fill", int(fpos[p]), run))
            p += run
        else:
            out.append(("lin", int(fidx[p]), int(fpos[p]), run))
            p += run
    return out


# ------------------------------------------------------------------ XML
def rom_element(rs, sets, fidx, fpos, crcs, names):
    zips, s = [], rs.name
    while True:
        zips.append(f"{s}.zip")
        if not sets[s].parent:
            break
        s = sets[s].parent
    rom = ET.Element("rom", index="0", zip="|".join(zips), md5="none")

    def part(f, pos, length, mapv=None):
        e = ET.Element("part", name=names[f], crc=crcs[f], offset=f"0x{pos:X}", length=f"0x{length:X}")
        if mapv:
            e.set("map", mapv)
        return e

    def fill(v, cnt, mapv=None):
        e = ET.Element("part", repeat=f"0x{cnt:X}")
        if mapv:
            e.set("map", mapv)
        e.text = f"{v:02X}"
        return e

    for item in encode(fidx, fpos):
        if item[0] == "fill":
            rom.append(fill(item[1], item[2]))
        elif item[0] == "lin":
            rom.append(part(item[1], item[2], item[3]))
        else:
            _, unit, k, groups, fills = item
            il = ET.SubElement(rom, "interleave", output=str(8 * unit))
            for f, lanes in groups:
                nib = ["0"] * unit
                for j, (i, _q) in enumerate(lanes):
                    nib[i] = str(j + 1)
                il.append(part(f, lanes[0][1], len(lanes) * k, "".join(reversed(nib))))
            for i, v in fills.items():
                nib = ["0"] * unit
                nib[i] = "1"
                il.append(fill(v, k, "".join(reversed(nib))))
    return rom


# ------------------------------------------------------------------ assembler (mra_loader.cpp)
def assemble(mra_path, zipdir):
    root = ET.parse(mra_path).getroot()
    rom = next(r for r in root.findall("rom") if r.get("index") == "0")
    zips = [zipfile.ZipFile(zipdir / z) for z in rom.get("zip").split("|") if (zipdir / z).exists()]
    by_crc = {}
    for z in zips:
        for info in z.infolist():
            by_crc.setdefault("%08x" % info.CRC, (z, info))
    cache = {}
    out = bytearray()

    def data_of(part):
        if part.get("name"):
            crc = part.get("crc").lower()
            if crc not in cache:
                z, info = by_crc[crc]
                cache[crc] = z.read(info)
            d = cache[crc]
            off = int(part.get("offset", "0"), 0)
            ln = int(part.get("length", "-1"), 0)
            d = d[off:] if ln <= 0 else d[off:off + ln]
        else:
            d = bytes.fromhex("".join((part.text or "").split()))
        return d * int(part.get("repeat", "1"), 0)

    for el in rom:
        if el.tag == "part":
            out += data_of(el)
        elif el.tag == "interleave":
            unit = int(el.get("output"), 0) // 8
            arrs = []
            for part in el.findall("part"):
                nib = [int(c, 16) for c in reversed(part.get("map").rjust(unit, "0"))]
                d = np.frombuffer(data_of(part), dtype=np.uint8)
                used = [i for i in range(unit) if nib[i]]
                cnt = len(d) // len(used)
                arrs.append((nib, used, d, cnt))
            units = max(a[3] for a in arrs)
            buf = np.zeros(units * unit, dtype=np.uint8)
            for nib, used, d, cnt in arrs:
                per = len(used)
                for i in used:
                    buf[i:cnt * unit:unit] = d[nib[i] - 1:cnt * per:per]
            out += buf.tobytes()
    return bytes(out)


def board_view(stream, setname):
    """What the board reads: srdarwinb's sprite words with the address bits
    0 and 1 swapped (d8_board)."""
    if setname not in SPR_SWAP:
        return stream
    b = bytearray(stream)
    lo, hi = GFX_AT + GFX_BASE["spr"], GFX_AT + GFX_BASE["spr"] + 0x80000
    w = np.frombuffer(bytes(b[lo:hi]), dtype=">u4")
    idx = np.arange(len(w))
    perm = (idx & ~3) | ((idx & 1) << 1) | ((idx >> 1) & 1)
    b[lo:hi] = w[perm].astype(">u4").tobytes()
    return bytes(b)


# ------------------------------------------------------------------ DIP switches from INPUT_PORTS
def _label(s):
    s = s.strip()
    m = re.match(r'DEF_STR\(\s*(\w+)\s*\)', s)
    if m:
        s = m.group(1)
        c = re.match(r"(\d+)C_(\d+)C$", s)
        if c:
            return f"{c.group(1)}C/{c.group(2)}C"
        return s.replace("_", " ")
    return s.strip('"')


def parse_ports(inputs, text=None):
    """{port: [[name, mask, {value: label}, default], ...]} for DSW0/DSW1 of
    INPUT_PORTS_START(inputs), following PORT_INCLUDE and PORT_MODIFY;
    unused switches as [None, mask, {}, default]."""
    text = text or DRIVER.read_text().splitlines()
    i = next(n for n, ln in enumerate(text) if re.match(rf"static INPUT_PORTS_START\(\s*{inputs}\s*\)", ln))
    ports, port, cur = {}, None, None

    def put(entry):
        lst = ports.setdefault(port, [])
        lst[:] = [e for e in lst if not (e[1] & entry[1])]
        lst.append(entry)

    for ln in text[i + 1:]:
        if "INPUT_PORTS_END" in ln:
            break
        code = ln.split("//")[0]
        m = re.search(r"PORT_INCLUDE\(\s*(\w+)\s*\)", code)
        if m:
            for k, v in parse_ports(m.group(1), text).items():
                ports[k] = [list(e) for e in v]
            continue
        m = re.search(r'PORT_(START|MODIFY)\(\s*"(\w+)"', code)
        if m:
            port, cur = m.group(2), None
            continue
        if port not in ("DSW0", "DSW1"):
            continue
        m = re.search(r"PORT_DIPNAME\(\s*(0x\w+)\s*,\s*(0x\w+)\s*,\s*(.+?)\s*\)\s*PORT_DIPLOCATION", code)
        if m:
            mask, dflt = int(m.group(1), 16), int(m.group(2), 16)
            cur = [_label(m.group(3)), mask, {}, dflt & mask]
            put(cur)
            continue
        m = re.search(r"PORT_DIPSETTING\s*\(\s*(0x\w+)\s*,\s*(.+?)\s*\)\s*$", code.strip())
        if m and cur:
            lo = (cur[1] & -cur[1]).bit_length() - 1
            cur[2].setdefault((int(m.group(1), 16) & cur[1]) >> lo, _label(m.group(2)))
            continue
        m = re.search(r"PORT_DIPUNUSED\(\s*(0x\w+)\s*,\s*IP_ACTIVE_LOW", code)
        if m:
            mask = int(m.group(1), 16)
            put([None, mask, {}, mask])
            cur = None
    return ports


def switches(inputs):
    ports = parse_ports(inputs)
    default = 0
    sw = ET.Element("switches")
    for pi, pn in enumerate(("DSW0", "DSW1")):
        for name, mask, vals, dflt in sorted(ports[pn], key=lambda e: e[1] & -e[1]):
            default |= dflt << (8 * pi)
            if name is None:
                continue
            lo = (mask & -mask).bit_length() - 1
            nb = mask.bit_length() - lo
            assert mask == ((1 << nb) - 1) << lo, f"non-contiguous DIP {name}"
            # MAME repeats a label for settings that behave alike; number the
            # repeats so the OSD can tell them apart, the default unnumbered
            dv = dflt >> lo
            order = [dv] + [v for v in range(1 << nb) if v != dv]
            ids, seen = {}, {}
            for v in order:
                lab = vals.get(v, "?")
                seen[lab] = seen.get(lab, 0) + 1
                ids[v] = lab if seen[lab] == 1 else f"{lab} ({seen[lab]})"
            bl = lo + 8 * pi
            bits = str(bl) if nb == 1 else f"{bl},{bl + nb - 1}"
            ET.SubElement(sw, "dip", name=name, bits=bits, ids=",".join(ids[v] for v in range(1 << nb)))
    sw.set("default", f"{default & 0xFF:02X},{default >> 8:02X}")
    return sw, default


# ------------------------------------------------------------------ MRA
def title_of(setname):
    for ln in DRIVER.read_text().splitlines():
        m = re.match(r'GAME\(\s*(\d+),\s*(\w+),.*?,\s*"([^"]*)",\s*"([^"]*)"', ln)
        if m and m.group(2) == setname:
            return m.group(1), m.group(3), m.group(4)
    raise KeyError(setname)


# J1 (Arcade-DEC8.sv): B1, B2, B3, Turn Left, Turn Right, Start, Coin, Service, Pause
BUTTONS = {
    "lastmisn": ("Shoot,Bomb,Select,-,-,Start,Coin,Service,Pause", "A,B,X,-,-,Start,Select,-,-"),
    "gondo":    ("Button 1,Button 2,-,Turn Left,Turn Right,Start,Coin,Service,Pause", "A,B,-,L,R,Start,Select,-,-"),
    "srdarwin": ("Button 1,Button 2,-,-,-,Start,Coin,Service,Pause", "A,B,-,-,-,Start,Select,-,-"),
}


def make(setname, sets):
    rs = sets[setname]
    year, maker, title = title_of(setname)
    kind = "srdarwin" if rs.machine == "srdarwinb" else rs.machine
    code, crcs, names = stream_codes(rs)
    fidx, fpos = split(code)
    root = ET.Element("misterromdescription")
    for tag, val in (("name", title), ("setname", setname), ("rbf", RBF), ("mameversion", "0288"),
                     ("year", year), ("manufacturer", maker), ("players", "2"),
                     ("joystick", "8-way"),
                     ("rotation", "vertical (ccw)" if rs.rot == "ROT270" else "horizontal")):
        ET.SubElement(root, tag).text = val
    sw, _ = switches(rs.inputs)
    root.append(sw)
    nm, df = BUTTONS[kind]
    ET.SubElement(root, "buttons", names=nm, default=df)
    gid = ET.SubElement(root, "rom", index="1")
    ET.SubElement(gid, "part").text = f"{MACHINE_ID[rs.machine]:02X}"
    root.append(rom_element(rs, sets, fidx, fpos, crcs, names))
    ET.indent(root, "    ")
    safe = re.sub(r'[\\/:*?"<>|]', "-", title.replace(": ", " - "))
    outdir = OUTDIR / "_alternatives" / ("_" + PARENT_GAME[rs.parent]) if rs.parent else OUTDIR
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{safe}.mra"
    path.write_text(ET.tostring(root, encoding="unicode") + "\n")
    return path, len(code)


def expected(setname):
    sd = (REGIONS / setname / "sdram.bin").read_bytes()
    gfx = (REGIONS / setname / "gfx.bin").read_bytes()
    return sd[:PROG_END] + bytes(GFX_AT - PROG_END) + gfx


def main(argv):
    sets = parse_driver()
    todo = argv or list(sets)
    bad = 0
    for s in todo:
        path, n = make(s, sets)
        got = assemble(path, ROOT / "roms")
        want = expected(s)
        view = board_view(got, s)
        parts = sum(1 for _ in ET.parse(path).getroot().iter("part"))
        if len(got) == n and view == want:
            (REGIONS / s / "stream.bin").write_bytes(got)
            note = " (board view: sprite word address bits 0/1 swapped)" if s in SPR_SWAP else ""
            print(f"OK   {s:11s} {path.relative_to(ROOT)}: stream {n:#x} bytes = sdram.bin + gfx.bin{note}, "
                  f"{parts} parts")
        else:
            m = min(len(view), len(want))
            first = next((i for i in range(m) if view[i] != want[i]), m)
            print(f"BAD  {s:11s} {path.name}: lengths {len(got):#x}/{len(want):#x}, first diff at {first:#x}")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
