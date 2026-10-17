"""Second-stage diagnosis on the real screenshots.

Two things went wrong in diag_real1.py that must be understood before fixing:

 1. detect_overlays returned top=0 / bottom=0 for most pairs.
    Real screenshots DO have a static status bar and home indicator, so the
    detector is failing. Suspect: the clock text changes between shots and the
    changed-column count exceeds maxChanged = staticChangedFrac * W.
    -> measure static_rows directly.

 2. Some pairs match well (cost 0.23) and one pair does not match at all
    (cost 0.72). That smells like the assumed order is wrong, or the user
    scrolled back and forth.
    -> score ALL 30 ordered pairs so we can rebuild the real capture chain.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S


DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"


def load_gray(path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    return a @ np.array([0.299, 0.587, 0.114], np.float32)


def static_prefix_suffix(A, B):
    """Re-run the same rule as stitcher.static_rows but report the numbers."""
    H, W = A.shape
    max_changed = max(1, int(S.STATIC_CHANGED_FRAC * W))
    changed = (np.abs(A - B) >= S.CHANGE_EPS).sum(axis=1)
    is_static = changed <= max_changed
    print("    maxChanged=%d  rows with changed<=max: %d / %d"
          % (max_changed, int(is_static.sum()), H))
    print("    changed-col count at key rows: "
          "row0=%d row40=%d row80=%d row120=%d row186=%d row400=%d "
          "row2580=%d row2600=%d row2621=%d"
          % (changed[0], changed[40], changed[80], changed[120],
             changed[186], changed[400], changed[2580], changed[2600],
             changed[2621]))
    # where does the static prefix really end (allowing the clock to differ)?
    first_false = 0
    while first_false < H and is_static[first_false]:
        first_false += 1
    last_false = H - 1
    while last_false >= 0 and is_static[last_false]:
        last_false -= 1
    print("    static prefix=%d  static suffix=%d"
          % (first_false, H - 1 - last_false))
    return first_false, H - 1 - last_false


def best_for_pair(A, B, top, bot, lo, hi):
    sdA = S._row_sd(A, S.FINE_COL_STRIDE)
    curve = S._scan_curve(A, B, top, bot, lo, hi, sdA,
                          S.FINE_ROW_STRIDE, S.FINE_COL_STRIDE)
    if not curve:
        return None, 9.9
    kk = min(curve, key=lambda k: curve[k][0])
    return kk, curve[kk][0]


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    names = [os.path.basename(p)[:8] for p in files]
    grays = [load_gray(p) for p in files]
    H, W = grays[0].shape
    print("count=%d size=%dx%d" % (len(grays), W, H))
    print("")
    print("=== static-row analysis (consecutive pairs) ===")
    for i in range(len(grays) - 1):
        print("pair %s -> %s" % (names[i], names[i + 1]))
        static_prefix_suffix(grays[i], grays[i + 1])
        print("")

    print("=== all ordered pairs, best coarse match ===")
    print("      " + "".join("%-10s" % n for n in names))
    M = {}
    for i in range(len(grays)):
        row = "%-6s" % names[i]
        for j in range(len(grays)):
            if i == j:
                row += "%-10s" % "-"
                continue
            A, B = grays[i], grays[j]
            lo = max(int(S.MIN_SCROLL_FRAC * H), S.FINE_WINDOW)
            hi = H - max(24, int(S.MIN_OVERLAP_FRAC * H))
            d, c = best_for_pair(A, B, 0, 0, lo, hi)
            M[(i, j)] = (d, c)
            row += "%-10s" % ("%.3f" % c)
        print(row)
    print("")
    print("=== best d for each ordered pair (cost < 0.45 only) ===")
    for (i, j), (d, c) in sorted(M.items(), key=lambda kv: kv[1][1]):
        if c < 0.45:
            print("  %s -> %s  d=%-5s cost=%.4f" % (names[i], names[j],
                                                    str(d), c))


if __name__ == "__main__":
    main()
