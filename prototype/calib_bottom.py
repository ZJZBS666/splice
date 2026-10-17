"""Calibrate a robust BOTTOM overlay detector for real screenshots.

Root cause of the device bug (established):
  the bottom bar (WeChat input box / Settings search field) is TRANSLUCENT.
  Content shows through it, so its pixels are not pixel-identical between two
  screenshots. The current "static row" test therefore under-estimates the bar
  height, the leftover bar rows get baked into the middle of the long image,
  and exactly that many rows of real content are lost.

Two independent estimators are compared:

  (a) static_bottom : existing method. A row is "static" when the number of
      pixels changed by >= CHANGE_EPS is <= STATIC_CHANGED_FRAC * W.
      Works when the bar is opaque, fails when it is translucent.

  (b) struct_bottom : a row is "fixed overlay" when
          |A[y] - B[y]| < DIFF_THR          (same screen position, same look)
      AND row std >= STD_THR                (it carries UI structure, so it is
                                             not blank scrolling background)
      Take the contiguous suffix, tolerating short gaps.
      Blank content rows are excluded by the std test; content rows by the diff
      test; only real overlay rows satisfy both.

Over-estimating bottom is SAFE (the next screenshot supplies the content).
Under-estimating is what corrupts the image. So take max(a, b).

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIFF_THR = 5.0
STD_THR = 2.5
GAP_TOL = 6
FRAC_TOL = 0.85


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32)


def static_bottom(grays, eps):
    """Reuse the production criterion but with a caller-supplied eps."""
    A, B = grays[0], grays[1]
    H, W = A.shape
    max_changed = max(1, int(S.STATIC_CHANGED_FRAC * W))
    st = np.ones(H, dtype=bool)
    changed = (np.abs(A - B) >= eps).sum(axis=1)
    st &= changed <= max_changed
    y = H
    while y > 0 and st[y - 1]:
        y -= 1
    return H - y


def struct_bottom(A, B):
    H, W = A.shape
    diff = np.abs(A - B).mean(axis=1)
    sd = A[:, 30:W - 30].std(axis=1)
    ov = (diff < DIFF_THR) & (sd >= STD_THR)
    # contiguous suffix from the bottom, tolerating short gaps
    y = H
    gaps = 0
    for k in range(H - 1, -1, -1):
        if ov[k]:
            gaps = 0
            y = k
        else:
            gaps += 1
            if gaps > GAP_TOL:
                break
    if y >= H:
        return 0
    band = ov[y:H]
    if band.mean() < FRAC_TOL:
        return 0
    return H - y


def main():
    print("### REAL pairs")
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    rgbs = [load_rgb(p) for p in files]
    grays = [r.mean(axis=2) for r in rgbs]
    for i in range(len(rgbs) - 1):
        sb = {e: static_bottom([grays[i], grays[i + 1]], e)
              for e in (2.0, 6.0, 12.0)}
        ub = struct_bottom(grays[i], grays[i + 1])
        print("  pair%d %s->%s  static2=%d static6=%d static12=%d struct=%d  max=%d"
              % (i, os.path.basename(files[i])[:8],
                 os.path.basename(files[i + 1])[:8],
                 sb[2.0], sb[6.0], sb[12.0], ub, max(sb[12.0], ub)))

    print("")
    print("### SYNTHETIC pairs (truth = content_bottom_bar)")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        gg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
              for p in info["shots"]]
        truth = info["content_bottom_bar"]
        for k in range(len(gg) - 1):
            sb = static_bottom([gg[k], gg[k + 1]], 2.0)
            sb12 = static_bottom([gg[k], gg[k + 1]], 12.0)
            ub = struct_bottom(gg[k], gg[k + 1])
            print("  %-9s pair%d truth=%-4d static2=%-4d static12=%-4d struct=%-4d max=%-4d"
                  % (name, k, truth, sb, sb12, ub, max(sb12, ub)))


if __name__ == "__main__":
    main()
