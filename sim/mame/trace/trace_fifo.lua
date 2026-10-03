local m = manager.machine
local f = 0
local N = tonumber(os.getenv("TRACE_FRAMES") or "3000")
_G._tcb = emu.add_machine_frame_notifier(function()
  f = f + 1
  if f == 1 then m.debugger:command("trace " .. os.getenv("TRACE_FIFO") .. ",maincpu,noloop") end
  if f == N then m.debugger:command("trace off,maincpu"); m:exit() end
end)
