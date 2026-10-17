"""Per-row match profile at the correct d: where does content actually start/end?

For each real pair, use the d found by the Python algorithm, then for every row y
compute the fraction of columns where |A[y+d] - B[y]| <= TOL. Rows in the
overlay bands should NOT match; content rows should match almost perfectly.

This tells us whether top/bottom can be recovered from the match profile alone
(which would fix detect_overlays without relying on cross-shot staticness).

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"
TOL = 12.0


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32) @ \
        np.array([0.299, 0.587, 0.114], np.float32)


def profile(A, B, d, tol=TOL):
    H = A.shape[0]
    y1 = H - d
    ys = np.arange(0, y1)
    cf = (np.abs(A[ys + d] - B[ys]) <= tol).mean(axis=1)
    return ys, cf


def bands(ys, cf, thr=0.90, min_len=20):
    ok = cf >= thr
    out = []
    s = None
    for k, v in enumerate(ok):
        if v and s is None:
            s = k
        elif not v and s is not None:
            if k - s >= min_len:
                out.append((int(ys[s]), int(ys[k - 1])))
            s = None
    if s is not None and len(ok) - s >= min_len:
        out.append((int(ys[s]), int(ys[-1])))
    return out


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    names = [os.path.basename(p)[:8] for p in files]
    grays = [load_gray(p) for p in files]
    H = grays[0].shape[0]

    for i in range(len(grays) - 1):
        A, B = grays[i], grays[i + 1]
        d, c = S.find_offset(A, B, 0, 0)
        if d is None:
            print("=== %s -> %s : d=None (no overlap)" % (names[i], names[i + 1]))
            print("")
            continue
        ys, cf = profile(A, B, d)
        print("=== %s -> %s  d=%d" % (names[i], names[i + 1], d))
        print("  comparable rows 0..%d" % (ys[-1],))
        # coarse profile: mean cf per 100-row band
        line = []
        for b0 in range(0, H, 100):
            m = (ys >= b0) & (ys < b0 + 100)
            if m.sum() == 0:
                line.append("%4d:  -- " % b0)
            else:
                line.append("%4d:%.2f" % (b0, cf[m].mean()))
        for k in range(0, len(line), 6):
            print("   " + "  ".join(line[k:k + 6]))
        print("  contiguous bands with cf>=0.90 (len>=20): %s"
              % (bands(ys, cf),))
        for thr in (0.70, 0.50):
            print("    thr=%.2f bands: %s" % (thr, bands(ys, cf, thr)))
        print("")


if __name__ == "__main__":
    main()
