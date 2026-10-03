#!/bin/sh
# build the M2 harness into DIR (default build/m2fast) with the Makefile's flags
DIR=${1:-build/m2fast}
UC=$(cd ../rtl/vendor/jt8051 && pwd)/jt8051.uc
mkdir -p $DIR
verilator --cc --exe --build -O3 --x-assign fast --x-initial fast -Wno-fatal -Wno-lint -Wno-style \
  -Wno-UNOPTFLAT -Wno-SYNCASYNCNET --top-module d8_sys -I../rtl/vendor/jt8051 -DSIMULATION \
  "-DJT8051_UCFILE=\"$UC\"" -CFLAGS "-O3 -march=native" -j 4 -Mdir $DIR/obj_dir \
  ../rtl/d8_sys.sv ../rtl/d8_mcu.sv ../rtl/d8_video.sv ../rtl/d8_snapram.sv ../rtl/d8_dpram.sv \
  ../rtl/d8_fifo.sv ../rtl/vendor/mc6809i/mc6809i.v ../rtl/vendor/jt8051/jt8051*.v m2/tb_sys.cpp
