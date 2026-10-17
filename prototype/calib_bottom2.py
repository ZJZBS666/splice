"""Robust overlay detector: MEDIAN diff profile across all matched pairs.

Why the old detector fails on real screenshots:
  A row counts as "static" only if <= STATIC_CHANGED_FRAC*W pixels changed by
  >= CHANGE_EPS. Two problems:
    (1) the translucent dark bar has content showing through, so with a tight
        eps every row "changes" and the suffix is empty (bottom=0);
    (2) a single row with a big change (e.g. an unread badge, cursor, or JPEG
        ringing at y=2592 with diff=83) BREAKS the contiguous suffix, so a
        275-row bar is reported as 24.
  Both are fixed by (a) using the mean absolute difference at the SAME screen
  position instead of an exact-match pixel count, and (b) taking the MEDIAN
  across all pairs instead of trusting one pair.

Detector:
  diff_i(y) = mean |B_i[y] - A_i[y]|                 (same screen row)
  prof(y)   = median over matched pairs i of diff_i(y)
  row y is overlay  <=>  prof(y) < OVERLAY_DIFF_THR
  top    = longest prefix of overlay rows
  bottom = longest suffix of overlay rows (gaps up to GAP_TOL tolerated)

This is applied GLOBALLY to the whole batch (same app, same session, same
overlay geometry), not per pair.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

OVERLAY_DIFF_THR = 6.0
GAP_TOL = 12
MARGIN = 6


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def diff_profiles(grays, matched):
    """Per-pair same-position mean abs diff, for matched pairs only."""
    profs = []
    for i in matched:
        profs.append(np.abs(grays[i + 1] - grays[i]).mean(axis=1))
    return np.array(profs)


def median_profile(profs):
    return np.median(profs, axis=0)


def detect(prof, H, thr=OVERLAY_DIFF_THR):
    ov = prof < thr
    # prefix
    top = 0
    while top < H and ov[top]:
        top += 1
    # suffix, tolerating gaps
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


def clamp(top, bottom, H):
    mt = S.MIN_OVERLAY_H
    mf = S.MAX_OVERLAY_FRAC
    if top < mt or top > mf * H:
        top = 0
    if bottom < mt or bottom > mf * H:
        bottom = 0
    return top, bottom


def main():
    print("### REAL (truth: top~318, bottom~275 from visual ground truth)")
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    grays = [load_gray(p) for p in files]
    H = grays[0].shape[0]
    matched = [0, 1, 2, 4]
    profs = diff_profiles(grays, matched)
    prof = median_profile(profs)
    for thr in (3.0, 6.0, 10.0, 16.0):
        t, b = detect(prof, H, thr)
        tc, bc = clamp(t, b, H)
        print("  thr=%-5.1f raw top=%-4d bottom=%-4d | clamped top=%-4d bottom=%-4d"
              % (thr, t, b, tc, bc))
    # boundary detail
    print("  profile near bottom boundary:")
    for y in range(2320, 2380, 4):
        print("     y=%-5d median=%.2f" % (y, prof[y]))
    # single-pair behaviour, to show why median is needed
    print("  per-pair bottom with thr=6.0:")
    for i in matched:
        t1, b1 = detect(profs[matched.index(i)], H)
        print("     pair%d -> top=%d bottom=%d" % (i, t1, b1))
    print("")

    print("### SYNTHETIC (truth from gen_samples)")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        gg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
              for p in info["shots"]]
        Hs = gg[0].shape[0]
        pr = diff_profiles(gg, list(range(len(gg) - 1)))
        pf = median_profile(pr)
        t, b = detect(pf, Hs)
        tc, bc = clamp(t, b, Hs)
        print("  %-9s truth_top=%-4d truth_bot=%-4d | raw=(%d,%d) clamped=(%d,%d)"
              % (name, info["content_top"], info["content_bottom_bar"],
                 t, b, tc, bc))
        # per-pair spread, to confirm consistency
        bits = []
        for i in range(len(gg) - 1):
            t1, b1 = detect(pr[i], Hs)
            bits.append("(%d,%d)" % (t1, b1))
        print("      per-pair raw: %s" % " ".join(bits))


if __name__ == "__main__":
    main()
