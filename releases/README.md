# Releases

Released bitstreams and MRA files, in the MiSTer-devel arcade layout.

Copy `Arcade-DEC8_YYYYMMDD.rbf` to `/media/fat/_Arcade/cores/`, the MRA
files to `/media/fat/_Arcade/`, and the ROM sets (MAME 0.288/0.289
naming) to `/media/fat/games/mame/`.

Alternative versions live in `_alternatives/_Last Mission/`,
`_alternatives/_Gondomania/` and `_alternatives/_SRD Super Real Darwin/`
and are copied to the same folders under
`/media/fat/_Arcade/_alternatives/`.

| File | md5 | Notes |
|------|-----|-------|
| `Arcade-DEC8_20261004.rbf` | `70ef132767ae6777700205213261b2e2` | First release: Last Mission (four sets), Gondomania (three sets), SRD: Super Real Darwin (three sets). |

Every released RBF passed, in order: frame replay against MAME for every
set (video pixel-exact), full-system boots against MAME from power-on, a
sound comparison against MAME, a board-level simulation through the MRA
stream and the SDRAM model, a clean Quartus timing summary (every clock
non-negative), and an md5-verified deploy.
