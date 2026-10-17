"""Identify the 6 real screenshots and measure each one's bottom bar top.

Two questions:
  1) What is the actual visual order/content of the 6 files? (mtime order may
     not equal the order the user swiped.)
  2) Where does each image's bottom UI bar start?

Method for (2), app-agnostic:
  The bar is a translucent fixed overlay. Its rows barely change between two
  scrolled screenshots, while content rows change a lot. But blank background
  is ALSO unchanged, so motion alone over-extends. Extra condition: the bar
  has STRUCTURE (placeholder text, icons), so we walk down from the top of the
  unchanged suffix to the first row with real horizontal structure.

Prints a labelled strip and per-image bar tops.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

SRC = r"E:\DeepSeek\本地电脑\splice\samples\1"
H = 2622


def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32)


def smooth(a, w=21):
    k = np.ones(w, dtype=np.float32) / w
    return np.convolve(a, k, mode="same")


def unchanged_suffix(A, B, thr):
    d = smooth(np.abs(B - A).mean(axis=(1, 2)))
    y = H - 1
    while y > 0 and d[y] < thr:
        y -= 1
    return y + 1, d


def first_structured_row(gray, y0, std_min=3.0):
    for y in range(y0, H):
        if gray[y, 40:H - 40].std() >= std_min:
            return y
    return H


def main():
    files = sorted(glob.glob(os.path.join(SRC, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    imgs = [load(p) for p in files]
    grays = [im.mean(axis=2) for im in imgs]

    # ---- labelled strip (downscaled)
    tw = 150
    th = int(H * tw / 1206)
    gap = 10
    canvas = Image.new("RGB", (len(files) * (tw + gap), th + 22), (255, 255, 255))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(canvas)
    for i, p in enumerate(files):
        im = Image.open(p).convert("RGB").resize((tw, th), Image.LANCZOS)
        canvas.paste(im, (i * (tw + gap), 22))
        dr.text((i * (tw + gap) + 3, 4), "%d:%s" % (i, os.path.basename(p)[:6]),
                fill=(0, 0, 0))
    out = os.path.join(SRC, "_order6.png")
    canvas.save(out)
    print("wrote %s %s" % (out, canvas.size))

    # ---- bar tops
    for i in range(len(imgs) - 1):
        A, B = imgs[i], imgs[i + 1]
        ys, d = unchanged_suffix(A, B, 6.0)
        top_of_blank = ys
        bar = first_structured_row(grays[i + 1], top_of_blank)
        print("pair %d -> %d : unchanged suffix starts y=%d ; first structured row y=%d"
              % (i, i + 1, top_of_blank, bar))
        print("     => bottom (structured) = %d ; bottom (suffix) = %d"
              % (H - bar, H - top_of_blank))

    # ---- single-image bottom structure profile (no pair needed)
    print("")
    print("per-image last structured row below y=2200:")
    for i, g in enumerate(grays):
        rows = [y for y in range(2200, H) if g[y, 40:H - 40].std() >= 3.0]
        print("  img%d %s  last_structured=%s"
              % (i, os.path.basename(files[i])[:8],
                 (max(rows) if rows else None)))


if __name__ == "__main__":
    main()
