"""Bottom overlay calibration v12: also catch FLOATING fixed islands.

The settings pair showed the failure mode the old rule misses: iOS 26 puts the
search capsule at a FIXED screen position y=2394..2538, but real content keeps
scrolling BELOW it.  classify_bottom() takes the last CONT row, so it answers
bottom=0 and the capsule is stitched in twice.

Fix: the bottom cut must also start at the top of any fixed (non-scrolling)
band in the bottom zone, because cropping from the bottom is safe (the next
screenshot re-covers those rows).

    bottom_class  = H - 1 - lastContRow
    bottom_island = H - topOfHighestFixedBand     (band len >= MIN_OVERLAY_H,
                                                   band must end near the bottom)
    bottom        = max(bottom_class, bottom_island)

ASCII only.
"""
import glob
import os

import numpy as np
from PIL import Image

import gen_samples as G
import stitcher as S

THR = S.CLASSIFY_THR
MIN_BAND = S.MIN_OVERLAY_H
END_NEAR = 0.12


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def cont_mask(A, B, d, thr=THR):
    H = A.shape[0]
    y0 = max(int(H * (1.0 - S.MAX_OVERLAY_FRAC)), d, 0)
    ys = np.arange(y0, H)
    same = np.abs(A[ys] - B[ys]).mean(axis=1)
    shift = np.abs(A[ys] - B[ys - d]).mean(axis=1)
    return ys, (same >= thr) & (shift < thr)


def bands(mask, min_len):
    out = []
    start = None
    for i, v in enumerate(mask):
        if not v and start is None:
            start = i
        elif v and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    if start is not None and len(mask) - start >= min_len:
        out.append((start, len(mask)))
    return out


def shift_mask(A, B, d, thr=THR):
    H = A.shape[0]
    y0 = max(int(H * (1.0 - S.MAX_OVERLAY_FRAC)), d, 0)
    ys = np.arange(y0, H)
    shift = np.abs(A[ys] - B[ys - d]).mean(axis=1)
    return ys, shift


def bottom_new(A, B, d, thr=THR):
    H = A.shape[0]
    ys, cont = cont_mask(A, B, d, thr)
    idx = np.flatnonzero(cont)
    b_class = H - 1 - int(ys[idx[-1]]) if len(idx) else 0
    # "fixed" = content does NOT reappear anywhere -> shift stays large.
    # This catches translucent overlays whose interior pixels keep changing.
    _, shift = shift_mask(A, B, d, thr)
    nb = bands(~(shift >= thr), MIN_BAND)
    b_isl = 0
    for (s, e) in nb:
        y_top = int(ys[s])
        y_end = int(ys[e - 1])
        if y_end >= H - int(END_NEAR * H):
            b_isl = max(b_isl, H - y_top)
    return b_class, b_isl, max(b_class, b_isl)


def main():
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    g = [load_gray(p) for p in files]
    ds = [1048, 1341, 1109, None, 778]
    truth = [276, 276, 276, 0, 228]
    print("=== real 6 images (truth 276/276/276/0/228) ===")
    for i, d in enumerate(ds):
        if d is None:
            print("  pair%d  d=None (no overlap)" % i)
            continue
        bc, bi, bn = bottom_new(g[i], g[i + 1], d)
        print("  pair%d d=%4d  class=%4d island=%4d  -> %4d   truth=%4d  %s"
              % (i, d, bc, bi, bn, truth[i],
                 "OK" if abs(bn - truth[i]) <= 40 else "MISMATCH"))

    print("\n=== synthetic 5 scenes (truth = content_bottom_bar) ===")
    sets = G.build_all()
    for name, info in sets.items():
        shots = [load_gray(p) for p in info["shots"]]
        dsyn = info["deltas"]
        tbot = info["content_bottom_bar"]
        got = []
        for i, d in enumerate(dsyn):
            bc, bi, bn = bottom_new(shots[i], shots[i + 1], d)
            got.append((bc, bi, bn))
        print("  %-8s truth=%3d  " % (name, tbot)
              + "  ".join("c%d/i%d->%d" % (a, b, c) for a, b, c in got))


if __name__ == "__main__":
    main()
