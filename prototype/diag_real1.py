"""Diagnose the real screenshots in splice/samples/1/.

Order is taken from file mtime (EXIF DateTime is absent):
  86dac91c -> 120c5a2d -> 4cdf0381 -> 3f47518d -> 2cc671e8 -> 36a92788

For every consecutive pair print:
  * detected overlays (top / bottom)
  * chosen d + cost + band agreement
  * whether d is pinned to the search window edges
  * the best few minima of the full-resolution cost curve, with gaps
    relative to the best d (to expose periodic aliases)
  * expected long-image height vs what the App actually produced

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"
H_EXPECT = 2622


def load_gray(path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    return a @ np.array([0.299, 0.587, 0.114], np.float32)


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    print("order:")
    for i, p in enumerate(files):
        print("  %d %s" % (i, os.path.basename(p)))
    print("")

    grays = [load_gray(p) for p in files]
    H = grays[0].shape[0]
    W = grays[0].shape[1]
    print("size: %d x %d, count=%d" % (W, H, len(grays)))
    print("")

    total = 0
    ds = []
    for i in range(len(grays) - 1):
        A, B = grays[i], grays[i + 1]
        top, bot = S.detect_overlays([A, B])
        content_h = H - top - bot
        lo = max(int(S.MIN_SCROLL_FRAC * content_h), S.FINE_WINDOW)
        hi = H - bot - max(24, int(S.MIN_OVERLAP_FRAC * H)) - top
        d, cost = S.find_offset(A, B, top, bot)
        agree, devs = (0, [])
        if d is not None:
            agree, devs = S.band_votes(A, B, d, top, bot)
        print("pair %d -> %d" % (i, i + 1))
        print("  top=%d bottom=%d contentH=%d  window=[%d,%d]"
              % (top, bot, content_h, lo, hi))
        print("  chosen d=%s cost=%.4f  band_agree=%d/%d devs=%s"
              % (str(d), cost, agree, S.BAND_COUNT, devs))
        if d is not None:
            if d <= lo + 2:
                print("  !! d pinned to LOWER bound (true scroll may be smaller)")
            if d >= hi - 2:
                print("  !! d pinned to UPPER bound (true scroll may be larger)")
        # full-resolution curve, top minima
        sdA = S._row_sd(A, S.FINE_COL_STRIDE)
        curve = S._scan_curve(A, B, top, bot, lo, hi, sdA,
                              S.FINE_ROW_STRIDE, S.FINE_COL_STRIDE)
        best = sorted(curve.items(), key=lambda kv: kv[1][0])[:8]
        print("  curve minima:")
        bcost = best[0][1][0] if best else 1.0
        for kk, vv in best:
            mark = ""
            if d is not None and abs(kk - d) <= 1:
                mark = "  <== chosen"
            elif vv[0] <= bcost * 1.5 + 1e-9:
                mark = "  (near-tie)"
            print("    d=%-5d cost=%.4f rows=%-5d%s" % (kk, vv[0], vv[1], mark))
        if d is not None:
            gaps = sorted(set(d - kk for kk, _ in best if kk < d))
            if gaps:
                print("  d minus smaller candidates: %s" % (gaps,))
        ds.append(d)
        if d is not None:
            total += d
        print("")

    print("sum(d) = %d" % total)
    print("expected long height (keep first chrome) = %d"
          % (H - 34 + total))
    print("")
    print("App actually produced: 3384 / 3445 / 3485 (sum(d) 796 / 857 / 897)")


if __name__ == "__main__":
    main()
