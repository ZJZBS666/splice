"""Pick the aggregation rule for the overlay profile: median vs max vs min.

Concern: with only TWO screenshots there is a single pair, so "median across
pairs" degenerates to that one pair. pair0 of the real set alone reports
bottom=24 instead of ~275, which is exactly the bug we are fixing. So the rule
must also work with one pair.

Rules under test:
  median : robust to a minority of odd pairs, but degenerate with one pair
  max    : overlay row is low in EVERY pair -> max stays low; a content row is
           high in at least one pair -> max is high. Immune to blank content
           appearing identical in one pair. Sensitive to noise spikes, which
           GAP_TOL absorbs.
  min    : overly permissive, blank rows pass

Evaluate on: all real pairs, each single real pair, and the synthetic sets
(whose ground truth is known).

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

THRS = (4.0, 6.0, 8.0, 10.0, 12.0)
GAP_TOL = 12


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def profiles(grays):
    return [np.abs(grays[i + 1] - grays[i]).mean(axis=1)
            for i in range(len(grays) - 1)]


def detect(prof, H, thr):
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
            if gaps > GAP_TOL:
                break
    return top, bottom


def report(tag, grays, truth_top, truth_bot):
    H = grays[0].shape[0]
    pr = profiles(grays)
    arr = np.array(pr)
    aggs = {
        "median": np.median(arr, axis=0),
        "max": arr.max(axis=0),
        "min": arr.min(axis=0),
    }
    bits = []
    for name, prof in aggs.items():
        best = None
        for thr in THRS:
            t, b = detect(prof, H, thr)
            # score: distance to truth (top matters only above MIN_OVERLAY_H)
            st = t if t >= S.MIN_OVERLAY_H else 0
            err = abs(st - truth_top) + abs(b - truth_bot)
            if best is None or err < best[0]:
                best = (err, thr, st, b)
        bits.append("%s(thr=%g top=%d bot=%d err=%d)"
                    % (name, best[1], best[2], best[3], best[0]))
    print("  %-28s %s" % (tag, "  ".join(bits)))


def main():
    print("### REAL (truth top=318 bottom~275)")
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    grays = [load_gray(p) for p in files]
    report("all 6 images (5 pairs)", grays, 318, 275)
    for i in range(len(grays) - 1):
        report("only pair%d" % i, [grays[i], grays[i + 1]], 318, 275)
    print("")

    print("### SYNTHETIC (truth known)")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        gg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
              for p in info["shots"]]
        report("%s all" % name, gg, info["content_top"],
               info["content_bottom_bar"])
        report("%s only pair0" % name, gg[:2], info["content_top"],
               info["content_bottom_bar"])


if __name__ == "__main__":
    main()
