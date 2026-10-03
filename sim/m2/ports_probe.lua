-- M2 helper: every input port's value at the frame notifier (inside vblank,
-- line 248) of frame 3, and at a write to video RAM during the visible scan
-- (outside vblank), to see how MAME presents the custom vblank bits and the
-- DIP defaults per set. Prints one line per port and exits.
local m = manager.machine
local frame, done_vis = 0, false
local out = {}
local function readall(tag)
  local names = {}
  for n, _ in pairs(m.ioport.ports) do names[#names + 1] = n end
  table.sort(names)
  for _, n in ipairs(names) do
    out[#out + 1] = string.format("%s %s %02x", tag, n, m.ioport.ports[n]:read() & 0xff)
  end
end
local scr = m.screens[":screen"]
local main = m.devices[":maincpu"].spaces["program"]
_G._probe_tap = main:install_write_tap(0x0000, 0x3fff, "probe", function(o, d, mask)
  if frame >= 3 and not done_vis then
    local pos = scr.frame_period - scr:time_until_pos(0, 0)
    local line = math.floor(pos / scr.scan_period + 1e-6)
    if line >= 20 and line < 200 then
      readall("vis_line" .. line)
      done_vis = true
    end
  end
end)
_G._probe_n = emu.add_machine_frame_notifier(function()
  frame = frame + 1
  if frame == 3 then readall("vblank") end
  if frame >= 40 then
    for _, l in ipairs(out) do print(l) end
    m:exit()
  end
end)
