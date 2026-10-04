derive_pll_clocks
derive_clock_uncertainty

# --------------------------------------------------------------------------
# Multicycle paths, each from a core whose registers only change on a clock
# enable several 96 MHz clocks apart (docs/m4_findings.md 7 has the proof
# for each and the endpoints that use the relaxation). Hold is kept at the
# launch edge (-hold N-1). Instance names: d8_board.u_sys.{u_main, u_sub,
# u_mcu.u_mcu, u_snd.u_cpu, u_snd.u_ym, u_snd.u_opl}.
# --------------------------------------------------------------------------

# mc6809i (main and sub 6809): every register is enabled by cen_E (bus
# phase P-1) or cen_Q (3P/4-1), P = 32 (Gondomania) or 64 clocks, so two
# updates are at least P/4 = 8 clocks apart. Inside the core: 4 clocks.
# Into the rest of the board the first register that uses a CPU output is
# loaded at bus phase 1 (program ROM request, d8_sys), 2 clocks after
# cen_E; the access slots are at phases 12 and 20 and the data input is
# taken at cen_E.
foreach cpu {u_main u_sub} {
  set_multicycle_path -setup -end 2 -from [get_registers "emu|board|u_sys|$cpu|*"]
  set_multicycle_path -hold  -end 1 -from [get_registers "emu|board|u_sys|$cpu|*"]
  set_multicycle_path -setup -end 4 -from [get_registers "emu|board|u_sys|$cpu|*"] -to [get_registers "emu|board|u_sys|$cpu|*"]
  set_multicycle_path -hold  -end 3 -from [get_registers "emu|board|u_sys|$cpu|*"] -to [get_registers "emu|board|u_sys|$cpu|*"]
}

# jt8051 (i8751): every register is enabled by the MCU cen, every 12 clocks
# (jt8051 itself requires at least one idle clock between enables). Its
# outputs are used by registers enabled by the same cen (ROM and RAM reads,
# d8_mcu), by the ROM address pipeline register (read at the next cen), and
# by the port glue in d8_sys, which only loads on an SFR write (cen AND
# write).
set_multicycle_path -setup -end 4 -from [get_registers {emu|board|u_sys|u_mcu|u_mcu|*}]
set_multicycle_path -hold  -end 3 -from [get_registers {emu|board|u_sys|u_mcu|u_mcu|*}]

# jt65c02 (sound CPU): every register is enabled by cpu_cen, every 16
# clocks (or the ALU's half-carry pipeline register, read at the next
# enable). Its bus outputs reach the YM2203, the OPL, the RAM, the latch
# and the decode only through the write event (cpu_cen AND write) or the
# memory address registers, read at the next enable.
set_multicycle_path -setup -end 4 -from [get_registers {emu|board|u_sys|u_snd|u_cpu|*}]
set_multicycle_path -hold  -end 3 -from [get_registers {emu|board|u_sys|u_snd|u_cpu|*}]

# jt03 (YM2203) and jtopl (OPL) inside each chip: registers enabled by the
# chip's enable (every 64 / 32 clocks) or by the CPU write event (on
# cpu_cen, every 16 clocks, a superset of both chip enables).
set_multicycle_path -setup -end 2 -from [get_registers {emu|board|u_sys|u_snd|u_ym|*}]  -to [get_registers {emu|board|u_sys|u_snd|u_ym|*}]
set_multicycle_path -hold  -end 1 -from [get_registers {emu|board|u_sys|u_snd|u_ym|*}]  -to [get_registers {emu|board|u_sys|u_snd|u_ym|*}]
set_multicycle_path -setup -end 2 -from [get_registers {emu|board|u_sys|u_snd|u_opl|*}] -to [get_registers {emu|board|u_sys|u_snd|u_opl|*}]
set_multicycle_path -hold  -end 1 -from [get_registers {emu|board|u_sys|u_snd|u_opl|*}] -to [get_registers {emu|board|u_sys|u_snd|u_opl|*}]

# The machine byte and the DIP switches are loaded from the MRA while the
# core is held in reset and are static during play.
set_false_path -from [get_registers {emu|board|mbyte*}]
set_false_path -from [get_registers {emu|board|dsw0*}]
set_false_path -from [get_registers {emu|board|dsw1*}]
