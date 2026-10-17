# -*- coding: utf-8 -*-
"""Run the production stitch algorithm on REAL iPhone screenshots.

Usage:
  1. Put screenshots into E:\\DeepSeek\\本地电脑\\splice-samples\\
     - one sub-folder per group (e.g. samples\\group1\\*.png), OR
     - dump them all in the root (then all files = one group, sorted by name)
  2. python run_real.py

Prints, per group: top/bottom overlay, every pair's scroll offset + cost +
band votes, and the resulting long image height. Writes out_real_<g>.png so
you can eyeball the seam.
"""
import os
import sys
import glob
import numpy as np
from PIL import Image

import stitcher as S

ROOT = r"E:\DeepSeek\本地电脑\splice-samples"
EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")


def find_groups(root):
    """Return [(name, [paths...]), ...]. Sub-folders are separate groups."""
    if not os.path.isdir(root):
        return []
    subs = [d for d in sorted(os.listdir(root))
            if os.path.isdir(os.path.join(root, d))]
    groups = []
    if subs:
        for d in subs:
            files = []
            for p in sorted(glob.glob(os.path.join(root, d, "*"))):
                if p.lower().endswith(EXTS):
                    files.append(p)
            if files:
                groups.append((d, files))
        # also pick up loose files in the root
        loose = [p for p in sorted(glob.glob(os.path.join(root, "*")))
                 if os.path.isfile(p) and p.lower().endswith(EXTS)]
        if loose:
            groups.append(("root", loose))
    else:
        files = [p for p in sorted(glob.glob(os.path.join(root, "*")))
                 if os.path.isfile(p) and p.lower().endswith(EXTS)]
        if files:
            groups.append(("root", files))
    return groups


def load_rgb(path):
    im = Image.open(path).convert("RGB")
    return np.asarray(im, dtype=np.uint8)


def main():
    groups = find_groups(ROOT)
    if not groups:
        print("NO SAMPLES FOUND in " + ROOT)
        print("Put your screenshots there first (one sub-folder per group).")
        return

    for name, files in groups:
        print("=" * 72)
        print("GROUP " + name + "  (" + str(len(files)) + " images)")
        print("=" * 72)
        rgbs = []
        for p in files:
            a = load_rgb(p)
            rgbs.append(a)
            print("  " + os.path.basename(p) + "  " + str(a.shape[1]) + "x" + str(a.shape[0]))

        # width must agree; crop to the narrowest like the app does
        minw = min(a.shape[1] for a in rgbs)
        rgbs = [a[:, :minw, :] for a in rgbs]
        grays = [S.to_gray(a) for a in rgbs]
        H = grays[0].height

        top, bottom = S.detect_overlays(grays)
        print("  overlay: top=" + str(top) + "  bottom=" + str(bottom) +
              "   contentH=" + str(H - top - bottom) + "  (H=" + str(H) + ")")

        offsets = []
        total_extra = 0
        for i in range(len(grays) - 1):
            d, c = S.find_offset(grays[i], grays[i + 1], top, bottom)
            agree, devs = S.band_votes(grays[i], grays[i + 1], d if d else 0, top, bottom)
            print("  pair " + str(i) + "->" + str(i + 1) +
                  ": d=" + str(d) + "  cost=" + str(round(c, 4)) +
                  "  band_agree=" + str(agree) + "/" + str(S.BAND_COUNT) +
                  "  devs=" + str(devs))
            offsets.append(d)
            if d:
                total_extra += d

        if any(d is None for d in offsets):
            print("  >>> some pair has NO overlap -> will be hard-joined with a divider")
        exp_h = (H - bottom) + total_extra
        print("  expected long image height = " + str(exp_h))
        print("  (top kept once = " + str(top) + ", contentH = " + str(H - top - bottom) +
              ", sum of scrolls = " + str(total_extra) + ")")

        # render it so we can look at the seams
        try:
            res = S.stitch_group(rgbs)
            img = res["image"] if isinstance(res, dict) else res
            outp = os.path.join(ROOT, "out_real_" + name + ".png")
            Image.fromarray(img).save(outp)
            print("  wrote " + outp + "  " + str(img.shape[1]) + "x" + str(img.shape[0]))
        except Exception as e:
            print("  render skipped: " + repr(e))
        print("")


if __name__ == "__main__":
    main()
