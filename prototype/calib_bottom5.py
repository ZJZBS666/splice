"""Single-pair overlay detection: handle rows that carry NO information.

The blocker, measured on pair0:
  rows 2256..2345 are FLAT dark (std 0.0..1.5, luminance 17.0) in BOTH shots.
  The chat's background there is empty, so it does not move even though it is
  CONTENT. A pixel-diff test cannot tell "static because overlay" from "static
  because the content is blank", so the contiguous suffix walks straight through
  the bar and keeps going into blank content.

Two ideas tested here:

  R_flat : a row is overlay-ish if (diff < THR) OR (both rows nearly flat,
           std < FLAT_STD). Walking up from the bottom, stop only after
           BARRIER consecutive rows that are informative AND mismatched.
           Blank rows are therefore treated as "unknown -> assume overlay",
           which errs toward cropping too much. That is the SAFE direction:
           cropping blank dark rows is invisible, keeping bar residue is not.

  R_ratio: a row is content if it matches A[y+d] clearly better than A[y]
           (scrolled < 0.5 * same). Overlay rows do the opposite. Rows where
           both are tiny are "unknown -> assume overlay".

Ground truth: real bottom ~275 (WeChat input bar top edge at y=2346, visible in
dbg_feat.py as the row where std jumps 1.45 -> 11.84 and edge 0 -> 24).

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

KNOWN_D = {0: 1048, 1: 1341, 2: 1109, 3: None, 4: 778}
TRUTH_BOTTOM = 275
TRUTH_TOP = 318


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def walk(mask, H, barrier):
    """Longest suffix of True, tolerating runs of False shorter than barrier."""
    bottom = 0
    bad = 0
    for k in range(H - 1, -1, -1):
        if mask[k]:
            bad = 0
            bottom = H - k
        else:
            bad += 1
            if bad >= barrier:
                break
    return bottom


def rule_flat(A, B, d, thr, flat_std, barrier):
    H = A.shape[0]
    diff = np.abs(B - A).mean(axis=1)
    flat = (A.std(axis=1) < flat_std) & (B.std(axis=1) < flat_std)
    mask = (diff < thr) | flat
    return walk(mask, H, barrier)


def rule_ratio(A, B, d, min_sig, barrier):
    H, W = A.shape
    same = np.abs(B - A).mean(axis=1)
    ys = np.arange(H)
    scrolled = np.full(H, 1e9, dtype=np.float32)
    lo = 0
    hi = H - d
    if hi > lo:
        scrolled[lo:hi] = np.abs(B[lo:hi] - A[lo + d:hi + d]).mean(axis=1)
    sig = (same > min_sig) | (scrolled > min_sig)
    content = sig & (scrolled < 0.5 * same)
    return walk(~content, H, barrier)


def top_from(prof_mask, H, cap_frac=0.22):
    top = 0
    cap = int(cap_frac * H)
    while top < cap and prof_mask[top]:
        top += 1
    return top


def main():
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    real = [load_gray(p) for p in files]

    print("### REAL single pairs (truth bottom=%d)" % TRUTH_BOTTOM)
    for i, d in KNOWN_D.items():
        if d is None:
            continue
        A, B = real[i], real[i + 1]
        H = A.shape[0]
        outs = []
        for thr, fs, bar in ((6.0, 1.0, 20), (6.0, 2.0, 20), (6.0, 2.0, 30),
                             (10.0, 2.0, 20)):
            b = rule_flat(A, B, d, thr, fs, bar)
            outs.append("flat(thr=%g,fs=%g,bar=%d)=%d" % (thr, fs, bar, b))
        for ms, bar in ((3.0, 20), (6.0, 20), (6.0, 30)):
            b = rule_ratio(A, B, d, ms, bar)
            outs.append("ratio(ms=%g,bar=%d)=%d" % (ms, bar, b))
        print("  pair%d d=%-5d %s" % (i, d, "  ".join(outs)))
    print("")

    print("### SYNTHETIC single pair (truth from gen_samples)")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        gg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
              for p in info["shots"]]
        tb = info["content_bottom_bar"]
        tt = info["content_top"]
        A, B = gg[0], gg[1]
        H = A.shape[0]
        d = info["deltas"][0]
        outs = []
        for thr, fs, bar in ((6.0, 1.0, 20), (6.0, 2.0, 20), (10.0, 2.0, 20)):
            b = rule_flat(A, B, d, thr, fs, bar)
            outs.append("flat(thr=%g,fs=%g)=%d" % (thr, fs, b))
        for ms, bar in ((3.0, 20), (6.0, 20)):
            b = rule_ratio(A, B, d, ms, bar)
            outs.append("ratio(ms=%g)=%d" % (ms, b))
        print("  %-9s truth=(%d,%d) %s" % (name, tt, tb, "  ".join(outs)))


if __name__ == "__main__":
    main()
