-- As trace_fifo.lua (main CPU trace into a FIFO for N frames), with the
-- oracle's INPUTS ("frame:PORT:Field name:value;...") applied at the frame
-- notifier, so a gameplay capture's inputs can be traced (R4 on gameplay).
local m = manager.machine
local f = 0
local N = tonumber(os.getenv("TRACE_FRAMES") or "3000")
local events = {}
for tok in string.gmatch(os.getenv("INPUTS") or "", "([^;]+)") do
  local fr, port, field, val = tok:match("^%s*(%d+):([^:]+):([^:]+):(%d+)%s*$")
  if fr then
    local ev = events[tonumber(fr)] or {}
    ev[#ev + 1] = { port, field, tonumber(val) }
    events[tonumber(fr)] = ev
  end
end
_G._tcb = emu.add_machine_frame_notifier(function()
  f = f + 1
  if f == 1 then m.debugger:command("trace " .. os.getenv("TRACE_FIFO") .. ",maincpu,noloop") end
  local ev = events[f]
  if ev then
    for _, e in ipairs(ev) do m.ioport.ports[":" .. e[1]].fields[e[2]]:set_value(e[3]) end
  end
  if f == N then m.debugger:command("trace off,maincpu"); m:exit() end
end)
