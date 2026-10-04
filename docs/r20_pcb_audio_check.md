# R20 check against PCB audio: SRD music (OPL) to effects (YM2203) balance

2026-10-04. Question: on the real board, is the YM3526 (music) to YM2203 FM
(effects) balance 1:1 (the schematics' equal 10 kOhm summing resistors,
current core: FM_GAIN = OPL_GAIN = 102) or 2:1 (MAME 0.80 / 0.40)?

**Verdict: the board is between the two, closer to MAME. The best
estimate of the OPL:FM amplitude ratio is 1.65 (range 1.55 to 1.8), about
+4.3 dB (MAME's 2:1 is +6.0 dB, the core's 1:1 is 0 dB). The SSG is also
about 2 to 3 dB louder than the core's MAME-derived route. Recommended
gains (1/256): FM 102, OPL 170, SSG 3600.** Confidence: moderate. The
result rests on one real-board capture (a deterministic attract sequence,
134 s) with tight alignment and passing sanity fits. The two gameplay
videos cannot be aligned to a reference and give only a weak,
play-style-dependent check that does not contradict it.

## 1. Sources (YouTube, audio only)

| Video ID | Channel | Content | Audio stream | Use |
|---|---|---|---|---|
| dhoC-8KVKck | K !! | "実機基板キャプチャー(1080P HD)" (real-board capture): board power-on, then both demo types (stage 2 and stage 7). Japanese set (srdarwinj), 2:10 | itag 251 Opus, 48 kHz stereo, 108.6 kb/s | main fit |
| HrMhhSO97-A | OBS GAME RESEARCH | "アーケード実機の資料映像" (real arcade hardware reference footage), gameplay 0:12 to 14:15, 14:57 | itag 251 Opus, 48 kHz, 115.3 kb/s | weak cross-check |
| amenau-jqpo | Methylphenidate | "実基盤による自宅でのプレイ" (home play on the real board), loops 1 and 2, 56:57 | itag 251 Opus, 48 kHz, 113.5 kb/s | weak cross-check |

