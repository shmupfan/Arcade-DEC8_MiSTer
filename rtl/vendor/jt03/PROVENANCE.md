# jt03 (YM2203) and jt49 (its SSG)

Source: jotego/jt12, commit dc9be7c1ff75d5b9a7f9d89da1b7fba212af1257 (the
submodule pinned by jotego/jtcores 0b197ca, the same jtcores commit as the
T80), with its jt49 submodule at 7f6abfd08a2af9a92dbd5b32c71ea773248a77e2.
Fetched 2026-09-29 with git. GPL-3.0 (LICENSE).

Files: the jt03 list from jt12 `cfg/jt03.yaml` (hdl/) plus the jt49 list
from `cfg/jt49.yaml` (jt49/hdl/). Files unchanged.

Used by the YM2203 games (lastday, gulfstrm, pollux): two jt03 instances.

DEC8 copy: taken unchanged from dooyong-mister/rtl/vendor/jt03 on
2026-10-03 for rtl/d8_snd.sv (one jt03, the YM2203 on all three boards).
Integration note (d8_snd): jt03 clears its operator pipelines
(jt12_sh_rst) only on clock enables during reset, so its clock enable must
run while reset is held (the datasheet's reset pulse is at least 72
master cycles, 6 x 12, YM2203 datasheet AC table "Reset pulse width").
