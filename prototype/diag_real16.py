"""Reproduce the device's short long-images by feeding gapped timestamps.

Device output heights were 3384 / 3445 / 3485 for 1206-wide long images.
Solve h = (H - bottom) + d  for bottom = 286:
    d = 3384 - (2622-286) = 1048   <- exactly pair 0->1
    d = 3445 - 2336       = 1109   <- exactly pair 2->3
    d = 3485 - 2336       = 1149

So the device split 6 shots into THREE groups of two. The d values it
computed are correct; the grouping is what broke.

This script proves the grouping rule: when consecutive timestamps are more
than GROUP_TIME_GAP (90s) apart, stitch_all breaks the group even though
find_offset would happily match.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.uint8)


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    rgbs = [load_rgb(p) for p in files]
    n = len(rgbs)

    # force sane overlays so JPEG noise does not confound the grouping test
    orig = S.detect_overlays
    S.detect_overlays = lambda g: (318, 286)

    cases = {
        "all same time (gap 0)": [1000.0 + i for i in range(n)],
        "gap 60s  (<90)": [1000.0 + 60 * i for i in range(n)],
        "gap 100s (>90)": [1000.0 + 100 * i for i in range(n)],
        "gap 240s (>90)": [1000.0 + 240 * i for i in range(n)],
    }
    for name, ts in cases.items():
        res, da = S.stitch_all(rgbs, timestamps=ts, verbose=False,
                               keep_first_chrome=True)
        hs = [r[1]["height"] for r in res]
        dl = [[p["d"] for p in r[1]["pairs"]] for r in res]
        print("%-22s groups=%-18s heights=%-14s d=%s"
              % (name, str(da["groups"]), str(hs), dl))
        if len(hs) == 3:
            print("    *** reproduces device: 3 long images ***")

    S.detect_overlays = orig

    print("")
    print("--- device height back-solve (bottom=286) ---")
    for h in (3384, 3445, 3485):
        print("  h=%d -> d=%d" % (h, h - (2622 - 286)))


if __name__ == "__main__":
    main()
