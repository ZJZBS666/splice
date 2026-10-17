"""Find the TRUE bottom overlay height in the real screenshots.

The static-row test fails because in dark mode the WeChat input bar is
TRANSLUCENT: content shows through, so the bar's pixels change between
screenshots and it is never marked "static". Result: bottom is underestimated
(225/246 instead of ~286), the leftover rows of the bar get baked into the
middle of the long image.

This script measures, for the bottom region of each consecutive pair, how
similar the rows are. A translucent bar is NOT identical, but it is far more
similar than scrolling content, because the bar itself (blurred backdrop,
placeholder text, icons) dominates.

Prints per-row "similarity" for rows H-420..H-1, and the estimated bar top.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

SRC = r"E:\DeepSeek\本地电脑\splice\samples\1"
H = 2622
W = 1206


def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32)


def main():
    files = sorted(glob.glob(os.path.join(SRC, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    imgs = [load(p) for p in files]

    for i in range(len(imgs) - 1):
        A, B = imgs[i], imgs[i + 1]
        print("=== pair %d (%s -> %s)"
              % (i, os.path.basename(files[i])[:8],
                 os.path.basename(files[i + 1])[:8]))
        # per-row mean abs diff at the SAME screen position
        diff_same = np.abs(B - A).mean(axis=(1, 2))
        # a scrolling row differs a lot; a translucent bar differs little
        print("   y      diff_same   mean_lum_B")
        for y in range(H - 420, H, 20):
            print("   %-6d %8.2f   %7.1f"
                  % (y, diff_same[y], B[y].mean()))
        # estimate bar top: first row from bottom-up where diff_same stays low
        thr = 6.0
        y = H - 1
        while y > H - 600 and diff_same[y] < thr:
            y -= 1
        print("   contiguous low-diff suffix starts at y=%d -> bottom=%d"
              % (y + 1, H - (y + 1)))
        # also with a looser threshold
        for t in (3.0, 6.0, 10.0, 16.0):
            y = H - 1
            while y > H - 600 and diff_same[y] < t:
                y -= 1
            print("      thr=%-5.1f -> bottom=%d" % (t, H - (y + 1)))
        print("")


if __name__ == "__main__":
    main()
