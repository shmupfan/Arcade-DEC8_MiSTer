#!/usr/bin/env python3
"""M3: the core's sound outputs against MAME's WAV.

Core: m2/tb_sys.cpp +aud= (48 kHz frames of 4 int16: YM2203 FM, YM2203 SSG
(jt49 sum, unsigned), OPL, the RTL mix), from reset release. MAME: -wavwrite
of the same run, -samplerate 48000, mono. The time axes agree to about one
sample (the event logs show the core 2 us ahead at the first write), so no
lag search is needed beyond a +-5 ms check on 1 ms envelopes.

Both are DC-blocked and low-passed at --band (default 3.5 kHz, as the
Tecmo 16 and 1945k III M3s: above that the chips' raw sample rates and
MAME's resampler differ). Then:
  --fit   least squares of MAME's signal on (FM, SSG, OPL) over the run:
          the gains (in 1/256 of the core's units) that make the core's
          components sum to MAME's mix, and the residual
  always  level of the RTL mix against MAME (RMS ratio in dB, whole run and
          per --seg seconds) and the correlation of 20 ms RMS envelopes

Usage: compare_audio.py core.raw mame.wav [--upto S] [--fit] [--band HZ]
"""
import argparse
import sys
import wave

import numpy as np
from scipy.signal import butter, sosfiltfilt


def env(x, win):
    n = len(x) // win
    return np.sqrt((x[:n * win].reshape(n, win) ** 2).mean(axis=1))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("core")
    ap.add_argument("mame")
    ap.add_argument("--upto", type=float, default=None, help="seconds")
    ap.add_argument("--skip", type=float, default=0.5, help="seconds skipped at the start")
    ap.add_argument("--band", type=float, default=3500.0)
    ap.add_argument("--seg", type=float, default=10.0)
    ap.add_argument("--fit", action="store_true")
    a = ap.parse_args(argv)
    c = np.fromfile(a.core, dtype="<i2").astype(np.float64).reshape(-1, 4)
    c[:, 1] = np.fromfile(a.core, dtype="<u2").astype(np.float64).reshape(-1, 4)[:, 1]
    w = wave.open(a.mame)
    assert w.getsampwidth() == 2 and w.getframerate() == 48000
    m = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64).reshape(-1, w.getnchannels()).mean(axis=1)
    n = min(len(c), len(m))
    if a.upto:
        n = min(n, int(a.upto * 48000))
    s0 = int(a.skip * 48000)
    c, m = c[s0:n], m[s0:n]
    sos = butter(6, [20.0, a.band], btype="bandpass", fs=48000, output="sos")
    cf = np.stack([sosfiltfilt(sos, c[:, i]) for i in range(4)], axis=1)
    mf = sosfiltfilt(sos, m)
    em, ec = env(mf, 48), env(cf[:, 3], 48)
    k = max(range(-5, 6), key=lambda d: np.dot(ec[max(0, d):len(ec) + min(0, d)], em[max(0, -d):len(em) - max(0, d)]))
    print(f"{n / 48000:.1f} s compared from {a.skip:.1f} s; envelope lag {k} ms (expected 0)")
    if a.fit:
        # per-component gains from 20 ms window powers (FM synthesis in the
        # jt cores and in MAME's ymfm is not sample-identical, so a waveform
        # fit does not apply): MAME's power ~ sum of gain^2 x component power,
        # the components treated as uncorrelated; non-negative least squares
        from scipy.optimize import nnls
        win = 960
        k = len(mf) // win
        P = np.stack([(cf[:k * win, i].reshape(k, win) ** 2).mean(axis=1) for i in range(3)], axis=1)
        pm = (mf[:k * win].reshape(k, win) ** 2).mean(axis=1)
        sel = pm > 1e3
        g2, _ = nnls(P[sel], pm[sel])
        g = np.sqrt(g2)
        print("fit from window powers (MAME units per core unit, x256): FM %.1f  SSG %.1f  OPL %.1f" % tuple(g * 256)
              + f"  over {int(sel.sum())} windows with sound")
    rc, rm = np.sqrt((cf[:, 3] ** 2).mean()), np.sqrt((mf ** 2).mean())
    print(f"RTL mix vs MAME: {20 * np.log10(rc / rm):+.2f} dB (RMS {rc:.0f} vs {rm:.0f}); "
          f"20 ms envelope correlation {np.corrcoef(env(cf[:, 3], 960), env(mf, 960))[0, 1]:.3f}")
    seg = int(a.seg * 48000)
    for i in range(0, len(mf) - seg // 2, seg):
        a1, a2 = np.sqrt((cf[i:i + seg, 3] ** 2).mean()), np.sqrt((mf[i:i + seg] ** 2).mean())
        if a2 > 50:
            print(f"  {(s0 + i) / 48000:5.1f}-{(s0 + i + seg) / 48000:5.1f} s: {20 * np.log10(a1 / a2):+.2f} dB "
                  f"(env corr {np.corrcoef(env(cf[i:i + seg, 3], 960), env(mf[i:i + seg], 960))[0, 1]:.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
