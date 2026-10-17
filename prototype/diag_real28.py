"""Establish GROUND TRUTH for the bottom overlay: crop the bottom of every
screenshot and lay them side by side so the bar boundary is visible.

Also print, for every row in the bottom 500, the per-pair diff and the MEDIAN
across pairs. The bar should show a sharp drop in median diff at its top edge.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image, ImageDraw

SRC = r"E:\DeepSeek\本地电脑\splice\samples\1"
H = 2622
BAND = 500          # rows from H-BAND to H
TW = 200            # thumb width


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def main():
    files = sorted(glob.glob(os.path.join(SRC, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    grays = [load_gray(p) for p in files]
    n = len(files)

    # ---- visual: bottom band of each image
    th = int(BAND * TW / 1206)
    gap = 8
    canvas = Image.new("RGB", (n * (TW + gap), th + 20), (255, 255, 255))
    dr = ImageDraw.Draw(canvas)
    for i, p in enumerate(files):
        im = Image.open(p).convert("RGB").crop((0, H - BAND, 1206, H))
        im = im.resize((TW, th), Image.LANCZOS)
        canvas.paste(im, (i * (TW + gap), 20))
        dr.text((i * (TW + gap) + 2, 4), "%d:%s" % (i, os.path.basename(p)[:6]),
                fill=(0, 0, 0))
        dr.line([(i * (TW + gap), 20), (i * (TW + gap), th + 20)],
                fill=(255, 0, 0))
    out = os.path.join(SRC, "_bottom6.png")
    canvas.save(out)
    print("wrote %s %s" % (out, canvas.size))

    # ---- median diff profile
    print("")
    print("y      " + "  ".join("p%d" % i for i in range(n - 1)) + "   median")
    for y in range(H - BAND, H, 10):
        vals = [float(np.abs(grays[i][y] - grays[i + 1][y]).mean())
                for i in range(n - 1)]
        med = float(np.median(vals))
        print("%-6d " % y + "  ".join("%5.1f" % v for v in vals)
              + "   %6.2f" % med)


if __name__ == "__main__":
    main()
