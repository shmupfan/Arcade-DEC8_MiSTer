# M4 targets (MiSTer board, SDRAM, MRA). Included by sim/Makefile, or run on
# its own from sim/:  make -f m4.mk <target>
#
#   make m4-mra       generate every MRA, prove each one rebuilds the ROM
#                     stream byte for byte (Main_MiSTer loader rules) and
#                     write build/regions/<set>/stream.bin (what the board
#                     receives on ioctl index 0)
#   make m4-lint      Verilator -Wall on d8_sdram and d8_board
#   make m4-build     board harness (d8_board: d8_sys + d8_sdram + ioctl +
#                     SDRAM model)
#   make m4-ref       M2 harness rebuilt from the current RTL (FREE_TIMING 0,
#                     C++ ROM models) and run for the M4 gate runs: the
#                     byte-for-byte reference
#   make m4-boot      the same runs through the board (3 at a time, nice 15)
#   make m4-compare   board vs M2 reference, file by file
#
# sim/build/regions/<set>/{sdram,gfx}.bin come from `make regions` and
# `make m1-gfx` (M0, M1).

PY        ?= python3
VERILATOR ?= verilator
M4DIR     ?= build/m4

M4SYS := ../rtl/d8_sys.sv ../rtl/d8_mcu.sv ../rtl/d8_video.sv ../rtl/d8_snapram.sv ../rtl/d8_dpram.sv \
         ../rtl/d8_fifo.sv ../rtl/vendor/mc6809i/mc6809i.v $(wildcard ../rtl/vendor/jt8051/jt8051*.v) \
         ../rtl/d8_snd.sv $(wildcard ../rtl/vendor/jt65c02/jt65c02*.v) $(wildcard ../rtl/vendor/jt03/hdl/*.v) \
         $(filter-out %/jtopl.v,$(wildcard ../rtl/vendor/jtopl/hdl/jtopl*.v)) ../rtl/vendor/jtopl/hdl/jtopl.v
M4INC := -I../rtl/vendor/jt8051 -I../rtl/vendor/jt65c02 -I../rtl/vendor/jt03/hdl -I../rtl/vendor/jtopl/hdl \
         -DJT8051_UCFILE='"$(abspath ../rtl/vendor/jt8051/jt8051.uc)"' \
         -DJT65C02_UCFILE='"$(abspath ../rtl/vendor/jt65c02/deco222.uc)"'
M4BRTL := $(M4SYS) ../rtl/d8_sdram.sv ../rtl/d8_board.sv m4/sdram_model.sv m4/tb_board.sv
M4BBIN := $(M4DIR)/board_obj/Vtb_board
M4RBIN := $(M4DIR)/ref_obj/Vd8_sys

.PHONY: m4-mra m4-lint m4-shell-lint m4-rotary m4-build m4-ref m4-boot m4-compare

m4-mra:
	cd .. && $(PY) tools/make_mra.py

m4-lint:
	$(VERILATOR) --lint-only -Wall -Wno-MULTIDRIVEN --top-module d8_sdram ../rtl/d8_sdram.sv
	$(VERILATOR) --lint-only -Wall -Wno-MULTIDRIVEN -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-fatal \
	  $(M4INC) -DSIMULATION --top-module d8_board $(M4SYS) ../rtl/d8_sdram.sv ../rtl/d8_board.sv 2>&1 \
	  | grep -E "%(Warning|Error)" | grep -E "d8_board|d8_sdram" ; true

$(M4BBIN): $(M4BRTL) m4/tb_board.cpp
	mkdir -p $(M4DIR)
	nice -n 15 $(VERILATOR) --cc --exe --build -O3 --x-assign fast --x-initial fast -Wno-fatal -Wno-lint -Wno-style \
	  -Wno-UNOPTFLAT -Wno-SYNCASYNCNET -Wno-MULTIDRIVEN --top-module tb_board $(M4INC) -DSIMULATION \
	  -Mdir $(M4DIR)/board_obj -o Vtb_board -CFLAGS "-O3 -march=native" -j 4 $(M4BRTL) m4/tb_board.cpp

$(M4RBIN): $(M4SYS) m2/tb_sys.cpp
	mkdir -p $(M4DIR)
	nice -n 15 $(VERILATOR) --cc --exe --build -O3 --x-assign fast --x-initial fast -Wno-fatal -Wno-lint -Wno-style \
	  -Wno-UNOPTFLAT -Wno-SYNCASYNCNET --top-module d8_sys $(M4INC) -DSIMULATION \
	  -Mdir $(M4DIR)/ref_obj -o Vd8_sys -CFLAGS "-O3 -march=native" -j 4 $(M4SYS) m2/tb_sys.cpp

m4-build: $(M4BBIN) $(M4RBIN)

# ---------------------------------------------------------------- M4 gate
# run:set:frames. Captures: every 20th frame plus 1-60 (power-on), all RAM
# dumps at each; inputs from the MAME oracle where the run has them.
M4OUT  := $(M4DIR)/gate
M4RUNS := lm_attract:lastmisn:1200 lm_play:lastmisn:1500 go_attract:gondo:1200 go_play:gondo:1200 \
          sr_attract:srdarwin:1200 sr_play:srdarwin:1200 clone_srdarwinb:srdarwinb:900
M4JOBS ?= 3

m4-ref: $(M4RBIN)
	$(PY) m4/run_gate.py ref --jobs $(M4JOBS) $(M4RUNS)

m4-boot: $(M4BBIN)
	$(PY) m4/run_gate.py board --jobs $(M4JOBS) $(M4RUNS)

m4-compare:
	$(PY) m4/run_gate.py compare $(M4RUNS)

# The MiSTer shell (Arcade-DEC8.sv) with the framework stubs (m4/lint_stubs.sv)
m4-shell-lint:
	$(VERILATOR) --lint-only -Wall -Wno-fatal -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-MULTIDRIVEN -Wno-PINCONNECTEMPTY \
	  -DLINT_STUBS -DMISTER_FB=1 -DSIMULATION -I.. -I../sys $(M4INC) --top-module emu m4/lint_stubs.sv \
	  ../Arcade-DEC8.sv ../sys/video_freak.sv ../sys/math.sv ../rtl/d8_rotary.sv ../rtl/d8_board.sv ../rtl/d8_sdram.sv $(M4SYS) 2>&1 \
	  | grep -E "^%(Error|Warning)" | grep -E "Error|Arcade-DEC8|d8_board|d8_sdram|d8_rotary" ; true

# d8_rotary (Gondomania rotary from buttons, spinner, paddle) unit test
m4-rotary:
	$(VERILATOR) --cc --exe --build -Wno-fatal -GCLK_HZ=1000 --top-module d8_rotary \
	  -Mdir $(M4DIR)/rotary_obj ../rtl/d8_rotary.sv m4/rotary/tb_rotary.cpp > /dev/null
	$(M4DIR)/rotary_obj/Vd8_rotary
