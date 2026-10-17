"""Bottom-chrome detection using the "reappear test" with a known offset d.

Core idea
---------
We already know the scroll offset d exactly (verified: d = 1048/1341/1109/778
on the real samples). For a row y near the BOTTOM of image A:

    A[y]  should equal  B[y - d]      if that row is *scrolling content*
                                      (it reappears higher up in B)
    A[y]  does NOT equal B[y - d]     if that row is *fixed chrome*
                                      (the input bar never scrolls)

This separates chrome from blank content, which the plain static-row test
cannot do: blank chat background above the input bar is identical in both
shots, so it looks "static" and inflates the overlay estimate.

Valid range: y - d must be >= top (below B's top chrome) and y < H.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

THR = 6.0
GAP_TOL = 6
TRUTH_BOTTOM = 275


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def bottom_by_reappear(A, B, d, top, thr=THR, gap_tol=GAP_TOL):
    H = A.shape[0]
    y0 = max(d + top, 0)
    if y0 >= H:
        return 0
    ys = np.arange(y0, H)
    diff = np.abs(A[ys] - B[ys - d]).mean(axis=1)
    bottom = 0
    gap = 0
    for k in range(len(ys) - 1, -1, -1):
        if diff[k] >= thr:
            gap = 0
            bottom = H - int(ys[k])
        else:
            gap += 1
            if gap > gap_tol:
                break
    return bottom


def bottom_by_reappear_frac(A, B, d, top, col_tol=12.0, frac_thr=0.5,
                            gap_tol=GAP_TOL):
    """Robust variant: a row 'reappears' if most columns match within col_tol."""
    H = A.shape[0]
    y0 = max(d + top, 0)
    if y0 >= H:
        return 0
    ys = np.arange(y0, H)
    a = A[ys]
    b = B[ys - d]
    frac = (np.abs(a - b) <= col_tol).mean(axis=1)
    bottom = 0
    gap = 0
    for k in range(len(ys) - 1, -1, -1):
        if frac[k] < frac_thr:          # row did NOT reappear -> chrome
            gap = 0
            bottom = H - int(ys[k])
        else:
            gap += 1
            if gap > gap_tol:
                break
    return bottom


def main():
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    real = [load_gray(p) for p in files]

    print("### REAL  truth bottom=%d" % TRUTH_BOTTOM)
    known = {0: 1048, 1: 1341, 2: 1109, 4: 778}
    for i, d in known.items():
        A, B = real[i], real[i + 1]
        b1 = bottom_by_reappear(A, B, d, 318)
        b2 = bottom_by_reappear_frac(A, B, d, 318)
        print("  pair%d d=%-5d mean=%-4d frac=%-4d" % (i, d, b1, b2))
    print("")

    print("### SYNTHETIC  (truth = content_bottom_bar)")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        gg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
              for p in info["shots"]]
        tb = info["content_bottom_bar"]
        deltas = info["deltas"]
        bits = []
        for i, d in enumerate(deltas):
            b1 = bottom_by_reappear(gg[i], gg[i + 1], d, 321)
            b2 = bottom_by_reappear_frac(gg[i], gg[i + 1], d, 321)
            bits.append("%d/%d" % (b1, b2))
        print("  %-9s truth=%-4d %s" % (name, tb, "  ".join(bits)))


if __name__ == "__main__":
    main()
