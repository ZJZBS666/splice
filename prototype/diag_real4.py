"""Visual sanity check on the real screenshots.

Produces:
  _row6.png   all six screenshots side by side (downscaled), so the reading
              order and the content can be eyeballed at a glance
  _ovl_<i>.png  for every consecutive pair: the bottom part of shot i pasted
              above the top part of shot i+1 using the chosen d, so a correct
              d shows continuous content and a wrong d shows a visible jump

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


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    names = [os.path.basename(p)[:8] for p in files]
    imgs = [Image.open(p).convert("RGB") for p in files]
    H, W = imgs[0].size[1], imgs[0].size[0]
    print("count=%d size=%dx%d" % (len(imgs), W, H))

    # ---- row of six -------------------------------------------------------
    tw = 180
    th = int(H * tw / W)
    gap = 6
    sheet = Image.new("RGB", (len(imgs) * tw + (len(imgs) - 1) * gap, th),
                      (255, 0, 0))
    for i, im in enumerate(imgs):
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (i * (tw + gap), 0))
    out = os.path.join(DIR, "_row6.png")
    sheet.save(out)
    print("wrote %s (%dx%d)" % (out, sheet.width, sheet.height))

    # ---- overlap visualisation per consecutive pair ----------------------
    grays = [load_gray(p) for p in files]
    for i in range(len(imgs) - 1):
        A, B = grays[i], grays[i + 1]
        d, c = S.find_offset(A, B, 0, 0)
        print("pair %d -> %d  d=%s cost=%.4f" % (i, i + 1, str(d), c))
        if d is None:
            continue
        # region of A that is NOT in B (the new bottom band of A) then the
        # shared region, then B's new content
        band = 700
        # take A's rows [H-d-band, H-d] (shared) plus B's last d rows
        y0 = max(0, H - d - band)
        partA = imgs[i].crop((0, y0, W, H))
        partB = imgs[i + 1].crop((0, H - d, W, H))
        comb = Image.new("RGB", (W, partA.height + partB.height + 6),
                         (255, 0, 0))
        comb.paste(partA, (0, 0))
        comb.paste(partB, (0, partA.height + 6))
        comb = comb.resize((W // 2, comb.height // 2), Image.LANCZOS)
        p = os.path.join(DIR, "_ovl_%d_%d.png" % (i, i + 1))
        comb.save(p)
        print("  wrote %s (%dx%d)  [red band = where A ends / B continues]"
              % (p, comb.width, comb.height))


if __name__ == "__main__":
    main()
