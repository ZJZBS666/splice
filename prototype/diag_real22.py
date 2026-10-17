"""Why did the device fail pair 1->2?

Python passes it with agree=3/4 or 4/4 depending on the overlay heights it
was given. The device measures overlays PER PAIR, so each pair may be scored
with different (top,bottom). Sweep every plausible overlay combo for each
pair and report the band vote + the gates. If some combos drop below
MIN_BAND_AGREE the gate is too fragile and must be hardened.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S

DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"


def load_gray(path):
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.uint8)
    return S.to_gray(rgb)


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    gs = [load_gray(p) for p in files]
    combos = [(0, 0), (0, 17), (0, 34), (0, 71), (0, 130), (0, 270), (0, 286),
              (318, 0), (318, 17), (318, 34), (318, 130), (318, 270), (318, 286),
              (317, 24)]
    for i in range(len(gs) - 1):
        print("=== pair %d ===" % i)
        for (top, bot) in combos:
            d, c = S.find_offset(gs[i], gs[i + 1], top, bot)
            if d is None:
                print("  top=%-4d bot=%-4d -> None (cost=%.4f)" % (top, bot, c))
                continue
            agree, devs = S.band_votes(gs[i], gs[i + 1], d, top, bot)
            flag = "PASS" if agree >= S.MIN_BAND_AGREE else "FAIL"
            print("  top=%-4d bot=%-4d d=%-5d cost=%.4f agree=%d/%d devs=%s %s"
                  % (top, bot, d, c, agree, S.BAND_COUNT, devs, flag))
        print("")


if __name__ == "__main__":
    main()