Downloaded with yt-dlp 2026.08.19 (Homebrew's 2026.07.04 got HTTP 403),
one at a time, into `sim/pcb_audio/` (git-ignored, not committed), decoded
to 48 kHz 16-bit WAV with ffmpeg. All three are mono sources (L/R
correlation 0.99995 or higher).

Capture checks (dhoC-8KVKck):
- YouTube loudness normalisation scales the whole track. It does not
  change the internal balance, and the fit uses ratios only.
- No AGC or compression found. The noise floor in the two silences (power-on
  6 to 10 s and between demos 66 to 75 s) is constant (12.9 and 13.8 dB
  full band, about 8 dB in the 20 Hz to 3.5 kHz band, against about 70 dB
  for music). The end-of-demo decay follows MAME's to within the noise
  floor, with no pumping. In the music sections the log-log slope of PCB
  window power against its fitted prediction is 0.82 to 0.88, against
  0.86 to 0.96 for MAME's WAV fitted the same way. A slope below 1 is
  expected for both because the fitted prediction is imperfect (regression
  dilution), and the PCB value is only slightly lower.
- Clipping: 1.3e-5 of samples at full scale (after normalisation),
  negligible.
- No video edits. A single linear time map fits every 5 s segment to
  within 6 ms (17 of 23 segments kept by the outlier rule; the rest are
  silences or the power-on beep). The map is pcb_t = 1.703 s +
  ref_t x 1.00068: the board's audio starts 1.70 s after MAME's power-on,
  and its clock (or the capture clock) runs 0.068% slow. This is an
  observation only and was not investigated.

## 2. Reference streams

- Core: `sim/build/r20/srj_attract/aud.raw`, srdarwinj, 7700 frames
  (134.0 s) from power-on with no inputs. The binary is
  `sim/build/m3/obj_dir/Vd8_sys`, built after the R17 fixes with the 1:1
  mix. It ran at nice 15 for 66 min. The output is 48 kHz frames of FM,
  SSG (unsigned jt49 sum), OPL and the RTL mix. The existing srdarwin run
  `sim/build/m3/sr_attract` (62.7 s) gave the same first-demo result
  (OPL:FM 1.63) before this run finished.
- MAME 0.288: `sim/mame/out/r20_srj_attract/mame.wav`, srdarwinj, 7700
  frames, `-wavwrite -samplerate 48000` through `d8_oracle.lua` (as
  `run_m3.py oracle`). The srdarwin and srdarwinj attract audio match over
  the first 60 s (20 ms envelope correlation 0.97, level within 0.01 dB).
- Sequence (reference time): SSG power-on beep 0 to 3.5 s; demo 1 music
  and effects 9 to 58 s; SSG title sounds 74 to 77 s; demo 2 83 to 128 s.
  In the demo, the YM2203 FM is the demo ship's shots and effects and the
  OPL is the music. In sr_play the FM is silent between shots while the
  OPL plays continuously, so OPL:FM is the music:effects ratio.
- The PCB has a sound at reference 78 to 82 s that MAME and the core do
  not have. It is probably the operator moving the ship on the Japanese
  title screen (the video description mentions this). It is excluded
  because only windows where MAME has sound are fitted.

## 3. Method

The scripts are `sim/m3/r20/` (`fit.py`, `xcheck.py`, `pct.py`, `lib.py`).

1. Everything is band-passed from 20 Hz to 3.5 kHz (sixth-order
   Butterworth, zero phase), as in `compare_audio.py`.
2. Alignment: 1 ms log-RMS envelopes of the PCB and MAME are
   cross-correlated in 5 s segments, and a robust straight line is fitted
   through the lags. The core and MAME share a time axis (the M3 result,
   tempo within 0.014%).
3. Fit: 20 ms window power of the PCB (noise floor subtracted) is modelled
   as gF·P_FM + gS·P_SSG + gO·P_OPL of the core's component powers, by
   non-negative least squares (as `compare_audio.py --fit`). The ratios
   are sqrt(gO/gF) and sqrt(gS/gF). The 90% intervals come from a
   bootstrap over 2 s blocks (400 resamples). The same fit is run on
   MAME's WAV and on the core's own RTL mix as sanity checks.
4. Per-band fits in five bands from 100 Hz to 3.5 kHz. A frequency
   response in the capture chain scales both chips equally within a band,
   so the ratio should not depend on the band.
5. Simpler cross-check: the level of windows where the core says FM
   dominates (FM over 4x OPL) minus the level of windows where OPL
   dominates, in the PCB, in MAME and in the core mix. This is compared
   with the same difference computed from the core components mixed at
   OPL:FM = k.

## 4. Results (dhoC-8KVKck, 0.5 to 134 s, 5001 windows of 20 ms)

| Fitted signal | OPL:FM [90% CI] | SSG:FM (x FM 102 = SSG gain) | R² |
|---|---|---|---|
| PCB | **1.69 [1.60-1.77]** | 36.9 [34.3-39.6] → 3760 | 0.44 |
| MAME WAV (true 2.0) | 1.97 [1.89-2.05] | 30.1 → 3070 (route 2775) | 0.64 |
| Core RTL mix (true 1.0) | 1.00 [0.99-1.01] | 27.2 → 2775 (exact) | 0.94 |

Both sanity fits recover their known balance. MAME is recovered to within
2%. For MAME the R² is lower because ymfm and jt03/jtopl are not
sample-identical; for the PCB it is lower again (codec, analog chain,
alignment).

Per demo: demo 1 (0.5 to 60 s) PCB 1.63 [1.53-1.71] against MAME 1.98;
demo 2 (70 to 134 s) PCB 1.72 [1.58-1.84] against MAME 1.96.

Per 10 s segment, PCB / MAME: 1.49/1.87, 1.57/1.88, 1.59/1.97,
1.46/2.04, 1.55/1.99, 1.57/1.95, 1.43/1.60, 1.34/1.61, 1.50/1.62 (core
mix 0.96 to 1.03 in every segment). The segment at 110 to 120 s is left
out: there the FM and OPL envelopes move together (collinear), and MAME's
own fit drops to 0.89. Scaled by MAME's known 2.0, the PCB segments give
1.5 to 1.8 (median 1.6).

Per band (PCB / MAME): 100-250 Hz 1.69/1.94, 250-500 1.44/1.60,
500-1000 1.83/1.94, 1000-2000 1.75/1.89, 2000-3500 1.65/1.93. Scaled by
MAME's 2.0 this gives 1.74 to 1.89. There is no strong frequency
dependence, so the band limit and the board's output stage (section 5)
do not decide the result.

Class cross-check (100 ms windows, 68 FM-dominated, 208 OPL-dominated):

| | FM-dom minus OPL-dom | implied OPL:FM |
|---|---|---|
| PCB | +0.28 dB | 1.82 |
| MAME | -0.50 dB | 2.2 (true 2.0) |
| Core mix | +4.09 dB | 1.0 (true 1.0) |

Scaled by MAME's +10% bias, the PCB value becomes 1.65. The same check on
the SSG-dominated windows (mostly the power-on beep) puts the PCB SSG
about 3 dB above the core's route at that OPL:FM, which gives an SSG gain
of about 3900.

Combined estimate: OPL:FM 1.55 to 1.8, central 1.65, that is OPL gain 170
for FM 102. SSG: 3400 (NNLS scaled by MAME's bias) to 3900 (class check),
central 3600.

## 5. Board output stage (LM-SCH sheet 27, PDF p. 31; GONDO-TSM sheet 28, PDF p. 46)

There is no low-pass or shaping filter between the DACs and the
amplifier. Each YM3014 drives a 3403 follower, then a 4.7 uF capacitor
and 10 kOhm into the node. The SSG goes through 1 kOhm x3 (Gondomania
10 kOhm x3), 10 uF and 56 kOhm into the node. Then come VR1 10 kOhm,
10 uF and the MB3730 (0.15 uF Zobel and stability capacitors at its
output). The coupling high-pass corners are a few Hz, the same for both
DAC paths. The board therefore does not weight music and effects
differently by frequency, which matches the flat per-band ratios above.
The schematic does not explain the 1.65 ratio; a difference in level
between the two chips' DAC data words or YM3014 drive is the likely
cause, not the summing network. The schematic alone predicts 1:1, and
the recording disagrees with it.

## 6. Gameplay videos (HrMhhSO97-A, amenau-jqpo): weak cross-check only

The stage music cannot be aligned with a reference past the first
3 s after the start (envelope correlation 0.6 to 0.7 at the start, about
0 afterwards against `sr_play`). The play differs, the effects dominate
the envelope, and no reference run reaches the same stage states, so no
per-chip fit is possible. A reference-free statistic, the spread of
100 ms window power over gameplay (P90 minus P10, P50 minus P10, in dB),
gives:

| | P90-P10 | P50-P10 |
|---|---|---|
| HrMhhSO97-A (15 to 855 s) | 4.13 | 2.04 |
| amenau-jqpo (8 to 3410 s) | 5.57 | 3.01 |
| MAME sr_play (2:1) | 5.06 | 2.83 |
| Core mix sr_play (1:1) | 7.59 | 4.29 |
| Core components at k = 1.5 / 2.0 | 6.01 / 5.34 | 3.54 / 2.96 |

Both PCB videos are narrower than the 1:1 core mix, which fits a louder
OPL. However, the statistic depends on how often effects play (the PCB
players fire continuously with rapid-fire boards, while the sr_play
script does not), so it gives no number. The OBS capture has a noise
floor about 50 dB below the music, with hiss; amenau-jqpo is at most 360p
with an Opus stream of the same quality.

## 7. Caveats

- One board, one capture chain, one game, all from a single real-board
  video. The other two videos give only an indirect check. Lastmisn and
  gondo were not measured; MAME's 1.25x OPL on gondo is untested.
- The fit treats the chips as uncorrelated in power. When FM and OPL move
  together, a segment's fit becomes unstable (the 110 to 120 s segment).
  This is the reason for the bootstrap and the per-segment and per-band
  spreads.
- The SSG estimate comes mostly from the power-on beep and a few title
  and demo sounds (67 SSG-dominated windows). The board's coupling
  capacitors (10 uF into 56 kOhm, time constant 0.6 s) have settled by
  then (the beep starts 1.7 s after the board's audio starts). Moderate
  confidence.
- The Opus codec (108 kb/s) leaves the levels between 20 Hz and 3.5 kHz
  unchanged to well within the spread above.

## 8. Recommendation

Set FM_GAIN 102, OPL_GAIN 170 (srdarwin, and lastmisn by the same
hardware unless measured otherwise), SSG_GAIN 3600. For OPL_GAIN_GO on
gondo there is no PCB evidence. Scaling MAME's 1.25x by the same
board-over-schematic finding is not justified; keep it until a Gondomania
recording is checked. Headroom on the core streams: peak 27971 on
srj_attract and 21997 on sr_play with (102, 3600, 170), no clipping.
This is the same as MAME's (102, 2775, 205), which peaks at 27863. R20:
reopen as settled by recording, OPL:FM 1.65, superseding the 1:1 of
m3_findings 7.2. No RTL was changed in this check.
