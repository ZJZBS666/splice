"""Locate the overlay boundary by the STEP in row statistics.

Why the pure pixel-diff rule is ambiguous:
  On pair0 the rows just above the input bar (2256..2345) are blank dark chat
  background: flat (std ~0.0..1.5) and identical between the two shots. The bar
  body just below (2352..2582) is ALSO flat and identical. A diff test cannot
  separate them, so the suffix walk either stops at the bar's real top (2346) or
  runs on into blank content (2256) depending on tolerance.

The bar's top edge is still a hard visual edge. Row statistics jump there:
  dbg_feat.py img0:  y=2340 std=1.45  edge=0
                     y=2346 std=11.84 edge=24
So: take the identical suffix, then refine its upper boundary to the row with
the strongest step in (mean, std) of BOTH images.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

THR = 6.0
SEARCH = 60


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def identical_suffix(A, B, thr=THR, gap_tol=24):
    H = A.shape[0]
    diff = np.abs(B - A).mean(axis=1)
    bottom = 0
    bad = 0
    for k in range(H - 1, -1, -1):
        if diff[k] < thr:
            bad = 0
            bottom = H - k
        else:
            bad += 1
            if bad > gap_tol:
                break
    return bottom


def step_profile(A, B):
    """Row-to-row discontinuity of mean and std, both images."""
    out = np.zeros(A.shape[0], dtype=np.float32)
    for g in (A, B):
        m = g.mean(axis=1)
        s = g.std(axis=1)
        dm = np.abs(np.diff(m, prepend=m[:1]))
        ds = np.abs(np.diff(s, prepend=s[:1]))
        out += dm + ds
    return out


def refine(A, B, bottom, search=SEARCH):
    H = A.shape[0]
    if bottom <= 0:
        return bottom
    y0 = H - bottom
    lo = max(0, y0 - search)
    hi = min(H - 2, y0 + search)
    if hi <= lo:
        return bottom
    st = step_profile(A, B)
    k = lo + int(np.argmax(st[lo:hi]))
    return H - k


def main():
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    real = [load_gray(p) for p in files]
    print("### REAL  truth bottom=275")
    for i in range(len(real) - 1):
        A, B = real[i], real[i + 1]
        b0 = identical_suffix(A, B)
        b1 = refine(A, B, b0)
        print("  pair%d raw=%-4d refined=%-4d" % (i, b0, b1))
    print("")

    print("### SYNTHETIC  (truth bottom_bar)")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        gg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
              for p in info["shots"]]
        tb = info["content_bottom_bar"]
        bits = []
        for i in range(len(gg) - 1):
            b0 = identical_suffix(gg[i], gg[i + 1])
            b1 = refine(gg[i], gg[i + 1], b0)
            bits.append("%d->%d" % (b0, b1))
        print("  %-9s truth=%-4d %s" % (name, tb, "  ".join(bits)))


if __name__ == "__main__":
    main()
