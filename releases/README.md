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
| `Arcade-DEC8_20261004.rbf` | `aec0cd50e72098ca415cb349c6229628` | Last Mission (four sets), Gondomania (three sets), SRD: Super Real Darwin (three sets). Updated the same day: sound mix set from a real SRD board recording (music 1.67 times the effects, R20), output AC coupled as on the boards. First build of the day: `70ef132767ae6777700205213261b2e2`. |

Every released RBF passed, in order: frame replay against MAME for every
set (video pixel-exact), full-system boots against MAME from power-on, a
sound comparison against MAME (the mix balance then set from PCB evidence where it differs), a board-level simulation through the MRA
stream and the SDRAM model, a clean Quartus timing summary (every clock
non-negative), and an md5-verified deploy.
