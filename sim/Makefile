# DEC8 (Last Mission / Gondomania / SRD: Super Real Darwin) simulation and
# oracle harness.
#
# M0 targets (MAME 0.288 on PATH, or MAME=...; ROM zips in ../roms):
#   make roms-check      CRC/SHA1/size of all 10 sets vs the table generated
#                        from reference/mame/v0288/dec8.cpp
#   make regions         rebuild every MAME region + SDRAM image (build/regions)
#   make mame-regions    dump regions from MAME for all 10 sets and compare
#                        byte for byte with `make regions`
#   make oracle          all captures below (JOBS at a time)
#   make oracle-verify   Python renderer vs MAME on every captured frame
#   make analyze         write-log, interrupt and sprite summaries
#   make m0              everything above, in order
#
# M1 targets (Verilator; need `make regions` and the oracle captures):
#   make m1-gfx          graphics ROM image per set (build/regions/<set>/gfx.bin,
#                        tools/gfx_layout.py) with the decode self-check
#   make m1-build        build the d8_video frame-replay harness: LIVE (the
#                        default), LATCH and KRN_FLIP=1 builds
#   make m1-verify       RTL vs MAME on every M0 capture frame, all 10 sets (gate)
#   make m1-verify-latch the same with the LATCH build
#   make m1-synth        synthetic scenes vs d8_render.py (gate)
#   make m1-krnflip      KRN_FLIP=1 build on the synthetic scenes vs the model
#                        with the chip flip on (R7 switch, not MAME parity)
#   make m1-vislog       rerun every capture with VISLOG=1 (visible-scan writes
#                        with the value before each write)
#   make m1-midscan      replay every captured frame with visible-scan writes
#                        through LIVE and LATCH and classify each difference (gate)
#   make m1-capacity     sprites-per-line probe (not a gate)
#   make m1              m1-gfx m1-build m1-verify m1-verify-latch m1-synth
#                        m1-krnflip m1-midscan
#
# Every MAME run starts from a wiped cfg/nvram directory (mame/run_mame.sh),
# so captures are reproducible from power-on. Output lands in mame/out
# (gitignored).

PY      ?= python3
MAME    ?= mame
export MAME
OUT     := mame/out
RUN     := mame/run_mame.sh
ORACLE  := mame/d8_oracle.lua
JOBS    ?= 4
ALLSETS := lastmisn lastmisnu6 lastmisnu5 lastmisnj gondo gondou makyosen srdarwin srdarwinj srdarwinb

# Capture plan (frame = MAME frame notifier count, 57.44 Hz).
# lastmisn spends its first ~600 frames on RAM/ROM tests; the dense windows
# hold attract demo play. Gameplay runs coin up after the boot.
LM_ATTRACT   := 1-12000/8,3000-3599
LM_PLAY      := 1000-6000/4
GO_ATTRACT   := 1-12000/8,2000-2599
GO_PLAY      := 700-6000/4
SR_ATTRACT   := 1-12000/8,1000-1599
SR_PLAY      := 700-6000/4
FLIP_FRAMES  := 1-6000/20
CLONE_FRAMES := 30-9000/30
CLONES       := lastmisnu6 lastmisnu5 lastmisnj gondou makyosen srdarwinj srdarwinb
RUNS := lm_attract lm_play go_attract go_play sr_attract sr_play go_flip sr_flip \
        $(addprefix clone_,$(CLONES))

.PHONY: roms-check regions mame-regions oracle oracle-verify analyze m0 clean-out \
        m1 m1-gfx m1-build m1-verify m1-verify-latch m1-synth m1-krnflip m1-vislog m1-midscan m1-capacity

roms-check:
	$(PY) ../tools/check_roms.py

regions:
	$(PY) ../tools/build_regions.py

mame-regions: regions
	@for s in $(ALLSETS); do \
	  DUMP_DIR=$(OUT)/regions/$$s RT_TAG=reg_$$s $(RUN) $$s mame/dump_regions.lua -seconds_to_run 5 >/dev/null 2>&1 \
	    || echo "MAME failed on $$s"; \
	done
	$(PY) ../tools/compare_regions.py $(ALLSETS)

