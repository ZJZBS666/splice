"""Find the bottom overlay boundary from the MATCH PROFILE at the true d.

Insight: the fixed overlay (WeChat input bar, home indicator, Settings search
field) sits at the SAME screen position in every screenshot. When we compare
B[y] against A[y+d] (the true scroll d), content rows match (they show the same
document text), but overlay rows do NOT match: B[y] shows the overlay at row y
while A[y+d] shows the overlay at row y+d, i.e. a different part of the bar.

So the overlay shows up as a CONTIGUOUS SUFFIX OF MISMATCH at the true d.
That is a self-contained detector: it needs no threshold on absolute motion,
only the known d.

Truth d for the real pairs (recovered from the device outputs):
  pair0 86dac91c->120c5a2d  d=1048
  pair1 120c5a2d->4cdf0381  d=1341
  pair2 4cdf0381->3f47518d  d=1109
  pair3 3f47518d->2cc671e8  d=None  (not overlapping)
  pair4 2cc671e8->36a92788  d=778

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

SRC = r"E:\DeepSeek\本地电脑\splice\samples\1"
H = 2622
W = 1206
TOP = 318
KNOWN_D = {0: 1048, 1: 1341, 2: 1109, 3: None, 4: 778}
SD_FLOOR = 8.0
TEXTURE_MIN = 3.0


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def row_profile(A, B, d, top, bottom):
    """Per-row normalised error at offset d, for rows top .. H-bottom-d."""
    n_end = H - bottom - d
    ys = np.arange(top, n_end)
    a = A[ys + d]
    b = B[ys]
    mad = np.abs(a - b).mean(axis=1)
    sd = a[:, 30:W - 30].std(axis=1)
    rne = mad / np.maximum(sd, SD_FLOOR)
    return ys, mad, rne, sd


def main():
    files = sorted(glob.glob(os.path.join(SRC, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    grays = [load_gray(p) for p in files]

    for i in range(len(grays) - 1):
        d = KNOWN_D[i]
        if d is None:
            print("=== pair%d  (no overlap, skipped)" % i)
            continue
        A, B = grays[i], grays[i + 1]
        ys, mad, rne, sd = row_profile(A, B, d, TOP, 0)
        print("=== pair%d d=%d  rows %d..%d" % (i, d, ys[0], ys[-1]))

        # profile in the bottom 600 rows
        print("    y      mad     rne     sd")
        for y in range(H - 600, ys[-1] + 1, 20):
            k = y - TOP
            if 0 <= k < len(ys):
                print("    %-6d %7.2f %7.2f %7.2f"
                      % (y, mad[k], rne[k], sd[k]))

        # contiguous mismatch suffix: from the last row upward, rows with
        # rne >= 1.0 count as "not matching", tolerate a few gaps
        thr = 1.0
        gap_tol = 8
        y_end = ys[-1]
        idx = len(ys) - 1
        gaps = 0
        bar_top = None
        while idx >= 0:
            if rne[idx] >= thr:
                bar_top = ys[idx]
                gaps = 0
            else:
                gaps += 1
                if gaps > gap_tol:
                    break
            idx -= 1
        if bar_top is None:
            print("    -> no mismatch suffix found (bottom=0)")
        else:
            print("    -> mismatch suffix starts y=%d  => bottom=%d"
                  % (bar_top, H - bar_top))
        print("")


if __name__ == "__main__":
    main()
