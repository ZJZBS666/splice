"""Decisive test: what happens when top=0 (real-device translucent status bar)?

On a real iPhone the status bar / nav bar are translucent and sit ON TOP of
scrolling content, so static_rows() cannot see them as static and
detect_overlays() returns top=0. The synthetic generator drew them opaque,
which is why every test so far used top~318.

Device output heights 3384 / 3445 / 3485 imply (bottom=286):
    sum(d) = 1048 / 1109 / 1149  -> 3 groups of 2 shots

This script audits every pair under several (top,bottom) so we can see
which combination reproduces that grouping.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"


def load_gray(path):
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.uint8)
    return S.to_gray(rgb)


def audit(gs, top, bot, label):
    print("=== %s  top=%d bot=%d ===" % (label, top, bot))
    ds = []
    for i in range(len(gs) - 1):
        A, B = gs[i], gs[i + 1]
        d, cost = S.find_offset(A, B, top, bot)
        if d is None:
            ds.append(None)
            print("  pair%d -> None (cost=%.4f)" % (i, cost))
            continue
        agree, devs = S.band_votes(A, B, d, top, bot)
        sdA1 = S._row_sd(A, S.FINE_COL_STRIDE)
        got = S._cost_at(A, B, d, top, bot, sdA1,
                         S.FINE_ROW_STRIDE, S.FINE_COL_STRIDE)
        c2, used, ys, rne, tex = got
        n_tex = int(tex.sum())
        uf = used / float(n_tex) if n_tex else 0.0
        ds.append(d)
        print("  pair%d d=%-5d cost=%.4f agree=%d/%d n_tex=%d uf=%.3f"
              % (i, d, c2, agree, S.BAND_COUNT, n_tex, uf))
    # grouping by None
    groups = []
    cur = [0]
    for i, d in enumerate(ds):
        if d is None:
            groups.append(cur)
            cur = [i + 1]
        else:
            cur.append(i + 1)
    groups.append(cur)
    hs = [(2622 - bot) + sum(x for x in ds if x is not None and False) for _ in [0]]
    heights = []
    for g in groups:
        s = 0
        for k in range(len(g) - 1):
            s += ds[g[k]] or 0
        heights.append((2622 - bot) + s)
    print("  groups=%s heights=%s" % (groups, heights))
    print("  DEVICE was groups of 2, heights [3384, 3445, 3485]")
    print("")


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    gs = [load_gray(p) for p in files]
    audit(gs, 0, 286, "translucent status bar (real device)")
    audit(gs, 0, 34, "translucent + home bar only")
    audit(gs, 0, 0, "no overlays at all")


if __name__ == "__main__":
    main()
