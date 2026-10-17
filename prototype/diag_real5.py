"""Decisive test: is the chosen d a TRUE overlap or a false match?

The normalized-L1 cost of 0.24-0.37 on real JPEGs is suspicious: exact
synthetic matches score 0.0000, and JPEG noise alone cannot produce 0.37.

Method
  * mask out the chrome bands (top nav bar rows 0..NAV_END and bottom input
    bar + home indicator rows BOT_END..H) because they are near-static and
    inflate any similarity score
  * for every d, compute the fraction of remaining rows whose MAX abs pixel
    difference is below TOL (two tolerances: 8 = JPEG-friendly, 24 = loose)
  * a TRUE overlap must show a sharp peak with frac close to 1.0

If no d exceeds ~0.6 the pair simply does not overlap and the only correct
answer is "hard stitch with a divider", not a guessed d.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"

# chrome bands to ignore while scoring (rows from the top / rows from bottom)
TOP_SKIP = 300
BOT_SKIP = 280


def load_gray(path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    return a @ np.array([0.299, 0.587, 0.114], np.float32)


def frac_at(A, B, d, tol, top_skip=TOP_SKIP, bot_skip=BOT_SKIP,
            row_stride=2, col_stride=1):
    H, W = A.shape
    y0 = top_skip
    y1 = H - bot_skip - d
    if y1 - y0 < 60:
        return None, 0
    ys = np.arange(y0, y1, row_stride)
    a = A[ys + d][:, ::col_stride]
    b = B[ys][:, ::col_stride]
    err = np.abs(a - b).max(axis=1)
    return float((err < tol).mean()), int(len(ys))


def scan(A, B, tol, lo, hi, step):
    out = []
    for d in range(lo, hi + 1, step):
        f, n = frac_at(A, B, d, tol)
        if f is not None:
            out.append((d, f, n))
    out.sort(key=lambda t: (-t[1], t[0]))
    return out


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    names = [os.path.basename(p)[:8] for p in files]
    grays = [load_gray(p) for p in files]
    H, W = grays[0].shape
    print("count=%d size=%dx%d  top_skip=%d bot_skip=%d"
          % (len(grays), W, H, TOP_SKIP, BOT_SKIP))
    print("")

    lo = 120
    hi = H - BOT_SKIP - 120
    print("scan range d in [%d, %d]" % (lo, hi))
    print("")

    for i in range(len(grays) - 1):
        A, B = grays[i], grays[i + 1]
        print("=== pair %s -> %s ===" % (names[i], names[i + 1]))
        d_py, c_py = S.find_offset(A, B, 0, 0)
        print("  python find_offset: d=%s cost=%.4f" % (str(d_py), c_py))
        for tol in (8.0, 24.0):
            res = scan(A, B, tol, lo, hi, 4)
            print("  tol=%.0f  top6:" % tol)
            for d, f, n in res[:6]:
                print("    d=%-5d frac=%.4f rows=%d" % (d, f, n))
            # refine +-4 around the best at step 1
            bd = res[0][0]
            fine = []
            for d in range(max(lo, bd - 4), min(hi, bd + 4) + 1):
                f, n = frac_at(A, B, d, tol)
                if f is not None:
                    fine.append((d, f, n))
            fine.sort(key=lambda t: (-t[1], t[0]))
            print("    best refined: d=%d frac=%.4f"
                  % (fine[0][0], fine[0][1]))
            if d_py is not None:
                fp, _ = frac_at(A, B, d_py, tol)
                print("    frac at python's d=%d : %s"
                      % (d_py, ("%.4f" % fp) if fp is not None else "n/a"))
        print("")

    print("=== verdict guide ===")
    print("  frac >= 0.85 at the chosen d  -> true overlap, d is right")
    print("  no d above ~0.60              -> pair does not overlap at all")
    print("                                   (must hard-stitch, never guess)")


if __name__ == "__main__":
    main()
