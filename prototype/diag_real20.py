"""Single-group test: put ALL shots into one long image, hard-stitching
(with a divider) wherever the offset cannot be found.

Rationale: the user's own spec (m00001 follow-ups) says non-overlapping or
missing-screen shots should be hard-stitched with a thin divider, NOT split
into separate long images. The current grouping code does the opposite, so a
failed match chops the run into several short long images -> "screenshot
incomplete".

This script compares:
  A) current grouping (break on no-match)
  B) single group, hard-stitch on no-match
under several (top,bottom) so we can see how much content each keeps.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"
OUT = os.path.join(DIR, "_single.png")


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.uint8)


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    rgbs = [load_rgb(p) for p in files]
    gs = [S.to_gray(r) for r in rgbs]
    H = gs[0].shape[0]

    for eps in (2.0, 12.0):
        S.CHANGE_EPS = eps
        top, bot = S.detect_overlays(gs)
        ds = []
        for i in range(len(gs) - 1):
            d, c = S.find_offset(gs[i], gs[i + 1], top, bot)
            ds.append((d, c))
        n_gap = sum(1 for d, _ in ds if d is None)
        content_h = H - top - bot
        h_single = content_h + sum((d if d is not None else content_h + S.DIVIDER_HEIGHT)
                                   for d, _ in ds)
        print("CHANGE_EPS=%.1f top=%d bot=%d" % (eps, top, bot))
        print("  per-pair d/cost: %s" % [(d, round(c, 4)) for d, c in ds])
        print("  gaps=%d  single-group height=%d  (H=%d)" % (n_gap, h_single, H))
        print("")

    # Render the single-group version with the most plausible overlays.
    S.CHANGE_EPS = 12.0
    top, bot = S.detect_overlays(gs)
    print("rendering single group with top=%d bot=%d" % (top, bot))
    ds = []
    for i in range(len(gs) - 1):
        d, c = S.find_offset(gs[i], gs[i + 1], top, bot)
        ds.append(d)
    cropped = [rgbs[i][0 if i == 0 else top:H - bot] for i in range(len(rgbs))]
    out = S.assemble(cropped, ds, first_kept_chrome=(top > 0), first_top=top)
    Image.fromarray(out).save(OUT)
    print("wrote %s %s" % (OUT, out.shape))


if __name__ == "__main__":
    main()
