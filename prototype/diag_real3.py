"""Ground-truth check on the real screenshots.

Question 1: is the chosen d (1048 / 1341 / 1109 / 778) actually CORRECT?
  The normalized-L1 cost is 0.24-0.37, which is far from the 0.0000 that exact
  synthetic matches produce. JPEG noise alone should not cost 0.37. So either
  the offset is wrong, or there is something else going on.

Method: for every d in a wide range compute
    frac = fraction of rows (over the comparable region) whose MAX abs pixel
           difference is below TOL (default 8, JPEG-friendly)
A correct offset must produce a high frac and a sharp peak.

Question 2: does a static top/bottom overlay really exist?
  If the nav bar is translucent, content scrolls behind it and there is NO
  static overlay. Then top=0/bottom=0 is CORRECT and the whole screenshot is
  scrollable content.
  Method: print the max abs diff per row band for a pair at the chosen d.

Also dumps a top-strip contact sheet so the nav bar can be eyeballed.

ASCII-only prints.
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"
TOL = 8.0


def load_gray(path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    return a @ np.array([0.299, 0.587, 0.114], np.float32)


def frac_at(A, B, d, top=0, bottom=0, tol=TOL, col_stride=1):
    H, W = A.shape
    y0 = top
    y1 = min(H - bottom - d, H - bottom)
    if y1 - y0 < 40:
        return None, 0
    ys = np.arange(y0, y1, 2)
    a = A[ys + d][:, ::col_stride]
    b = B[ys][:, ::col_stride]
    err = np.abs(a - b).max(axis=1)
    return float((err < tol).mean()), int(len(ys))


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    names = [os.path.basename(p)[:8] for p in files]
    grays = [load_gray(p) for p in files]
    H, W = grays[0].shape
    print("count=%d size=%dx%d" % (len(grays), W, H))
    print("")

    # ---- Question 1: scan frac for the first three pairs -------------------
    print("=== exact-match fraction scan (tol=%.0f) ===" % TOL)
    for i in range(len(grays) - 1):
        A, B = grays[i], grays[i + 1]
        lo = max(int(S.MIN_SCROLL_FRAC * H), 20)
        hi = H - max(24, int(S.MIN_OVERLAP_FRAC * H))
        res = []
        for d in range(lo, hi + 1, 4):
            f, n = frac_at(A, B, d)
            if f is not None:
                res.append((d, f, n))
        res.sort(key=lambda t: -t[1])
        print("pair %s -> %s  (scan %d..%d step4)"
              % (names[i], names[i + 1], lo, hi))
        for d, f, n in res[:6]:
            print("    d=%-5d frac=%.4f rows=%d" % (d, f, n))
        # refine around the best
        bd = res[0][0]
        fine = []
        for d in range(max(lo, bd - 8), min(hi, bd + 8) + 1):
            f, n = frac_at(A, B, d)
            if f is not None:
                fine.append((d, f, n))
        fine.sort(key=lambda t: -t[1])
        print("    refined best:")
        for d, f, n in fine[:4]:
            print("      d=%-5d frac=%.4f rows=%d" % (d, f, n))
        bd2 = fine[0][0]
        print("    -> best d=%d frac=%.4f" % (bd2, fine[0][1]))
        print("")

        # ---- Question 2: per-band diff profile at the best d --------------
        if i < 2:
            print("    per-band max|diff| at d=%d (16 bands over 0..H):" % bd2)
            y1 = H - bd2
            for bi in range(16):
                yy0 = int(bi * y1 / 16)
                yy1 = int((bi + 1) * y1 / 16)
                if yy1 - yy0 < 2:
                    continue
                seg = np.abs(A[yy0 + bd2:yy1 + bd2] - B[yy0:yy1])
                print("      y=%4d..%4d  meanAbs=%.2f  maxAbs=%.0f  "
                      "frac<8=%.3f"
                      % (yy0, yy1, seg.mean(), seg.max(),
                         float((seg.max(axis=2) < TOL).mean())))
            print("")

    # ---- contact sheet of the top 300 rows of every screenshot ------------
    print("writing top-strip contact sheet ...")
    strips = []
    for p in files:
        im = Image.open(p).convert("RGB")
        strips.append(im.crop((0, 0, W, 300)))
    sheet = Image.new("RGB", (W, 300 * len(strips) + 8 * (len(strips) - 1)),
                      (255, 0, 0))
    y = 0
    for s in strips:
        sheet.paste(s, (0, y))
        y += 300 + 8
    sheet = sheet.resize((W // 2, sheet.height // 2), Image.LANCZOS)
    out = os.path.join(DIR, "_topsheet.png")
    sheet.save(out)
    print("wrote %s (%dx%d)" % (out, sheet.width, sheet.height))


if __name__ == "__main__":
    main()
