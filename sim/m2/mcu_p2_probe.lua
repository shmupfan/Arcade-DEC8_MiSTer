-- M2 helper: log every i8751 write to P2 (SFR 0xA0, or env P2_ADDR) with the
-- beam position, frames F0-F1 (env P2_F0, P2_F1, P2_OUT), to compare the
-- MCU's SFR write timing with the core's +mcutrace.
local m = manager.machine
local scr = m.screens[":screen"]
local f = 0
local F0 = tonumber(os.getenv("P2_F0") or "20")
local F1 = tonumber(os.getenv("P2_F1") or "22")
local out = assert(io.open(os.getenv("P2_OUT") or "p2.txt", "w"))
local sfr = m.devices[":mcu"].spaces["sfr"]
local A = tonumber(os.getenv("P2_ADDR") or "0xa0")
_G._p2tap = sfr:install_write_tap(A, A, "p2", function(o, d, mask)
  if f >= F0 and f < F1 then
    local pos = scr.frame_period - scr:time_until_pos(0, 0)
    local line = math.floor(pos / scr.scan_period + 1e-6)
    local hpos = math.floor((pos - line * scr.scan_period) / scr.pixel_period + 1e-6)
    out:write(string.format("%d %d %d %02x\n", f, line, hpos, d))
  end
end)
_G._p2n = emu.add_machine_frame_notifier(function()
  f = f + 1
  if f >= F1 then out:close(); m:exit() end
end)
