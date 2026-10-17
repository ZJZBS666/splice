# -*- coding: utf-8 -*-
"""Diagnose the production stitch algorithm on REAL iPhone screenshots.

Put screenshots in E:\\DeepSeek\\本地电脑\\splice-samples\\
  - one sub-folder per group (samples\\g1\\*.png), or
  - loose files in the root = one single group (sorted by filename)
Then:  python diag_real.py

For every pair it prints the search window, the chosen offset, whether that
offset is truncated at a search bound (a classic cause of "content vanished"),
and the top cost minima so periodic aliases are visible.
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
    if not os.path.isdir(root):
        return []
    groups = []
    for d in sorted(os.listdir(root)):
        p = os.path.join(root, d)
        if os.path.isdir(p):
            files = [f for f in sorted(glob.glob(os.path.join(p, "*")))
                     if f.lower().endswith(EXTS)]
            if files:
                groups.append((d, files))
    loose = [p for p in sorted(glob.glob(os.path.join(root, "*")))
             if os.path.isfile(p) and p.lower().endswith(EXTS)]
    if loose:
        groups.append(("root", loose))
    return groups


def load_rgb(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    return np.asarray(im.convert("RGB"), dtype=np.uint8)


def main():
    groups = find_groups(ROOT)
    if not groups:
        print("NO SAMPLES in " + ROOT)
        print("Export the problem screenshots there first.")
        print("(HEIC is NOT supported - export as PNG or JPG.)")
        return

    for name, files in groups:
        print("=" * 78)
        print("GROUP " + name + "   " + str(len(files)) + " images")
        print("=" * 78)
        rgbs = []
        for p in files:
            a = load_rgb(p)
            rgbs.append(a)
            print("  " + os.path.basename(p) + "   " + str(a.shape[1]) + "x" + str(a.shape[0]))
        if len(rgbs) < 2:
            print("  need >= 2 images, skipped")
            continue

        minw = min(a.shape[1] for a in rgbs)
        rgbs = [a[:, :minw, :] for a in rgbs]
        grays = [S.to_gray(a) for a in rgbs]
        H = grays[0].shape[0]

        top, bottom = S.detect_overlays(grays)
        contentH = H - top - bottom
        min_overlap = max(24, int(S.MIN_OVERLAP_FRAC * H))
        d_hi = H - bottom - min_overlap - top
        min_scroll = max(int(S.MIN_SCROLL_FRAC * contentH), S.FINE_WINDOW)

        print("  H=" + str(H) + "  top=" + str(top) + "  bottom=" + str(bottom) +
              "  contentH=" + str(contentH))
        print("  search window: lo=" + str(min_scroll) + "  hi=" + str(d_hi) +
              "   (min_overlap=" + str(min_overlap) + ")")

        total = 0
        for i in range(len(grays) - 1):
            A, B = grays[i], grays[i + 1]
            d, c = S.find_offset(A, B, top, bottom)
            agree, devs = S.band_votes(A, B, d if d else 0, top, bottom)
            print("  --- pair " + str(i) + "->" + str(i + 1) + " ---")
            print("    chosen d=" + str(d) + "  cost=" + str(round(c, 4)) +
                  "  band_agree=" + str(agree) + "/" + str(S.BAND_COUNT) +
                  "  devs=" + str(devs))

            if d is None:
                print("    !! NO OVERLAP -> hard join with divider")
            else:
                total += d
                if d >= d_hi:
                    print("    !! d is AT the upper bound -> real scroll may be larger,")
                    print("       content between the two shots would be dropped")
                if d <= min_scroll:
                    print("    !! d is AT the lower bound -> real scroll may be smaller")

            # alias scan: full-resolution cost curve, report near-equal minima
            sdA = S._row_sd(A, 1)
            lo = min_scroll
            hi = d_hi
            if hi - lo >= 8:
                curve = S._scan_curve(A, B, top, bottom, lo, hi, sdA, 4, 2)
                if curve:
                    items = sorted(curve.items(), key=lambda kv: kv[1][0])
                    best = items[0][1][0]
                    print("    cost minima (top 6):")
                    for dd, (cc, used) in items[:6]:
                        tag = ""
                        if best > 1e-6 and cc <= best * 1.5:
                            tag = "  <-- near-tie"
                        elif cc <= best + 0.02:
                            tag = "  <-- near-tie"
                        print("      d=" + str(dd) + "  cost=" + str(round(cc, 4)) +
                              "  used=" + str(used) + tag)
                    # spacing between the best and the next well-separated near-tie
                    near = [dd for dd, (cc, _) in items
                            if dd != items[0][0] and (cc <= best * 1.5 or cc <= best + 0.02)]
                    if near:
                        print("    !! ALIASES at " + str(sorted(near)[:8]) +
                              " -> content is periodic; d is ambiguous")
                        print("       gaps from best: " +
                              str([dd - items[0][0] for dd in sorted(near)[:8]]))

        print("  sum of scrolls = " + str(total))
        print("  expected long-image height = " + str((H - bottom) + total))
        print("")

    print("Done. Send me this whole output plus the sample files.")


if __name__ == "__main__":
    main()
