-- MAME debugger trace of one or more CPUs over a frame window (M2 debugging):
-- TRACE_F0 / TRACE_F1 frame notifier numbers, TRACE_CPUS "maincpu,sub,mcu",
-- TRACE_DIR output directory (one <cpu>.tr file each). Run with -debug
-- -debugger none. INPUTS ("frame:PORT:Field:value;...") as d8_oracle.lua.
local m = manager.machine
local f = 0
local F0 = tonumber(os.getenv("TRACE_F0") or "1")
local F1 = tonumber(os.getenv("TRACE_F1") or "2")
local dir = os.getenv("TRACE_DIR") or "."
local cpus = {}
for c in string.gmatch(os.getenv("TRACE_CPUS") or "maincpu", "([^,]+)") do cpus[#cpus + 1] = c end
local events = {}
for tok in string.gmatch(os.getenv("INPUTS") or "", "([^;]+)") do
  local fr, port, field, val = tok:match("^%s*(%d+):([^:]+):([^:]+):(%d+)%s*$")
  if fr then
    local ev = events[tonumber(fr)] or {}
    ev[#ev + 1] = { port, field, tonumber(val) }
    events[tonumber(fr)] = ev
  end
end
_G._twin = emu.add_machine_frame_notifier(function()
  f = f + 1
  local ev = events[f]
  if ev then
    for _, e in ipairs(ev) do m.ioport.ports[":" .. e[1]].fields[e[2]]:set_value(e[3]) end
  end
  if f == F0 then
    for _, c in ipairs(cpus) do m.debugger:command("trace " .. dir .. "/" .. c .. ".tr," .. c .. ",noloop") end
  end
  if f == F1 then
    for _, c in ipairs(cpus) do m.debugger:command("trace off," .. c) end
    m:exit()
  end
end)
