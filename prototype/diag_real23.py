"""Measure band cost-curve flatness.

Hypothesis for the device's extra break: some bands contain only content that
is IDENTICAL in both shots (input bar, empty background). Their cost curve is
flat, so the argmin is pure noise and the band votes against the true offset.
Such bands should ABSTAIN, not disagree.

For each band print the cost curve spread:
    spread = (max - min) / max   over dd in [d-8, d+8]
A flat band has small spread; an informative band has a clear minimum.

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


def band_curves(A, B, d, top, bottom, col_stride=S.COARSE_COL_STRIDE):
    H = A.shape[0]
    n_end = H - bottom - d
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
        out.append({"dev": xs[best], "min": float(cs.min()),
                    "max": float(cs.max()),
                    "spread": float((cs.max() - cs.min()) / max(cs.max(), 1e-9))})
    return out


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    gs = [load_gray(p) for p in files]
    cases = [(0, 1048, 0, 0), (1, 1341, 0, 0), (2, 1109, 0, 0),
             (4, 778, 0, 0),
             (0, 1048, 318, 286), (1, 1341, 318, 286), (2, 1109, 318, 286),
             (4, 778, 318, 286)]
    for (i, d, top, bot) in cases:
        bs = band_curves(gs[i], gs[i + 1], d, top, bot)
        print("pair%d d=%d top=%d bot=%d" % (i, d, top, bot))
        for k, b in enumerate(bs):
            if b is None:
                print("   band%d  (no data)" % k)
            else:
                print("   band%d dev=%-3d min=%.4f max=%.4f spread=%.3f"
                      % (k, b["dev"], b["min"], b["max"], b["spread"]))
        print("")

    # unrelated pair for contrast
    print("=== UNRELATED pair3 (best d found) ===")
    d, c = S.find_offset(gs[3], gs[4], 0, 0)
    print("  find_offset -> %s cost=%.4f" % (d, c))
    for probe in (136, 400, 1000):
        bs = band_curves(gs[3], gs[4], probe, 0, 0)
        print("  probe d=%d" % probe)
        for k, b in enumerate(bs):
            if b is None:
                print("    band%d (no data)" % k)
            else:
                print("    band%d dev=%-3d min=%.4f max=%.4f spread=%.3f"
                      % (k, b["dev"], b["min"], b["max"], b["spread"]))


if __name__ == "__main__":
    main()
