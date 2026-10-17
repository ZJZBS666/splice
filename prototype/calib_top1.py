"""Top + bottom chrome from the 3-way row classification, using a known d.

Convention: B[y] == A[y + d]  (B is A scrolled down by d).

For a row y near the BOTTOM of A, its content (if it scrolls) must reappear
higher up in B, at B[y - d]:
    same  = |A[y] - B[y]|
    shift = |A[y] - B[y - d]|
    CONT (content) : same >= THR and shift <  THR
    FIX  (chrome)  : same <  THR and shift >= THR
    AMB  (blank)   : both <  THR
    NOIS           : both >= THR

For a row y near the TOP of B, its content (if it scrolls) must appear further
down in A, at A[y + d]:
    same  = |B[y] - A[y]|
    shift = |B[y] - A[y + d]|
    CONT : same >= THR and shift <  THR   -> y is content, not chrome

bottom = H - 1 - (largest CONT row of A)
top    = first CONT row of B

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

THR = 6.0
MAX_OVERLAY_FRAC = 0.22


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def bottom_by_class(A, B, d, thr=THR, max_frac=MAX_OVERLAY_FRAC):
    H = A.shape[0]
    y0 = max(int(H * (1.0 - max_frac)), d, 0)
    if y0 >= H:
        return 0
    ys = np.arange(y0, H)
    same = np.abs(A[ys] - B[ys]).mean(axis=1)
    shift = np.abs(A[ys] - B[ys - d]).mean(axis=1)
    cont = (same >= thr) & (shift < thr)
    idx = np.nonzero(cont)[0]
    if len(idx) == 0:
        return 0
    return H - 1 - int(ys[idx[-1]])


def top_by_class(A, B, d, thr=THR, max_frac=MAX_OVERLAY_FRAC):
    H = B.shape[0]
    y1 = min(int(H * max_frac), H - d)
    if y1 <= 0:
        return 0
    ys = np.arange(0, y1)
    same = np.abs(B[ys] - A[ys]).mean(axis=1)
    shift = np.abs(B[ys] - A[ys + d]).mean(axis=1)
    cont = (same >= thr) & (shift < thr)
    idx = np.nonzero(cont)[0]
    if len(idx) == 0:
        return 0
    return int(ys[idx[0]])


def main():
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    real = [load_gray(p) for p in files]

    print("### REAL  chat truth: top=318 bottom=276")
    for i, d in {0: 1048, 1: 1341, 2: 1109, 4: 778}.items():
        A, B = real[i], real[i + 1]
        print("  pair%d d=%-5d top=%-4d bottom=%-4d"
              % (i, d, top_by_class(A, B, d), bottom_by_class(A, B, d)))
    print("")

    print("### SYNTHETIC  (truth: top=318, bottom=content_bottom_bar)")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        gg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
              for p in info["shots"]]
        tb = info["content_bottom_bar"]
        tops, bots = [], []
        for i, d in enumerate(info["deltas"]):
            tops.append(top_by_class(gg[i], gg[i + 1], d))
            bots.append(bottom_by_class(gg[i], gg[i + 1], d))
        print("  %-9s top=%-14s bottom=%-18s truth_bot=%d"
              % (name, str(tops), str(bots), tb))


if __name__ == "__main__":
    main()
