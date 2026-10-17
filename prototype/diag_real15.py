"""Why does the device produce a much shorter long image than Python?

Python's find_offset on these real shots gives d = 1048 / 1341 / 1109 / - / 778.
The device's own long images have height 3384 / 3445 / 3485, which implies
sum(d) ~ 796..897 for a 2-image group.

Hypothesis to test: the difference is entirely in detect_overlays. On the
device the shots are clean PNGs, so static_rows() succeeds; on the JPEG
re-encodes we were given it fails and returns (0, 0).

So: force (top, bottom) to a grid and see which combination reproduces
the device heights. Also print what the device would get.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"
H = 2622
W = 1206


def load_rgb(path):
    im = Image.open(path).convert("RGB")
    return np.asarray(im).astype(np.uint8)


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    names = [os.path.basename(p)[:8] for p in files]
    rgbs = [load_rgb(p) for p in files]

    grid = [(0, 0), (0, 34), (318, 34), (318, 270), (321, 34), (318, 200),
            (318, 214), (318, 0)]

    orig = S.detect_overlays
    for (top, bot) in grid:
        S.detect_overlays = lambda g, t=top, b=bot: (t, b)
        res, da = S.stitch_all(rgbs, verbose=False, keep_first_chrome=True)
        hs = [r[1]["height"] for r in res]
        dl = [[p["d"] for p in r[1]["pairs"]] for r in res]
        print("top=%3d bot=%3d -> groups=%s heights=%s sum=%d d_lists=%s"
              % (top, bot, da["groups"], hs, sum(hs), dl))
        if hs == [3384, 3445, 3485] or sum(hs) in (3384, 3445, 3485):
            print("   *** MATCHES DEVICE HEIGHT ***")
        print("")
    S.detect_overlays = orig

    # also: single pair 0->1 with each (top,bot), for direct comparison
    print("--- pair 0->1 d under each (top,bottom) ---")
    g0 = S.to_gray(rgbs[0])
    g1 = S.to_gray(rgbs[1])
    for (top, bot) in grid:
        d, c = S.find_offset(g0, g1, top, bot)
        content_h = H - top - bot
        implied_h = (H - bot) + (d if d else 0)
        print("top=%3d bot=%3d  d=%s cost=%.4f  content_h=%4d  pair_height=%d"
              % (top, bot, d, c, content_h, implied_h))


if __name__ == "__main__":
    main()
