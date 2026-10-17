"""Bottom chrome via 3-way row classification (needs d).

For a row y in the bottom band of image A, compare two quantities:

  same  = mean|A[y] - B[y]|       (A and B at the SAME screen row)
  shift = mean|A[y] - B[y - d]|   (A[y] against the row it would land on in B)

  CONT  same >= THR, shift <  THR  -> scrolling content: it is NOT in B at the
                                      same screen position, but it IS in B
                                      shifted. Only real content looks like this.
  FIX   same <  THR, shift >= THR  -> fixed chrome (input bar, home strip).
  AMB   both <  THR                -> blank (blank matches blank anywhere).
  NOIS  both >= THR                -> transient UI (cursor) or JPEG ringing.

Rule: bottom = H - 1 - (largest y that is CONT).
Everything below the last content row is either chrome or blank, and cropping
blank rows is visually harmless, so this is safe in both directions.
Fall back to the static-suffix estimate when d is unknown (no overlap).

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

THR = 6.0
MAX_OVERLAY_FRAC = 0.22
TRUTH_CHAT = 276


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def classify_rows(A, B, d, top, thr=THR):
    H = A.shape[0]
    lo = int(H * (1.0 - MAX_OVERLAY_FRAC))
    y0 = max(lo, d + top, 0)
    if y0 >= H:
        return None
    ys = np.arange(y0, H)
    same = np.abs(A[ys] - B[ys]).mean(axis=1)
    shift = np.abs(A[ys] - B[ys - d]).mean(axis=1)
    return ys, same, shift


def bottom_by_class(A, B, d, top, thr=THR):
    r = classify_rows(A, B, d, top, thr)
    if r is None:
        return 0
    ys, same, shift = r
    cont = (same >= thr) & (shift < thr)
    idx = np.nonzero(cont)[0]
    if len(idx) == 0:
        return A.shape[0] - int(ys[0])
    return A.shape[0] - 1 - int(ys[idx[-1]])


def bottom_static(A, B, thr=THR, gap_tol=6):
    H = A.shape[0]
    diff = np.abs(A - B).mean(axis=1)
    bottom = 0
    gap = 0
    for k in range(H - 1, -1, -1):
        if diff[k] < thr:
            gap = 0
            bottom = H - k
        else:
            gap += 1
            if gap > gap_tol:
                break
    return bottom


def main():
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    real = [load_gray(p) for p in files]

    print("### REAL  chat truth=%d  settings truth=~34" % TRUTH_CHAT)
    for i, d in {0: 1048, 1: 1341, 2: 1109, 4: 778}.items():
        A, B = real[i], real[i + 1]
        cls = bottom_by_class(A, B, d, 318)
        st = bottom_static(A, B)
        print("  pair%d d=%-5d class=%-4d static=%-4d" % (i, d, cls, st))
    print("")

    print("### SYNTHETIC  (truth = content_bottom_bar)")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        gg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
              for p in info["shots"]]
        tb = info["content_bottom_bar"]
        deltas = info["deltas"]
        got = []
        for i, d in enumerate(deltas):
            got.append(bottom_by_class(gg[i], gg[i + 1], d, 321))
        print("  %-9s truth=%-4d class=%-18s err=%s"
              % (name, tb, str(got), [g - tb for g in got]))


if __name__ == "__main__":
    main()
