"""Global overlay estimation across ALL screenshots of a batch.

Why per-pair is wrong:
  group [0,1] has only ONE pair. If that pair happens to give bottom=24, the
  whole group keeps 2598 rows and the input bar gets baked into the long image.
  But the SAME device, SAME app, SAME session -> the overlay height is a
  constant. Estimating it from all pairs and applying it to every group is both
  more accurate and self-consistent.

Also: CHANGE_EPS must adapt. These samples are JPEG-recompressed (a real PNG
from the device has no compression noise), so eps=2 finds nothing while eps=12
recovers the truth. We scan a ladder of eps values and take the UNION of
"static" rows, then read the prefix/suffix.

Over-estimating top/bottom is SAFE: the neighbouring screenshot still supplies
that content, because min scroll (~0.2 * contentH) is far larger than any
overlay. Under-estimating is what corrupts the image.

Prints, per eps: top/bottom. Then the union-based global estimate.
Then re-runs the real stitcher with that global estimate and reports the
resulting heights, so we can compare against the device's 3384/3445/3485.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

EPS_LADDER = (2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0)
MAX_OVERLAY_FRAC = S.MAX_OVERLAY_FRAC
MIN_OVERLAY_H = S.MIN_OVERLAY_H


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def static_union(grays):
    """A row is 'static' if ANY eps in the ladder says so, across ALL pairs."""
    H, W = grays[0].shape
    max_changed = max(1, int(S.STATIC_CHANGED_FRAC * W))
    union = np.ones(H, dtype=bool)
    for i in range(len(grays) - 1):
        A, B = grays[i], grays[i + 1]
        per_eps = np.zeros(H, dtype=bool)
        for eps in EPS_LADDER:
            changed = (np.abs(A - B) >= eps).sum(axis=1)
            per_eps |= (changed <= max_changed)
        union &= per_eps
    return union


def prefix_suffix(st, H):
    top = 0
    while top < H and st[top]:
        top += 1
    bot = 0
    while bot < H and st[H - 1 - bot]:
        bot += 1
    return top, bot


def main():
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    grays = [load_gray(p) for p in files]
    H, W = grays[0].shape
    print("images=%d  %dx%d" % (len(grays), W, H))

    max_changed = max(1, int(S.STATIC_CHANGED_FRAC * W))
    print("max_changed=%d  EPS_LADDER=%s" % (max_changed, EPS_LADDER))
    print("")

    # per-pair, per-eps view
    for i in range(len(grays) - 1):
        A, B = grays[i], grays[i + 1]
        line = "pair%d " % i
        for eps in EPS_LADDER:
            changed = (np.abs(A - B) >= eps).sum(axis=1)
            st = changed <= max_changed
            t, b = prefix_suffix(st, H)
            line += " e%g=(%d,%d)" % (eps, t, b)
        print(line)

    # union across all pairs
    st = static_union(grays)
    print("")
    print("union static rows: %d / %d" % (int(st.sum()), H))
    t, b = prefix_suffix(st, H)
    print("union prefix/suffix: top=%d bottom=%d" % (t, b))

    # clamp like production
    top = t if t >= MIN_OVERLAY_H and t <= MAX_OVERLAY_FRAC * H else 0
    bot = b if b >= MIN_OVERLAY_H and b <= MAX_OVERLAY_FRAC * H else 0
    print("clamped (MIN_OVERLAY_H=%d, MAX_OVERLAY_FRAC=%.2f): top=%d bottom=%d"
          % (MIN_OVERLAY_H, MAX_OVERLAY_FRAC, top, bot))
    print("")

    # run the real stitcher with the global estimate forced
    rgbs = [np.asarray(Image.open(p).convert("RGB")) for p in files]
    orig = S.detect_overlays
    try:
        S.detect_overlays = lambda g, _t=top, _b=bot: (_t, _b)
        results, diag_all = S.stitch_all(rgbs, timestamps=None, verbose=False,
                                         keep_first_chrome=True)
        print("groups=%s breaks=%s" % (diag_all["groups"], diag_all["breaks"]))
        print("reasons=%s" % (diag_all["reasons"],))
        for gi, (img, d) in enumerate(results):
            print("  group%d h=%d top=%d bottom=%d content_h=%d d=%s"
                  % (gi, img.shape[0], d["top"], d["bottom"], d["content_h"],
                     d["d_list"]))
        print("sum heights = %d" % sum(im.shape[0] for im, _ in results))
    finally:
        S.detect_overlays = orig

    # also: what does the CURRENT production code give (for comparison)?
    results2, diag2 = S.stitch_all(rgbs, timestamps=None, verbose=False,
                                   keep_first_chrome=True)
    print("")
    print("PRODUCTION (unchanged) groups=%s heights=%s"
          % (diag2["groups"], [im.shape[0] for im, _ in results2]))
    for gi, (img, d) in enumerate(results2):
        print("  group%d h=%d top=%d bottom=%d d=%s"
              % (gi, img.shape[0], d["top"], d["bottom"], d["d_list"]))


if __name__ == "__main__":
    main()
