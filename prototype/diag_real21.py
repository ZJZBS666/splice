"""Identify EXACTLY which two source shots and which d produced each output.

For an output long image of height h, assuming
    out = A[0:content_h] ++ B[content_h-d:content_h]
with content_h = H - bottom, we can solve d = h - content_h and then verify
both halves against every candidate source pair.

This pins down what the device actually did, instead of guessing.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

SRC = r"E:\DeepSeek\本地电脑\splice\samples\1"
OUT = r"E:\DeepSeek\本地电脑\splice\samples"
H = 2622


def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.int16)


def agree(a, b, tol=16):
    """Fraction of pixels that match within tol."""
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    return float((d.max(axis=2) <= tol).mean())


def main():
    srcs = sorted(glob.glob(os.path.join(SRC, "*.jpg")),
                  key=lambda p: os.path.getmtime(p))
    names = [os.path.basename(p)[:8] for p in srcs]
    imgs = [load(p) for p in srcs]

    outs = sorted(glob.glob(os.path.join(OUT, "*.jpg")))
    for op in outs:
        o = load(op)
        h, w = o.shape[0], o.shape[1]
        print("=== %s  %dx%d ===" % (os.path.basename(op)[:8], w, h))
        for bottom in (0, 34, 286, 270, 214):
            ch = H - bottom
            d = h - ch
            if d <= 0 or d >= ch:
                continue
            # candidate A: first ch rows of out should equal A[0:ch]
            top_half = o[0:ch]
            bot_half = o[ch:h]
            best_a, best_a_s = None, 0.0
            for i, a in enumerate(imgs):
                if a.shape[0] != ch and a.shape[0] < ch:
                    continue
                s = agree(top_half, a[0:ch])
                if s > best_a_s:
                    best_a_s, best_a = s, names[i]
            best_b, best_b_s = None, 0.0
            for i, b in enumerate(imgs):
                src = b[ch - d:ch]
                if src.shape[0] != bot_half.shape[0]:
                    continue
                s = agree(bot_half, src)
                if s > best_b_s:
                    best_b_s, best_b = s, names[i]
            print("  bottom=%3d d=%-5d  A=%s(%.3f)  B=%s(%.3f)"
                  % (bottom, d, best_a, best_a_s, best_b, best_b_s))
        print("")


if __name__ == "__main__":
    main()
