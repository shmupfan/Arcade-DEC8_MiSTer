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

.PHONY: roms-check regions mame-regions oracle oracle-verify analyze m0 clean-out

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
