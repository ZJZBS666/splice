"""Is the overlay detection failure caused by JPEG noise, or is it real?

The 6 samples in samples/1 are JPEG re-encodes (136-170KB for 1206x2622),
so pixel-exact comparisons are polluted by +-2..+-8 compression noise.
The device loads the original PNGs, so this test tells us whether
`static_rows` would actually work on device.

For every pair and a range of CHANGE_EPS, print the static prefix/suffix.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"
W = 1206
H = 2622
FRACS = (0.05, 0.10, 0.20)
EPSS = (2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0)


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32) @ \
        np.array([0.299, 0.587, 0.114], np.float32)


def prefixes(st):
    n = st.shape[0]
    top = 0
    while top < n and st[top]:
        top += 1
    bot = 0
    while bot < n and st[n - 1 - bot]:
        bot += 1
    return top, bot


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    names = [os.path.basename(p)[:8] for p in files]
    grays = [load_gray(p) for p in files]

    for i in range(len(grays) - 1):
        A, B = grays[i], grays[i + 1]
        print("=== %s -> %s" % (names[i], names[i + 1]))
        d = np.abs(A - B)
        for eps in EPSS:
            ch = (d >= eps).sum(axis=1)
            line = "  eps=%5.1f " % eps
            for frac in FRACS:
                maxc = max(1, int(frac * W))
                t, b = prefixes(ch <= maxc)
                line += " | f=%.2f top=%4d bot=%4d" % (frac, t, b)
            print(line)
        # row profile of changed counts at eps=16 for reference
        ch16 = (d >= 16.0).sum(axis=1)
        print("  changed@eps16 per 100 rows (mean):")
        vals = []
        for b0 in range(0, H, 100):
            vals.append("%4d:%4d" % (b0, int(ch16[b0:b0 + 100].mean())))
        for k in range(0, len(vals), 6):
            print("    " + "  ".join(vals[k:k + 6]))
        print("")


if __name__ == "__main__":
    main()
