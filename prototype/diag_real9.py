"""Count the repeated bottom input bar in each App output image.

The WeChat bottom bar (voice icon / rounded text field / emoji / plus) is a
highly distinctive fixed overlay. In a correct stitch it must appear exactly
ONCE. Every extra occurrence marks a segment boundary, so its position also
reveals how many screenshots were stitched and where each segment ended.

Detection: the text field is a mid-grey rounded rect spanning a wide x-range at
a specific height. Scan every row for a long run of pixels in a narrow grey band
and require the pattern to repeat across several consecutive rows.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

SAMP = r"E:\DeepSeek\本地电脑\splice\samples"


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.int16)


def bar_rows(img, lo=52, hi=76, min_frac=0.30, x0=200, x1=760):
    """Rows where a wide band of pixels falls in the grey range."""
    g = img.mean(axis=2)
    seg = g[:, x0:x1]
    inband = (seg >= lo) & (seg <= hi)
    frac = inband.mean(axis=1)
    return frac >= min_frac


def runs(mask, min_len=40):
    out = []
    s = None
    for k, v in enumerate(mask):
        if v and s is None:
            s = k
        elif not v and s is not None:
            if k - s >= min_len:
                out.append((s, k - 1))
            s = None
    if s is not None and len(mask) - s >= min_len:
        out.append((s, len(mask) - 1))
    return out


def main():
    outs = sorted(glob.glob(os.path.join(SAMP, "*.jpg")))
    for p in outs:
        img = load_rgb(p)
        H = img.shape[0]
        print("=== %s  %dx%d" % (os.path.basename(p), img.shape[1], H))
        m = bar_rows(img)
        r = runs(m, min_len=40)
        print("    text-field-like row runs (len>=40): %s" % (r,))
        # the input bar's rounded field is ~90px tall; report candidates
        print("    candidates (height 60..140): %s"
              % ([x for x in r if 60 <= x[1] - x[0] <= 140],))
        print("")

    # reference: the same detector on a single original screenshot
    orig = os.path.join(SAMP, "1")
    for p in sorted(glob.glob(os.path.join(orig, "*.jpg")),
                    key=lambda q: os.path.getmtime(q)):
        img = load_rgb(p)
        m = bar_rows(img)
        r = runs(m, min_len=40)
        print("original %s %dx%d  runs=%s"
              % (os.path.basename(p)[:8], img.shape[1], img.shape[0], r))


if __name__ == "__main__":
    main()
