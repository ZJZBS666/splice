"""Bottom chrome = max(static_suffix, reappear_suffix).

Two independent estimators, each blind to the other's failure mode:

  static_suffix  : rows identical at the SAME screen position in A and B.
                   Catches the thin home-indicator strip (which is static and
                   sits on white background). Fails on the tall input bar when
                   a cursor/highlight makes one row differ (pair0 -> only 24).

  reappear_suffix: rows of A that do NOT reappear at B[y-d]. Catches the tall
                   input bar (it never scrolls). Fails on the thin home strip
                   when the blank white area happens to match blank content.

Underestimating is what destroys the image (36 lost rows last time), and
overestimating is self-healing because the next screenshot supplies those rows.
So take the MAX.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

STATIC_THR = 6.0
REAPPEAR_THR = 6.0
GAP_TOL = 6
TRUTH_BOTTOM = 275


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def static_suffix(A, B, thr=STATIC_THR, gap_tol=GAP_TOL):
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


def reappear_suffix(A, B, d, top, thr=REAPPEAR_THR, gap_tol=GAP_TOL):
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


def bottom_of(A, B, d, top):
    return max(static_suffix(A, B), reappear_suffix(A, B, d, top))


def main():
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    real = [load_gray(p) for p in files]

    print("### REAL  chat truth=275  settings truth=~34")
    known = {0: 1048, 1: 1341, 2: 1109, 4: 778}
    for i, d in known.items():
        A, B = real[i], real[i + 1]
        st = static_suffix(A, B)
        rp = reappear_suffix(A, B, d, 318)
        print("  pair%d d=%-5d static=%-4d reappear=%-4d max=%-4d"
              % (i, d, st, rp, max(st, rp)))
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
        errs = []
        for i, d in enumerate(deltas):
            st = static_suffix(gg[i], gg[i + 1])
            rp = reappear_suffix(gg[i], gg[i + 1], d, 321)
            bits.append("%d+%d=%d" % (st, rp, max(st, rp)))
            errs.append(max(st, rp) - tb)
        print("  %-9s truth=%-4d %s   err=%s"
              % (name, tb, "  ".join(bits), errs))


if __name__ == "__main__":
    main()
