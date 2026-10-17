"""Candidate final rule, evaluated per pair and as a batch.

Rule per pair i:
  diff_i(y) = mean |B_i[y] - A_i[y]|            (same screen row)
  flat_i(y) = stdA(y) < FS and stdB(y) < FS     (blank content, no information)
  mask_i(y) = diff_i(y) < THR or flat_i(y)
  bottom_i  = longest suffix of mask, tolerating mismatch runs < GAP_TOL
  top_i     = longest prefix of mask, same tolerance

Batch:
  top = max(top_i), bottom = max(bottom_i)  over matched pairs.

Why max: under-cropping a fixed overlay is catastrophic (the overlay's rows are
injected at the seam AND that many content rows are dropped, because assemble
takes B's bottom d rows of its content region). Over-cropping is harmless for
every image except the last: the rows cut from image i are supplied by image
i+1 through the overlap. So erring large is the safe direction.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

THR = 6.0
FS = 2.0
GAP_TOL = 24
MIN_OV = S.MIN_OVERLAY_H
MAX_OV = 0.22


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def walk_up(mask, H, gap_tol):
    bottom = 0
    bad = 0
    for k in range(H - 1, -1, -1):
        if mask[k]:
            bad = 0
            bottom = H - k
        else:
            bad += 1
            if bad > gap_tol:
                break
    return bottom


def walk_down(mask, H, gap_tol, cap_frac=MAX_OV):
    cap = int(cap_frac * H)
    top = 0
    bad = 0
    for k in range(0, cap):
        if mask[k]:
            bad = 0
            top = k + 1
        else:
            bad += 1
            if bad > gap_tol:
                break
    return top


def pair_masks(A, B, thr=THR, fs=FS):
    diff = np.abs(B - A).mean(axis=1)
    flat = (A.std(axis=1) < fs) & (B.std(axis=1) < fs)
    return (diff < thr) | flat


def estimates(A, B, gap_tol=GAP_TOL):
    H = A.shape[0]
    m = pair_masks(A, B)
    return walk_down(m, H, gap_tol), walk_up(m, H, gap_tol)


def clamp_batch(top, bottom, H):
    if top < MIN_OV:
        top = 0
    if bottom < MIN_OV:
        bottom = 0
    if top > MAX_OV * H:
        top = 0
    if bottom > MAX_OV * H:
        bottom = 0
    if top + bottom > 0.5 * H:
        return 0, 0
    return top, bottom


def main():
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    real = [load_gray(p) for p in files]
    H = real[0].shape[0]
    print("### REAL  truth top=318 bottom=275")
    for i in range(len(real) - 1):
        t, b = estimates(real[i], real[i + 1])
        print("  pair%d  top=%-4d bottom=%-4d" % (i, t, b))
    for grp in ([0, 1], [2, 3], [4, 5], [0, 1, 2, 3]):
        ts, bs = [], []
        for i in range(len(grp) - 1):
            t, b = estimates(real[grp[i]], real[grp[i + 1]])
            ts.append(t)
            bs.append(b)
        t, b = max(ts), max(bs)
        print("  group %-14s raw top=%-4d bottom=%-4d -> clamped %s"
              % (str(grp), t, b, clamp_batch(t, b, H)))
    print("")

    print("### SYNTHETIC  (truth top / bottom_bar)")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        gg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
              for p in info["shots"]]
        Hs = gg[0].shape[0]
        ts, bs = [], []
        for i in range(len(gg) - 1):
            t, b = estimates(gg[i], gg[i + 1])
            ts.append(t)
            bs.append(b)
        bt, bb = clamp_batch(max(ts), max(bs), Hs)
        at, ab = clamp_batch(max(ts[:1]), max(bs[:1]), Hs)
        print("  %-9s truth=(%d,%d) allpairs=(%d,%d) err=%d | onlypair0=(%d,%d) err=%d"
              % (name, info["content_top"], info["content_bottom_bar"],
                 bt, bb,
                 abs((bt if bt >= MIN_OV else 0) - info["content_top"])
                 + abs(bb - info["content_bottom_bar"]),
                 at, ab,
                 abs((at if at >= MIN_OV else 0) - info["content_top"])
                 + abs(ab - info["content_bottom_bar"])))
        print("      per-pair raw: %s"
              % " ".join("(%d,%d)" % (t, b) for t, b in zip(ts, bs)))


if __name__ == "__main__":
    main()
