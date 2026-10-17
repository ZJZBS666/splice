"""Recover the EXACT seam row and offset d the device used.

No assumptions. For an output long image of height h built from images
A (first) and B (second) by Splice's assemble():

    parts[0] = A[0 : k]            (k = content height kept from A)
    parts[1] = B[k - d : ]         (d = scroll amount)
    h = k + d

So for a candidate seam row k: d = h - k, and the tail must equal
B[k-d : k-d+d] = B[2k-h : 2k-h+d].

We scan k over a wide range, score the tail against every source image,
and report the best (source, k, d). That recovers what the device
ACTUALLY did, independent of any overlay guess.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

OUT_DIR = r"E:\DeepSeek\本地电脑\splice\samples"
SRC_DIR = r"E:\DeepSeek\本地电脑\splice\samples\1"


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.int16)


def best_tail_match(out, k, srcs):
    """Given seam row k, find which source the tail matches best."""
    h = out.shape[0]
    d = h - k
    if d <= 20:
        return None
    off = 2 * k - h
    if off < 0:
        return None
    tail = out[k:]
    best = None
    for idx, (name, A) in enumerate(srcs):
        H = A.shape[0]
        if off + d > H:
            continue
        seg = A[off:off + d]
        if seg.shape[0] != tail.shape[0]:
            continue
        diff = np.abs(tail - seg).mean()
        if best is None or diff < best[0]:
            best = (diff, idx, name, off)
    return best


def prefix_match(out, k, A):
    """How well does out[0:k] match A[0:k]?"""
    k = min(k, A.shape[0], out.shape[0])
    if k <= 0:
        return 999.0
    return float(np.abs(out[:k] - A[:k]).mean())


def main():
    srcs = []
    for p in sorted(glob.glob(os.path.join(SRC_DIR, "*.jpg")),
                    key=lambda q: os.path.getmtime(q)):
        srcs.append((os.path.basename(p)[:8], load_rgb(p)))

    outs = sorted(glob.glob(os.path.join(OUT_DIR, "*.jpg")))
    for op in outs:
        out = load_rgb(op)
        h = out.shape[0]
        name = os.path.basename(op)[:8]
        print("=== output %s  %dx%d" % (name, out.shape[1], h))

        cands = []
        for k in range(1200, min(h - 20, 2622) + 1):
            r = best_tail_match(out, k, srcs)
            if r is None:
                continue
            diff, idx, sname, off = r
            if diff > 40:
                continue
            cands.append((diff, k, idx, sname, off, h - k))
        cands.sort()
        for c in cands[:6]:
            diff, k, idx, sname, off, d = c
            # which source does the head match?
            head_best = None
            for j, (nm, A) in enumerate(srcs):
                pm = prefix_match(out, k, A)
                if head_best is None or pm < head_best[0]:
                    head_best = (pm, j, nm)
            print("   k=%-5d d=%-5d tail<-%-9s@off=%-5d taildiff=%.2f | head<-%-9s prefixdiff=%.2f"
                  % (k, d, sname, off, diff, head_best[2], head_best[0]))
        print("")


if __name__ == "__main__":
    main()
