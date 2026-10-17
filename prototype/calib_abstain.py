"""Calibrate abstention: flat bands must not vote against the true offset.

Data from diag_real23:
  true matches : informative bands have spread > 0.3, flat ones < 0.12
  unrelated    : EVERY band spread < 0.05

So a band whose cost curve is flat carries no evidence. Today it still
returns argmin, which is noise, and that noise can push agree below
MIN_BAND_AGREE and break the group.

Rule to test: a band abstains when spread < SPREAD_MIN. Then require
    agree >= MIN_BAND_AGREE  AND  agree + abstain >= MIN_BAND_AGREE
i.e. only count bands that actually looked, and demand most of the
informative ones agree.

This script replays every positive pair (synthetic + real) and the negative
pairs and reports agree/abstain so we can pick SPREAD_MIN.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"


def load_gray(path):
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.uint8)
    return S.to_gray(rgb)


def band_stats(A, B, d, top, bottom, col_stride=S.COARSE_COL_STRIDE):
    """Return list of (dev, spread, min) per band."""
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 16:
        return []
    sd = S._row_sd(A, col_stride)
    ys_all = np.arange(top, n_end)
    ys_tex = ys_all[sd[ys_all + d] >= S.TEXTURE_MIN]
    if ys_tex.size < S.BAND_COUNT * 8:
        return []
    y_lo, y_hi = int(ys_tex[0]), int(ys_tex[-1])
    span = y_hi - y_lo + 1
    out = []
    for k in range(S.BAND_COUNT):
        b0 = y_lo + span * k // S.BAND_COUNT
        b1 = y_lo + span * (k + 1) // S.BAND_COUNT
        xs, cs = [], []
        for dd in range(max(1, d - S.BAND_WIN), d + S.BAND_WIN + 1):
            c = S._band_cost(A, B, dd, b0, b1, sd, col_stride)
            if c is None:
                continue
            xs.append(dd - d)
            cs.append(c)
        if not cs:
            out.append(None)
            continue
        cs = np.array(cs)
        best = int(np.argmin(cs))
        out.append((xs[best], float((cs.max() - cs.min()) / max(cs.max(), 1e-9)),
                    float(cs.min())))
    return out


def votes_with_abstain(stats, spread_min):
    agree = abstain = disagree = 0
    for b in stats:
        if b is None:
            abstain += 1
            continue
        dev, spread, _mn = b
        if spread < spread_min:
            abstain += 1
        elif abs(dev) <= S.BAND_AGREE_TOL:
            agree += 1
        else:
            disagree += 1
    return agree, abstain, disagree


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    gs = [load_gray(p) for p in files]

    print("### positive pairs (real), top=0 bot=0")
    pos = [(0, 1048), (1, 1341), (2, 1109), (4, 778)]
    for (i, d) in pos:
        st = band_stats(gs[i], gs[i + 1], d, 0, 0)
        line = "pair%d d=%d " % (i, d)
        for sm in (0.02, 0.05, 0.10, 0.15, 0.20):
            a, ab, di = votes_with_abstain(st, sm)
            line += "| sm=%.2f a=%d ab=%d d=%d " % (sm, a, ab, di)
        print(line)

    print("")
    print("### negative pairs (real), best d under probe")
    for (i, j, d) in [(3, 4, 136), (3, 4, 400), (3, 4, 1000), (5, 0, 800)]:
        st = band_stats(gs[i], gs[j], d, 0, 0)
        line = "pair%d-%d d=%d " % (i, j, d)
        for sm in (0.02, 0.05, 0.10, 0.15, 0.20):
            a, ab, di = votes_with_abstain(st, sm)
            line += "| sm=%.2f a=%d ab=%d d=%d " % (sm, a, ab, di)
        print(line)

    print("")
    print("### positive pairs (synthetic integer scrolls)")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        shots = info["shots"]
        rg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")).astype(np.uint8))
              for p in shots]
        deltas = info["deltas"]
        for k in range(min(2, len(rg) - 1)):
            st = band_stats(rg[k], rg[k + 1], deltas[k], 321, 34)
            a, ab, di = votes_with_abstain(st, 0.05)
            a2, ab2, di2 = votes_with_abstain(st, 0.15)
            print("%-9s pair%d d=%-5d sm0.05 a=%d ab=%d d=%d | sm0.15 a=%d ab=%d d=%d"
                  % (name, k, deltas[k], a, ab, di, a2, ab2, di2))


if __name__ == "__main__":
    main()
