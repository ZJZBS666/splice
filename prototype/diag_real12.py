"""Verify the exact hypothesis: output = A[0:H-b] + B[H-b-d:H-b]  (b=34).

For each output image, search all (original A, original B, d) combinations that
could explain it, reconstruct the expected long image with the SAME formula the
app uses, and report the pixel agreement. If one hypothesis reaches ~1.0 the
device stitched correctly and the short height simply means the group had only
two screenshots.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

SAMP = r"E:\DeepSeek\本地电脑\splice\samples"
ORIG = os.path.join(SAMP, "1")
BOT = 34
TOL = 20.0


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32)


def load_gray(path):
    return load_rgb(path) @ np.array([0.299, 0.587, 0.114], np.float32)


def score(O, A, B, d, bot=BOT):
    """Build A[0:H-bot] + B[H-bot-d:H-bot] and compare to O."""
    H = A.shape[0]
    first = A[0:H - bot]
    second = B[H - bot - d:H - bot] if d > 0 else B[0:0]
    exp = np.concatenate([first, second], axis=0)
    if exp.shape[0] != O.shape[0]:
        # allow the app to have produced a slightly different height: compare
        # the overlapping part only, and report the height mismatch
        n = min(exp.shape[0], O.shape[0])
        diff = np.abs(exp[:n] - O[:n])
        sc = float((diff.max(axis=2) <= TOL).mean())
        return sc, exp.shape[0], O.shape[0]
    diff = np.abs(exp - O)
    return float((diff.max(axis=2) <= TOL).mean()), exp.shape[0], O.shape[0]


def main():
    outs = sorted(glob.glob(os.path.join(SAMP, "*.jpg")))
    origs = sorted(glob.glob(os.path.join(ORIG, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    onames = [os.path.basename(p)[:8] for p in origs]
    As = [load_rgb(p) for p in origs]
    Gs = [load_gray(p) for p in origs]
    H = As[0].shape[0]

    for p in outs:
        O = load_rgb(p)
        print("=== %s  %dx%d" % (os.path.basename(p), O.shape[1], O.shape[0]))
        print("    implied d from height (if 2 shots, keepChrome): %d"
              % (O.shape[0] - (H - BOT)))
        best = []
        for ia in range(len(As)):
            for ib in range(len(As)):
                if ia == ib:
                    continue
                # derive d from the output height instead of searching blindly
                d = O.shape[0] - (H - BOT)
                if 60 <= d <= H - BOT - 60:
                    sc, eh, oh = score(O, As[ia], As[ib], d)
                    best.append((sc, ia, ib, d, eh, oh))
        best.sort(key=lambda t: -t[0])
        for sc, ia, ib, d, eh, oh in best[:4]:
            print("    %s + %s  d=%-5d  agree=%.4f  (built %d vs out %d)"
                  % (onames[ia], onames[ib], d, sc, eh, oh))
        print("")


if __name__ == "__main__":
    main()
