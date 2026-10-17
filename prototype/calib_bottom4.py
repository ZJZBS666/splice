"""Fix the two remaining weaknesses of the profile detector.

Weakness 1 (why pair0 reports bottom=24 instead of ~272):
  A single row with a large diff (JPEG ringing at y=2592, diff=83) breaks the
  contiguous suffix. GAP_TOL only helps if the spike is shorter than the gap
  budget, and here the spike sits inside an otherwise-flat run so the walk
  should continue... unless several such spikes cluster. Smoothing the profile
  with a moving average removes them by construction.

Weakness 2 (why max-aggregation failed on the real set):
  Non-matching pairs (a big jump, or a different app screen) have huge diff on
  EVERY row, so including them poisons any aggregate. Only matched pairs
  (pairs where find_offset returned a d) may contribute.

New rule under test:
  prof_i = moving_average(|A_i[y] - B_i[y]|, WIN)        for matched pairs only
  prof   = max_i prof_i
  overlay row <=> prof < THR
  top / bottom from the prefix / suffix, minus MARGIN to compensate smoothing

max is the theoretically right aggregate: an overlay row is low in EVERY pair,
so its max stays low; a content row is high in at least one pair, so its max is
high. Blank content that happens to look identical in one pair cannot fake it.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

THRS = (3.0, 4.0, 5.0, 6.0, 8.0, 10.0)


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def smooth(a, w):
    if w <= 1:
        return a
    k = np.ones(w, dtype=np.float32) / float(w)
    return np.convolve(a, k, mode="same")


def detect(prof, H, thr, margin, gap_tol=12):
    ov = prof < thr
    top = 0
    while top < H and ov[top]:
        top += 1
    bottom = 0
    gaps = 0
    for k in range(H - 1, -1, -1):
        if ov[k]:
            gaps = 0
            bottom = H - k
        else:
            gaps += 1
            if gaps > gap_tol:
                break
    top = max(0, top - margin)
    bottom = max(0, bottom - margin)
    return top, bottom


def evaluate(tag, grays, matched, truth_top, truth_bot, win, agg):
    H = grays[0].shape[0]
    pr = []
    for i in matched:
        pr.append(smooth(np.abs(grays[i + 1] - grays[i]).mean(axis=1), win))
    if not pr:
        print("  %-30s no matched pairs" % tag)
        return
    arr = np.array(pr)
    prof = arr.max(axis=0) if agg == "max" else np.median(arr, axis=0)
    margin = win // 2
    best = None
    for thr in THRS:
        t, b = detect(prof, H, thr, margin)
        st = t if t >= S.MIN_OVERLAY_H else 0
        err = abs(st - truth_top) + abs(b - truth_bot)
        if best is None or err < best[0]:
            best = (err, thr, st, b)
    print("  %-30s win=%-3d agg=%-6s thr=%-4g top=%-4d bot=%-4d err=%d"
          % (tag, win, agg, best[1], best[2], best[3], best[0]))


def main():
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    real = [load_gray(p) for p in files]

    print("### REAL  truth top=318 bottom=272")
    for win in (1, 9, 15, 21):
        for agg in ("max", "median"):
            evaluate("all matched [0,1,2,4]", real, [0, 1, 2, 4], 318, 272, win, agg)
    print("")
    for win in (1, 9, 15, 21):
        for agg in ("max", "median"):
            evaluate("only pair0 (single)", real, [0], 318, 272, win, agg)
    print("")
    for win in (1, 9, 15, 21):
        for agg in ("max", "median"):
            evaluate("only pair1 (single)", real, [1], 318, 272, win, agg)
    print("")

    print("### SYNTHETIC")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        gg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
              for p in info["shots"]]
        tt, tb = info["content_top"], info["content_bottom_bar"]
        allp = list(range(len(gg) - 1))
        for win in (1, 9, 15, 21):
            evaluate("%s all pairs" % name, gg, allp, tt, tb, win, "max")
        for win in (1, 9, 15, 21):
            evaluate("%s only pair0" % name, gg, [0], tt, tb, win, "max")
        print("")


if __name__ == "__main__":
    main()
