# jtopl (YM3526 / YM3812)

Source: jotego/jtopl, commit 7ac0c819ad274e208206f2acccbbde80aa06ed1a (2026-07-29), `hdl/`: the
files of `cfg/common.yaml` and `cfg/jt26.yaml` plus jtopl2.v, fetched
2026-10-03 with git. Copyright Jose Tejada Gomez, GPL-3.0-or-later
(LICENSE). Files unchanged.

Used by rtl/d8_snd.sv as one jtopl2 (YM3812) instance. On lastmisn and
gondo (YM3526) d8_snd clears bit 5 of register 01 (the YM3812 wave-select
enable, absent on the YM3526) on its way in; with that bit clear jtopl2
selects the sine for every operator (jtopl_reg.v wavsel = 0) and its
operator path equals jtopl's OPL_TYPE 1 path (jtopl_op.v).
