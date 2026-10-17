"""Simulate Swift's analyzeAll EXACTLY and compare with Python's stitch_all.

Suspected divergence:
  Python stitch_all -> breaks by (time, find_offset with per-pair overlays)
                       then stitch_group RE-RUNS find_offset with the GROUP's
                       overlays, so offsets and crop bounds are consistent.
  Swift  analyzeAll  -> computes pairOffsets with PER-PAIR overlays, then
                       renders with the GROUP's overlays. If the two overlay
                       measurements differ, offsets and crop bounds disagree.

Also: CHANGE_EPS=2.0 fails on these JPEGs (compression noise). Set it to 12
to emulate what the device sees with lossless PNGs.

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


def swift_analyze_all(gs, keep_first_chrome=True):
    """Mimic Stitcher.analyzeAll + assemble."""
    n = len(gs)
    pair_off, pair_cost = [None] * (n - 1), [0.0] * (n - 1)
    breaks = []
    per_pair_ovl = []
    for i in range(n - 1):
        top, bot = S.detect_overlays([gs[i], gs[i + 1]])
        per_pair_ovl.append((top, bot))
        d, c = S.find_offset(gs[i], gs[i + 1], top, bot)
        pair_off[i], pair_cost[i] = d, c
        if d is None:
            breaks.append(i)

    groups, start = [], 0
    for b in breaks:
        groups.append(list(range(start, b + 1)))
        start = b + 1
    groups.append(list(range(start, n)))

    out = []
    for g in groups:
        top, bot = S.detect_overlays([gs[i] for i in g])
        offs = [pair_off[g[k]] for k in range(len(g) - 1)]
        # assemble exactly like Swift: contentH = H - top - bot
        content_h = gs[0].shape[0] - top - bot
        chrome_h = top if keep_first_chrome else 0
        h = chrome_h + content_h
        for d in offs:
            h += content_h if d is None else d
        out.append({"group": g, "top": top, "bot": bot, "offs": offs,
                    "height": h})
    return per_pair_ovl, out


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    gs = [load_gray(p) for p in files]
    H = gs[0].shape[0]

    for eps in (2.0, 12.0):
        S.CHANGE_EPS = eps
        print("=== CHANGE_EPS=%.1f ===" % eps)
        ovl, plans = swift_analyze_all(gs)
        print("  per-pair overlays: %s" % (ovl,))
        for p in plans:
            print("  group=%s top=%d bot=%d offs=%s height=%d"
                  % (p["group"], p["top"], p["bot"], p["offs"], p["height"]))
        print("  -> %d long image(s), heights=%s"
              % (len(plans), [p["height"] for p in plans]))
        print("  DEVICE: 3 long images, heights [3384, 3445, 3485]")
        print("")

    S.CHANGE_EPS = 12.0
    print("=== reference: python stitch_all (self-consistent) ===")
    rgbs = [np.asarray(Image.open(p).convert("RGB")).astype(np.uint8)
            for p in files]
    res, da = S.stitch_all(rgbs, verbose=False, keep_first_chrome=True)
    print("  groups=%s heights=%s"
          % (da["groups"], [r[1]["height"] for r in res]))


if __name__ == "__main__":
    main()
