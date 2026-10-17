"""Is the per-row MAX criterion too strict for real JPEGs?

Current metric: err_row = max over columns of |A[y+d] - B[y]|, then a row counts
as matched only if err_row < tol. A single JPEG ringing pixel kills the row.

Test on the real pair 0->1 at d=1048:
  * per-row median abs diff
  * per-row fraction of columns within tol  (robust to isolated artifacts)
  * how many rows reach col_frac >= 0.9

Then re-scan every d with the robust metric and see whether the peak is sharp
and whether the chosen d is the true one.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"
TOP_SKIP = 300
BOT_SKIP = 280
TOL = 12.0


def load_gray(path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    return a @ np.array([0.299, 0.587, 0.114], np.float32)


def row_stats(A, B, d, tol=TOL):
    """Return (col_frac per row, median diff per row, ys)."""
    H, W = A.shape
    y0 = TOP_SKIP
    y1 = H - BOT_SKIP - d
    if y1 - y0 < 60:
        return None, None, None
    ys = np.arange(y0, y1, 2)
    a = A[ys + d]
    b = B[ys]
    diff = np.abs(a - b)
    col_frac = (diff <= tol).mean(axis=1)
    med = np.median(diff, axis=1)
    return col_frac, med, ys


def robust_score(A, B, d, tol=TOL):
    cf, med, ys = row_stats(A, B, d, tol)
    if cf is None:
        return None
    # score = mean column-match fraction over all comparable rows
    return float(cf.mean())


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    names = [os.path.basename(p)[:8] for p in files]
    grays = [load_gray(p) for p in files]
    H, W = grays[0].shape
    print("count=%d size=%dx%d tol=%.0f" % (len(grays), W, H, TOL))
    print("")

    # ---- detailed look at the candidate d for pair 0->1 ------------------
    A, B = grays[0], grays[1]
    for d in (1048, 120, 394):
        cf, med, ys = row_stats(A, B, d)
        if cf is None:
            print("d=%d : not comparable" % d)
            continue
        print("pair0->1 d=%-5d rows=%-4d  meanColFrac=%.4f  "
              "rows>=0.90: %d (%.1f%%)  medianOfRowMedian=%.1f"
              % (d, len(ys), cf.mean(), int((cf >= 0.90).sum()),
                 100.0 * (cf >= 0.90).mean(), np.median(med)))
    print("")

    # ---- robust full scan -------------------------------------------------
    lo = 120
    hi = H - BOT_SKIP - 120
    print("robust scan d in [%d,%d] step 2" % (lo, hi))
    for i in range(len(grays) - 1):
        A, B = grays[i], grays[i + 1]
        d_py, c_py = S.find_offset(A, B, 0, 0)
        res = []
        for d in range(lo, hi + 1, 2):
            sc = robust_score(A, B, d)
            if sc is not None:
                res.append((d, sc))
        res.sort(key=lambda t: -t[1])
        print("=== pair %s -> %s   python d=%s cost=%.4f"
              % (names[i], names[i + 1], str(d_py), c_py))
        for d, sc in res[:6]:
            print("    d=%-5d meanColFrac=%.4f" % (d, sc))
        if d_py is not None:
            sc = robust_score(A, B, d_py)
            print("    python d=%d meanColFrac=%s"
                  % (d_py, ("%.4f" % sc) if sc is not None else "n/a"))
        print("")


if __name__ == "__main__":
    main()
