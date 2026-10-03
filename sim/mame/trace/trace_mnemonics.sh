#!/bin/sh
# Trace a set's main CPU with MAME's debugger for N frames and count the
# mnemonics executed, without writing the trace to disk (it streams through
# a FIFO into collect_mnemonics.py). Used for research item R4 (does
# Gondomania's HD6309 ever leave 6809 emulation mode?).
#   sim/mame/trace/trace_mnemonics.sh <set> <frames> <out.txt> [INPUTS-free]
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SET=$1; FRAMES=$2; OUT=$3
TMP=$(mktemp -d)
mkfifo "$TMP/fifo"
python3 "$HERE/collect_mnemonics.py" "$TMP/fifo" "$OUT" &
TRACE_FIFO="$TMP/fifo" TRACE_FRAMES="$FRAMES" RT_TAG="trace_$SET" \
  "$HERE/../run_mame.sh" "$SET" "$HERE/trace_fifo.lua" -debug -debugger none
wait
rm -rf "$TMP"
