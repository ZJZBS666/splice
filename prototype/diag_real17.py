"""Per-pair gate audit on the real shots.

For each consecutive pair print: d, cost, band agree, n_tex, used_frac,
and the margin to each gate. The device seems to break more pairs than
Python does, so we need to know which gate is marginal.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"
TOP, BOT = 318, 286


def load_gray(path):
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.uint8)
    return S.to_gray(rgb)


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    gs = [load_gray(p) for p in files]
    print("pairs=%d  top=%d bot=%d" % (len(gs) - 1, TOP, BOT))
    for i in range(len(gs) - 1):
        A, B = gs[i], gs[i + 1]
        H = A.shape[0]
        lo = max(int(S.MIN_SCROLL_FRAC * (H - TOP - BOT)), S.FINE_WINDOW)
        hi = H - BOT - max(24, int(S.MIN_OVERLAP_FRAC * H)) - TOP
        d, cost = S.find_offset(A, B, TOP, BOT)
        sdC = S._row_sd(A, S.COARSE_COL_STRIDE)
        if d is None:
            print("pair%d -> None (cost=%.4f) window=[%d,%d]" % (i, cost, lo, hi))
            continue
        agree, devs = S.band_votes(A, B, d, TOP, BOT)
        sdA1 = S._row_sd(A, S.FINE_COL_STRIDE)
        got = S._cost_at(A, B, d, TOP, BOT, sdA1,
                         S.FINE_ROW_STRIDE, S.FINE_COL_STRIDE)
        c2, used, ys, rne, tex = got
        n_tex = int(tex.sum())
        uf = used / float(n_tex) if n_tex else 0.0
        print("pair%d d=%-5d cost=%.4f agree=%d/%d devs=%s n_tex=%d used=%d uf=%.3f"
              " | gates: agree>=%d %s, ntex>=%d %s, uf>=%.2f %s"
              % (i, d, c2, agree, S.BAND_COUNT, devs, n_tex, used, uf,
                 S.MIN_BAND_AGREE, "OK" if agree >= S.MIN_BAND_AGREE else "FAIL",
                 S.MIN_MATCH_ROWS, "OK" if n_tex >= S.MIN_MATCH_ROWS else "FAIL",
                 S.MIN_USED_FRAC, "OK" if uf >= S.MIN_USED_FRAC else "FAIL"))


if __name__ == "__main__":
    main()
