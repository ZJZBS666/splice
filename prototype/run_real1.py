"""Run the REAL pipeline on the real screenshots and see what it produces.

Goal: reproduce "3384 / 3445 / 3485" from the device, then confirm the two
root causes found by diag_real1/2:

  A. detect_overlays returns (0, 0) on real screenshots.
     Evidence: changed-column counts at the status bar rows are 700-1200 out of
     1206, far above maxChanged = 0.10 * 1206 = 120.
     Why: the status bar clock changes AND the dark-mode status bar sits on top
     of scrolling content, so nearly every column differs.

  B. The per-pair match is decent (cost 0.24-0.37) but the overlay guess being
     (0,0) means the whole screenshot is treated as scrollable content, so the
     first screenshot contributes contentH = H instead of H - top - bottom and
     the stitch geometry is wrong.

Print the produced heights so they can be compared with the device output.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S


DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"


def load_rgb(path):
    im = Image.open(path).convert("RGB")
    return np.asarray(im).astype(np.uint8)


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    names = [os.path.basename(p)[:8] for p in files]
    rgbs = [load_rgb(p) for p in files]
    H, W = rgbs[0].shape[:2]

    print("running S.stitch_all on %d real screenshots (no timestamps)"
          % len(rgbs))
    results, diag_all = S.stitch_all(rgbs, timestamps=None, verbose=True,
                                     keep_first_chrome=True)
    print("groups=%s breaks=%s reasons=%s too_tall=%s total_h=%d"
          % (diag_all["groups"], diag_all["breaks"],
             diag_all["reasons"], diag_all["too_tall"], diag_all["height"]))
    for gi, (img, diag) in enumerate(results):
        print("  group %d: height=%d  (H-34=%d, sum d=%s)"
              % (gi, diag["height"], H - 34,
                 sum(dd for dd in diag["d_list"] if dd is not None)))
        print("     deltas=%s" % (diag["d_list"],))
        print("     top=%s bottom=%s content_h=%s"
              % (diag["top"], diag["bottom"], diag["content_h"]))
        print("     pairs=%s" % (diag["pairs"],))
        Image.fromarray(img).save(
            os.path.join(DIR, "_out_group%d.png" % gi))

    print("")
    print("=== forced single group (bypass grouping) ===")
    img, diag = S.stitch_group(rgbs, verbose=True, keep_first_chrome=True)
    print("  height=%d" % diag["height"])
    print("  deltas=%s" % (diag["d_list"],))
    print("  top=%s bottom=%s" % (diag["top"], diag["bottom"]))
    Image.fromarray(img).save(os.path.join(DIR, "_out_forced.png"))


if __name__ == "__main__":
    main()
