"""Why does a NON-overlapping pair score cost=0.24?

Hypothesis: dark-mode chat screenshots are mostly pure black. Black rows are
identical at ANY offset, so both the exact-match fraction and the normalized-L1
cost are dominated by content-free rows. The metric measures "does this look
like a chat screenshot", not "is this the same content".

Test: score ONLY strongly textured rows and require near-exact pixel agreement.

For every d compute
    tex_frac = fraction of rows with sdA >= TEX_SD whose max|diff| <= TOL
    n_tex    = number of such rows
A true overlap must give tex_frac close to 1.0 over a meaningful row count.

Also scan the REVERSE direction, to detect a scroll-up between shots.

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
TEX_SD = 6.0
TOL = 16.0


def load_gray(path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    return a @ np.array([0.299, 0.587, 0.114], np.float32)


def tex_frac_at(A, B, d, sdA, tol=TOL, tex_sd=TEX_SD, row_stride=2):
    H, W = A.shape
    y0 = TOP_SKIP
    y1 = H - BOT_SKIP - d
    if y1 - y0 < 60:
        return None, 0
    ys = np.arange(y0, y1, row_stride)
    sd = sdA[ys + d]
    tex = sd >= tex_sd
    n_tex = int(tex.sum())
    if n_tex < 20:
        return None, n_tex
    err = np.abs(A[ys + d] - B[ys]).max(axis=1)
    ok = err < tol
    return float(ok[tex].mean()), n_tex


def scan_dir(A, B, sdA, lo, hi, step=2):
    out = []
    for d in range(lo, hi + 1, step):
        f, n = tex_frac_at(A, B, d, sdA)
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
    print("count=%d size=%dx%d tex_sd=%.0f tol=%.0f"
          % (len(grays), W, H, TEX_SD, TOL))
    print("")

    lo = 120
    hi = H - BOT_SKIP - 120

    for i in range(len(grays) - 1):
        A, B = grays[i], grays[i + 1]
        sdA = S._row_sd(A, 1)
        sdB = S._row_sd(B, 1)
        d_py, c_py = S.find_offset(A, B, 0, 0)
        print("=== pair %s -> %s ===" % (names[i], names[i + 1]))
        print("  python: d=%s cost=%.4f" % (str(d_py), c_py))
        fwd = scan_dir(A, B, sdA, lo, hi)
        print("  FORWARD (B scrolled down) top5:")
        for d, f, n in fwd[:5]:
            print("    d=%-5d tex_frac=%.4f n_tex=%d" % (d, f, n))
        rev = scan_dir(B, A, sdB, lo, hi)
        print("  REVERSE (B scrolled up)   top5:")
        for d, f, n in rev[:5]:
            print("    d=%-5d tex_frac=%.4f n_tex=%d" % (d, f, n))
        if d_py is not None:
            f, n = tex_frac_at(A, B, d_py, sdA)
            print("  python d tex_frac=%s n_tex=%d"
                  % (("%.4f" % f) if f is not None else "n/a", n))
        print("")

    print("verdict: tex_frac >= 0.90 with n_tex >= 100 means a real overlap.")
    print("         anything below ~0.60 means these shots do NOT overlap.")


if __name__ == "__main__":
    main()
