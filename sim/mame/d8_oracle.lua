-- DEC8 (Last Mission / Gondomania / SRD: Super Real Darwin) MAME oracle:
-- write logs plus per-frame state dumps (PLAN M0.4).
--
-- Usage (normally via sim/Makefile, which calls sim/mame/run_mame.sh):
--   DUMP_DIR=<outdir> DUMP_FRAMES=<list> TOTAL=<n> \
--     sim/mame/run_mame.sh <set> sim/mame/d8_oracle.lua
--
-- Environment:
--   DUMP_DIR     output directory (default sim/mame/out/<set>)
--   DUMP_FRAMES  comma list of frames and ranges "a-b" or "a-b/step" to dump
--   TOTAL        last frame of the run (default: last dump frame)
--   NO_SNAP      1 = skip snap.png
--   HEAVY_LOG    1 = log every palette/sprite/tile RAM write row by row
--                (default: per-frame per-class summaries only)
--   INPUTS       "frame:PORT:Field name:value;..." input events
--   FIELDS       "PORT:Field name:value;..." DIP user values at start
--
-- Frame numbering (as in the Dooyong, 1945k III and Tecmo 16 oracles): the
-- frame notifier runs inside screen vblank_begin (line 248, dec8.cpp
-- set_screen_raw_params L1977-1981), after MAME has rendered the frame. The
-- driver never forces a partial update (no update_partial in dec8.cpp or
-- dec8_v.cpp), so the RAM, scroll and flip state read here are exactly what
-- MAME rendered frame N from, except for writes that land at the very
-- instant of vblank (none expected; the write log shows each write's line).
--
-- Beam position: screen:time_until_pos (MAME 0.288 Lua has no
-- screen:vpos()), in MAME's 384 x 272 geometry, visible lines 8-247.
-- scan_frame = the frame whose scan-out (or the vblank after it) the write
-- falls in.
--
-- Interrupt entries are counted per frame with read taps on the 6809
-- vectors (FIRQ 0xfff6, IRQ 0xfff8, NMI 0xfffc): the CPU reads the vector
-- high byte once per taken interrupt (also on any data read there, none in
-- these programs as far as the logs show).
--
-- Byte order of every .bin: as in RAM (8-bit), sprite buffer words of
-- lastmisn/gondo high byte first.
-- All tap and notifier handles are pinned in _G.

local m = manager.machine
local setname = emu.romname()
local outdir = os.getenv("DUMP_DIR") or ("sim/mame/out/" .. setname)
os.execute("mkdir -p '" .. outdir .. "'")

local function parse_frames(s)
  local t, maxf = {}, 0
  for tok in string.gmatch(s or "", "([^,]+)") do
    local a, b, st = tok:match("^(%d+)-(%d+)/(%d+)$")
    if not a then a, b = tok:match("^(%d+)-(%d+)$"); st = 1 end
    if a then
      for f = tonumber(a), tonumber(b), tonumber(st) do t[f] = true; if f > maxf then maxf = f end end
    elseif tonumber(tok) then
      t[tonumber(tok)] = true; if tonumber(tok) > maxf then maxf = tonumber(tok) end
    end
  end
  return t, maxf
end

local dump_frames, maxdump = parse_frames(os.getenv("DUMP_FRAMES") or "")
local no_snap = os.getenv("NO_SNAP") == "1"
local total = tonumber(os.getenv("TOTAL") or "0")
if total == 0 then total = maxdump end
if total == 0 then total = 600 end
local heavy = os.getenv("HEAVY_LOG") == "1"

local MACHINE = {
  lastmisn = "lastmisn", lastmisnu6 = "lastmisn", lastmisnu5 = "lastmisn", lastmisnj = "lastmisn",
  gondo = "gondo", gondou = "gondo", makyosen = "gondo",
  srdarwin = "srdarwin", srdarwinj = "srdarwin", srdarwinb = "srdarwinb",
}
local machine_name = MACHINE[setname]
assert(machine_name, "unknown set " .. setname)
local is_sr = machine_name == "srdarwin" or machine_name == "srdarwinb"

-- Address map of each machine (dec8.cpp, line numbers of MAME 0.288).
-- main: classes of main CPU writes; sub: lastmisn sub CPU (same video map).
local MAPS = {
  lastmisn = {   -- lastmisn_map L300-326, lastmisn_sub_map L328-350
    { 0x1000, 0x13ff, "pal" }, { 0x1400, 0x17ff, "palx" },
    { 0x1800, 0x1800, "irq_sub_off" }, { 0x1801, 0x1801, "irq_main_off" },
    { 0x1802, 0x1802, "firq_off" }, { 0x1803, 0x1803, "irq_main_on" },
    { 0x1804, 0x1804, "irq_sub_on" }, { 0x1805, 0x1805, "spr_buffer" },
    { 0x1807, 0x1807, "flip" }, { 0x1809, 0x1809, "scrollx" }, { 0x180b, 0x180b, "scrolly" },
    { 0x180c, 0x180c, "soundlatch" }, { 0x180d, 0x180d, "control" },
    { 0x180e, 0x180e, "mcu_hi" }, { 0x180f, 0x180f, "mcu_lo" },
    { 0x2000, 0x27ff, "fixram" }, { 0x2800, 0x2fff, "spr" }, { 0x3800, 0x3fff, "bgram" },
    { 0x4000, 0xffff, "romw" },
  },
  gondo = {      -- gondo_map L425-447
    { 0x1800, 0x1fff, "fixram" }, { 0x2000, 0x27ff, "bgram" },
    { 0x2800, 0x2bff, "pal" }, { 0x2c00, 0x2fff, "palx" }, { 0x3000, 0x37ff, "spr" },
    { 0x3810, 0x3810, "soundlatch" }, { 0x3818, 0x382f, "scroll" }, { 0x3830, 0x3830, "bank" },
    { 0x383a, 0x383a, "mcu_hi" }, { 0x383b, 0x383b, "mcu_lo" },
    { 0x4000, 0xffff, "romw" },
  },
  srdarwin = {   -- srdarwin main_map L565-587
    { 0x0600, 0x07ff, "spr" }, { 0x0800, 0x0fff, "fixram" }, { 0x1400, 0x17ff, "bgram" },
    { 0x1800, 0x1800, "mcu_hi" }, { 0x1801, 0x1801, "mcu_lo" }, { 0x1803, 0x1803, "w1803" },
    { 0x1804, 0x1804, "spr_buffer" }, { 0x1805, 0x1806, "control" },
    { 0x2000, 0x2000, "soundlatch" }, { 0x2001, 0x2001, "flip" },
    { 0x2800, 0x288f, "pal" }, { 0x3000, 0x308f, "palx" },
    { 0x4000, 0xffff, "romw" },
  },
}
MAPS.srdarwinb = MAPS.srdarwin
local HEAVY = { pal = true, palx = true, spr = true, fixram = true, bgram = true }

local main = m.devices[":maincpu"].spaces["program"]
local sub = (machine_name == "lastmisn") and m.devices[":sub"].spaces["program"] or nil
local screen = m.screens[":screen"]

---------------------------------------------------------------------------
-- items
---------------------------------------------------------------------------
local function item_of(tag, name)
  local d = m.devices[tag]
  if not d then return nil end
  local idx = d.items[name]
  if not idx then return nil end
  return emu.item(idx)
end

local it_scroll = assert(item_of(":", "0/m_scroll"))
local it_flipx = assert(item_of(":", "0/m_flip_screen_x"))
local it_flipy = assert(item_of(":", "0/m_flip_screen_y"))
local it_vmaxy = assert(item_of(":screen", "0/m_visarea.max_y"))
local it_vminy = assert(item_of(":screen", "0/m_visarea.min_y"))
local it_vminx = assert(item_of(":screen", "0/m_visarea.min_x"))
local it_vmaxx = assert(item_of(":screen", "0/m_visarea.max_x"))
local it_sprbuf
if is_sr then
  it_sprbuf = assert(item_of(":spriteram", "0/m_buffered"))       -- 512 bytes
else
  it_sprbuf = assert(item_of(":", "0/m_buffered_spriteram16"))    -- 1024 words
end
local it_krnflip = item_of(":spritegen_krn", "0/m_flip_screen")
local it_bank = item_of(":", "0/m_bank_data")

---------------------------------------------------------------------------
-- timing
---------------------------------------------------------------------------
local FRAME_S = screen.frame_period
local LINE_S = screen.scan_period
local PIX_S = screen.pixel_period
local VTOTAL = math.floor(FRAME_S / LINE_S + 0.5)
local HTOTAL = math.floor(LINE_S / PIX_S + 0.5)
local VB_LINE = it_vmaxy:read(0) + 1     -- first line after the visible area (248)
local VIS_MIN = it_vminy:read(0)         -- first visible line (8)
local frame = 0

local function beam()
  local pos = FRAME_S - screen:time_until_pos(0, 0)
  local line = math.floor(pos / LINE_S + 1e-6)
  if line > VTOTAL - 1 then line = VTOTAL - 1 end
  local hpos = math.floor((pos - line * LINE_S) / PIX_S + 1e-6)
  if hpos < 0 then hpos = 0 end
  -- the notifier is at line VB_LINE: lines >= VB_LINE belong to the vblank
  -- after frame `frame`, lines < VB_LINE to the scan-out of frame+1
  local scan = (line >= VB_LINE) and frame or (frame + 1)
  return line, hpos, scan
end

---------------------------------------------------------------------------
-- logs
---------------------------------------------------------------------------
local wlog = assert(io.open(outdir .. "/writes.csv", "w"))
wlog:write("frame,line,hpos,scan_frame,visible,cpu,class,addr,data\n")
local hits = {}
local summ = {}
local sumlog = assert(io.open(outdir .. "/heavy_summary.csv", "w"))
sumlog:write("frame,class,count,visible_count,first_line,last_line\n")

local function is_visible(line) return line >= VIS_MIN and line < VB_LINE end

-- palette entries written since power-on (pal or ext byte)
local pal_written = {}
local PALBASE = ({ lastmisn = 0x1000, gondo = 0x2800, srdarwin = 0x2800, srdarwinb = 0x2800 })[machine_name]
local PALXBASE = ({ lastmisn = 0x1400, gondo = 0x2c00, srdarwin = 0x3000, srdarwinb = 0x3000 })[machine_name]

local function logw(cpu, class, addr, data)
  if class == "pal" then pal_written[addr - PALBASE] = true end
  if class == "palx" then pal_written[addr - PALXBASE] = true end
  hits[class] = (hits[class] or 0) + 1
  local line, hpos, scan = beam()
  local vis = is_visible(line)
  if HEAVY[class] then
    local key = class
    local s = summ[key]
    if not s then s = { n = 0, v = 0, first = nil, last = nil }; summ[key] = s end
    s.n = s.n + 1
    if vis then s.v = s.v + 1 end
    if not s.first then s.first = line end
    s.last = line
    if not heavy then return end
  end
  wlog:write(string.format("%d,%d,%d,%d,%d,%s,%s,%04x,%x\n",
    frame, line, hpos, scan, vis and 1 or 0, cpu, class, addr, data))
end

_G._d8_taps = {}
local function install(space, cpu)
  for _, e in ipairs(MAPS[machine_name]) do
    local lo, hi, class = e[1], e[2], e[3]
    if not (cpu == "sub" and (class == "scrollx" or class == "scrolly" or class == "control")) then
      local h = space:install_write_tap(lo, hi, cpu .. "_" .. class, function(offset, data, mask)
        logw(cpu, class, offset, data)
      end)
      table.insert(_G._d8_taps, h)
    end
  end
end
install(main, "main")
if sub then install(sub, "sub") end

-- interrupt entries per frame (vector high byte reads)
local ints = {}
local function vec(space, cpu, addr, name)
  local h = space:install_read_tap(addr, addr, cpu .. "_" .. name, function(offset, data, mask)
    local k = cpu .. "_" .. name
    ints[k] = (ints[k] or 0) + 1
    hits[k] = (hits[k] or 0) + 1
  end)
  table.insert(_G._d8_taps, h)
end
for _, sp in ipairs({ { main, "main" }, { sub, "sub" } }) do
  if sp[1] then
    vec(sp[1], sp[2], 0xfff6, "firq")
    vec(sp[1], sp[2], 0xfff8, "irq")
    vec(sp[1], sp[2], 0xfffc, "nmi")
  end
end

---------------------------------------------------------------------------
-- state dump
---------------------------------------------------------------------------
local function item_bytes(it)
  local parts = {}
  local char = string.char
  for i = 0, it.count - 1 do
    local v = it:read(i)
    if it.size == 1 then parts[#parts + 1] = char(v & 0xff)
    else parts[#parts + 1] = char((v >> 8) & 0xff, v & 0xff) end
  end
  return table.concat(parts)
end

local function share_bytes(tag)
  local s = m.memory.shares[tag]
  local parts = {}
  local char = string.char
  for a = 0, s.size - 1 do parts[#parts + 1] = char(s:read_u8(a)) end
  return table.concat(parts)
end

local function wfile(path, data)
  local f = assert(io.open(path, "wb"))
  f:write(data)
  f:close()
end

local function sprite_count(buf)
  -- visible sprite entries, as the M0 sprite statistics count them
  local n = 0
  if is_sr then
    for offs = 0, 0x1fc, 4 do
      local b0, b1, b3 = buf:byte(offs + 1), buf:byte(offs + 2), buf:byte(offs + 4)
      local code = b3 + ((b1 & 0xe0) << 3)
      if code ~= 0 and b0 ~= 0xf8 then n = n + 1 end
    end
  else
    for w = 0, 0x3fc, 4 do
      local d0 = (buf:byte(2 * w + 1) << 8) | buf:byte(2 * w + 2)
      local d1 = (buf:byte(2 * w + 3) << 8) | buf:byte(2 * w + 4)
      if (d0 & 0x8000) ~= 0 and (d1 & 1) ~= 0 then n = n + 1 end
    end
  end
  return n
end

local pending_pixels = nil

local function dump_frame(n, sprbuf)
  local d = string.format("%s/frames/%06d", outdir, n)
  os.execute("mkdir -p '" .. d .. "'")
  pending_pixels = d
  wfile(d .. "/palette.bin", share_bytes(":palette"))
  wfile(d .. "/palette_ext.bin", share_bytes(":palette_ext"))
  local pal = m.palettes[":palette"]
  local pc = {}
  for i = 0, pal.entries - 1 do
    local c = pal:pen_color(i)
    pc[#pc + 1] = string.char(c & 0xff, (c >> 8) & 0xff, (c >> 16) & 0xff, (c >> 24) & 0xff)
  end
  wfile(d .. "/pens.bin", table.concat(pc))
  local pw = {}
  for i = 0, pal.entries - 1 do pw[#pw + 1] = string.char(pal_written[i] and 1 or 0) end
  wfile(d .. "/palette_written.bin", table.concat(pw))
  wfile(d .. "/fixram.bin", share_bytes(":videoram"))
  wfile(d .. "/bgram.bin", share_bytes(":bg_ram"))
  wfile(d .. "/spr_live.bin", share_bytes(":spriteram"))
  wfile(d .. "/spr_buf.bin", sprbuf)
  local js = {}
  js[#js + 1] = string.format('  "set": "%s"', setname)
  js[#js + 1] = string.format('  "machine": "%s"', machine_name)
  js[#js + 1] = string.format('  "frame": %d', n)
  js[#js + 1] = string.format('  "width": %d', screen.width)
  js[#js + 1] = string.format('  "height": %d', screen.height)
  js[#js + 1] = string.format('  "vis_min_y": %d', VIS_MIN)
  -- the visible area of this frame (driver_device::updateflip() mirrors it
  -- inside the 384 x 272 total when the screen is flipped)
  js[#js + 1] = string.format('  "visarea": [%d, %d, %d, %d]', it_vminx:read(0), it_vmaxx:read(0), it_vminy:read(0), it_vmaxy:read(0))
  js[#js + 1] = string.format('  "htotal": %d', HTOTAL)
  js[#js + 1] = string.format('  "vtotal": %d', VTOTAL)
  js[#js + 1] = string.format('  "scroll": [%d, %d, %d, %d]', it_scroll:read(0), it_scroll:read(1), it_scroll:read(2), it_scroll:read(3))
  js[#js + 1] = string.format('  "flip_x": %d', it_flipx:read(0))
  js[#js + 1] = string.format('  "flip_y": %d', it_flipy:read(0))
  js[#js + 1] = string.format('  "krn_flip": %d', it_krnflip and it_krnflip:read(0) or -1)
  js[#js + 1] = string.format('  "bank_data": %d', it_bank and it_bank:read(0) or -1)
  js[#js + 1] = string.format('  "sprites": %d', sprite_count(sprbuf))
  wfile(d .. "/state.json", "{\n" .. table.concat(js, ",\n") .. "\n}\n")
  if not no_snap then screen:snapshot(d .. "/snap.png") end
end

---------------------------------------------------------------------------
-- per-frame trace (every frame)
---------------------------------------------------------------------------
local ftrace = assert(io.open(outdir .. "/frames.csv", "w"))
ftrace:write("frame,scroll0,scroll1,scroll2,scroll3,flip,krn_flip,sprites,sprbuf_changed,main_nmi,main_irq,main_firq,sub_irq,sub_firq\n")
local prev_sprbuf = ""

---------------------------------------------------------------------------
-- inputs and DIP fields
---------------------------------------------------------------------------
local events = {}
for tok in string.gmatch(os.getenv("INPUTS") or "", "([^;]+)") do
  local f, port, field, val = tok:match("^%s*(%d+):([^:]+):([^:]+):(%d+)%s*$")
  if f then
    local ev = events[tonumber(f)] or {}
    ev[#ev + 1] = { port, field, tonumber(val) }
    events[tonumber(f)] = ev
  end
end
local ilog = assert(io.open(outdir .. "/inputs.csv", "w"))
ilog:write("frame,port,field,value\n")
local function field_of(port, name)
  local p = m.ioport.ports[":" .. port]
  assert(p, "no port " .. port)
  local fl = p.fields[name]
  assert(fl, "no field '" .. name .. "' in " .. port)
  return fl
end
for tok in string.gmatch(os.getenv("FIELDS") or "", "([^;]+)") do
  local port, field, val = tok:match("^%s*([^:]+):([^:]+):(%d+)%s*$")
  if port then
    field_of(port, field).user_value = tonumber(val)
    ilog:write(string.format("0,%s,%s,user_value=%s\n", port, field, val))
  end
end

---------------------------------------------------------------------------
-- frame notifier
---------------------------------------------------------------------------
local vpos_check = "not checked"
_G._d8_frame = emu.add_machine_frame_notifier(function()
  frame = frame + 1
  if frame == 2 then
    local l, h = beam()
    vpos_check = string.format("beam at notifier: line %d hpos %d (expected %d, 0); visible %dx%d from line %d; total %dx%d; screen frame_number %d at notifier %d",
      l, h, VB_LINE, screen.width, screen.height, VIS_MIN, HTOTAL, VTOTAL, screen:frame_number(), frame)
  end
  for class, s in pairs(summ) do
    sumlog:write(string.format("%d,%s,%d,%d,%d,%d\n", frame - 1, class, s.n, s.v, s.first, s.last))
  end
  summ = {}
  local cur = item_bytes(it_sprbuf)
  ftrace:write(string.format("%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\n", frame,
    it_scroll:read(0), it_scroll:read(1), it_scroll:read(2), it_scroll:read(3),
    it_flipx:read(0), it_krnflip and it_krnflip:read(0) or -1, sprite_count(cur),
    (cur ~= prev_sprbuf) and 1 or 0,
    ints.main_nmi or 0, ints.main_irq or 0, ints.main_firq or 0, ints.sub_irq or 0, ints.sub_firq or 0))
  ints = {}
  if pending_pixels then
    wfile(pending_pixels .. "/screen.argb", (screen:pixels()))
    wfile(pending_pixels .. "/palette_next.bin", share_bytes(":palette") .. share_bytes(":palette_ext"))
    pending_pixels = nil
  end
  if dump_frames[frame] then dump_frame(frame, cur) end
  prev_sprbuf = cur
  local ev = events[frame]
  if ev then
    for _, e in ipairs(ev) do
      field_of(e[1], e[2]):set_value(e[3])
      ilog:write(string.format("%d,%s,%s,%d\n", frame, e[1], e[2], e[3]))
    end
  end
  if frame > total then
    wlog:close(); sumlog:close(); ftrace:close(); ilog:close()
    local s = assert(io.open(outdir .. "/summary.txt", "w"))
    s:write(string.format("set %s machine %s frames %d\n", setname, machine_name, frame))
    s:write(vpos_check .. "\n")
    local keys = {}
    for k in pairs(hits) do keys[#keys + 1] = k end
    table.sort(keys)
    for _, k in ipairs(keys) do s:write(string.format("tap %s hits %d\n", k, hits[k])) end
    s:write(string.format("taps installed %d\n", #_G._d8_taps))
    s:close()
    m:exit()
  end
end)

print(string.format("d8_oracle: %s (%s) total %d frames -> %s", setname, machine_name, total, outdir))