# one line per run: name set dump_frames [env assignments...]
runs.txt: Makefile
	@{ \
	  echo "lm_attract lastmisn $(LM_ATTRACT)"; \
	  echo "lm_play lastmisn $(LM_PLAY) INPUTS=$$($(PY) ../tools/play_inputs.py lastmisn 900 6000)"; \
	  echo "go_attract gondo $(GO_ATTRACT)"; \
	  echo "go_play gondo $(GO_PLAY) INPUTS=$$($(PY) ../tools/play_inputs.py gondo 600 6000)"; \
	  echo "sr_attract srdarwin $(SR_ATTRACT)"; \
	  echo "sr_play srdarwin $(SR_PLAY) INPUTS=$$($(PY) ../tools/play_inputs.py srdarwin 600 6000)"; \
	  echo "go_flip gondo $(FLIP_FRAMES) FIELDS=DSW0:Flip Screen:0"; \
	  echo "sr_flip srdarwin $(FLIP_FRAMES) FIELDS=DSW0:Flip Screen:0"; \
	  for s in $(CLONES); do echo "clone_$$s $$s $(CLONE_FRAMES)"; done; \
	} > runs.txt

oracle: runs.txt
	mkdir -p $(OUT); rm -rf $(addprefix $(OUT)/,$(RUNS))
	$(PY) mame/run_captures.py runs.txt $(JOBS)
	@for r in $(RUNS); do test -s $(OUT)/$$r/summary.txt || { echo "run $$r did not finish"; exit 1; }; done

oracle-verify:
	@rc=0; for r in $(RUNS); do \
	  ( echo "== $$r"; $(PY) oracle/compare_frames.py $(OUT)/$$r --quiet ) > $(OUT)/verify_$$r.txt 2>&1 & \
	  while [ $$(jobs -r | wc -l) -ge $(JOBS) ]; do sleep 1; done; \
	done; wait; for r in $(RUNS); do cat $(OUT)/verify_$$r.txt; tail -1 $(OUT)/verify_$$r.txt | grep -q "^\([0-9]*\)/\1 frames" || rc=1; done; exit $$rc

analyze:
	$(PY) ../tools/analyze_writes.py $(addprefix $(OUT)/,$(RUNS)) > $(OUT)/analysis.txt; cat $(OUT)/analysis.txt

m0: roms-check mame-regions oracle oracle-verify analyze

clean-out:
	rm -rf $(OUT) build runs.txt

# ---------------------------------------------------------------- M1
VERILATOR ?= verilator
RTL       := ../rtl/d8_video.sv ../rtl/d8_snapram.sv ../rtl/d8_dpram.sv ../rtl/d8_fifo.sv
M1BIN     := build/m1/obj_dir/Vd8_video
M1LBIN    := build/m1_latch/obj_dir/Vd8_video
M1KBIN    := build/m1_krnflip/obj_dir/Vd8_video
VFLAGS    := --cc --exe --build -O3 -Wall -Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM -Wno-WIDTHEXPAND \
             -Wno-WIDTHTRUNC --top-module d8_video -CFLAGS -O2 -j 4
M1RUNS    := $(addprefix $(OUT)/,$(RUNS))

m1-gfx:
	$(PY) ../tools/gfx_layout.py --check $(ALLSETS)

$(M1BIN): $(RTL) m1/tb_video.cpp
	mkdir -p build/m1
	$(VERILATOR) $(VFLAGS) -Mdir build/m1/obj_dir $(RTL) m1/tb_video.cpp

$(M1LBIN): $(RTL) m1/tb_video.cpp
	mkdir -p build/m1_latch
	$(VERILATOR) $(VFLAGS) -GLATCH=1 -Mdir build/m1_latch/obj_dir $(RTL) m1/tb_video.cpp

$(M1KBIN): $(RTL) m1/tb_video.cpp
	mkdir -p build/m1_krnflip
	$(VERILATOR) $(VFLAGS) -GKRN_FLIP=1 -Mdir build/m1_krnflip/obj_dir $(RTL) m1/tb_video.cpp

m1-build: $(M1BIN) $(M1LBIN) $(M1KBIN)

m1-verify: $(M1BIN)
	$(PY) m1/replay.py $(M1RUNS) --jobs $(JOBS) --quiet

m1-verify-latch: $(M1LBIN)
	$(PY) m1/replay.py $(M1RUNS) --jobs $(JOBS) --quiet --latch

m1-synth: $(M1BIN)
	$(PY) m1/make_scenes.py build/m1/scenes
	$(PY) m1/replay.py build/m1/scenes/* --jobs $(JOBS) --quiet

m1-krnflip: $(M1KBIN)
	$(PY) m1/make_scenes.py build/m1/scenes_krnflip --krnflip
	$(PY) m1/replay.py build/m1/scenes_krnflip/* --jobs $(JOBS) --quiet --krnflip --model_only

m1-vislog:
	$(PY) mame/vislog_runs.py --jobs $(JOBS)

m1-midscan: $(M1BIN) $(M1LBIN)
	$(PY) m1/midscan.py $(RUNS) --jobs $(JOBS)

m1-capacity: $(M1BIN)
	$(PY) m1/capacity.py

m1: m1-gfx m1-build m1-verify m1-verify-latch m1-synth m1-krnflip m1-midscan
