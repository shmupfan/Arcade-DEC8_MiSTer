#!/bin/sh
# quick M2 check: run SET for N frames, compare the I/O write stream (per
# CPU, order and value) with MAME's writes.csv of RUN up to frame N
SET=$1; RUN=$2; N=$3; D=build/m2/quick_$SET
mkdir -p $D
${BIN:-./build/m2/bin/Vd8_sys} +set=$SET +sdram=build/regions/$SET/sdram.bin +gfx=build/regions/$SET/gfx.bin \
  +frames=$N +io=$D/io.txt +ints=$D/ints.txt +out=$D $4 | tail -1
for c in main sub; do
  awk -F, -v n=$N -v c=$c 'NR>1 && $6==c && $1<n {print $1, $8, $9}' mame/out/$RUN/writes.csv > $D/mame_$c.txt
  awk -v c=$c '$4==c && $1<'$N' {print $1, $5, $6}' $D/io.txt > $D/ours_$c.txt
  n1=$(wc -l < $D/mame_$c.txt); n2=$(wc -l < $D/ours_$c.txt)
  first=$(paste -d'|' $D/mame_$c.txt $D/ours_$c.txt | awk -F'|' '$1!=$2 {print NR": mame["$1"] ours["$2"]"; exit}')
  echo "$c: mame $n1 ours $n2 first diff: ${first:-none}"
done
