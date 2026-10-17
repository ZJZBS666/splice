"""Row-by-row provenance map of each App output image.

For every output row y, find which (original, row) it came from, if any.
Output rows are compared against ALL rows of ALL originals at once by
building, for each original, the nearest-row index in a coarse descriptor
space (block means), then verifying with a strict pixel comparison.

Result: a compact list of "output y0..y1 <- original name @ a..b" segments,
which reveals exactly what the device stitched and where it lost content.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

SAMP = r"E:\DeepSeek\本地电脑\splice\samples"
ORIG = os.path.join(SAMP, "1")
TOL = 20.0
DESC_W = 60          # descriptor width (block means across x)
DESC_H = 8           # descriptor height (rows averaged)


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32) @ \
        np.array([0.299, 0.587, 0.114], np.float32)


def descriptors(g):
    """(n_blocks, 1206) -> block-mean descriptor per row block."""
    H, W = g.shape
    nb = H // DESC_H
    d = g[:nb * DESC_H].reshape(nb, DESC_H, W).mean(axis=1)
    # downsample columns by block means
    step = W // DESC_W
    d = d[:, :DESC_W * step].reshape(nb, DESC_W, step).mean(axis=2)
    return d


def match_rows(out_g, orig_g, desc_o, desc_a):
    """For each output row block, best original row block. Returns idx array."""
    # nearest neighbour by L2 on descriptors
    n_o = desc_o.shape[0]
    n_a = desc_a.shape[0]
    # pairwise distances, chunked to limit memory
    idx = np.empty(n_o, dtype=np.int32)
    dist = np.empty(n_o, dtype=np.float32)
    for s in range(0, n_o, 512):
        e = min(n_o, s + 512)
        blk = desc_o[s:e]
        d2 = ((blk[:, None, :] - desc_a[None, :, :]) ** 2).sum(axis=2)
        j = d2.argmin(axis=1)
        idx[s:e] = j
        dist[s:e] = np.sqrt(d2[np.arange(e - s), j])
    return idx, dist


def verify(out_g, orig_g, y, a, tol=TOL):
    """Strict check: compare output row block at y with original at a."""
    y0 = y * DESC_H
    a0 = a * DESC_H
    if y0 + DESC_H > out_g.shape[0] or a0 + DESC_H > orig_g.shape[0]:
        return 0.0
    o = out_g[y0:y0 + DESC_H]
    p = orig_g[a0:a0 + DESC_H]
    return float((np.abs(o - p) <= tol).mean())


def segments(labels, dist, out_g, origs_g, min_len=6):
    """Group consecutive output blocks with same (orig, offset)."""
    segs = []
    s = 0
    for k in range(1, len(labels) + 1):
        if k == len(labels) or labels[k] != labels[s]:
            if k - s >= min_len and labels[s][0] >= 0:
                segs.append((s * DESC_H, k * DESC_H, labels[s][0],
                             labels[s][1] * DESC_H,
                             (labels[s][1] - s) * DESC_H))
            s = k
    return segs


def main():
    outs = sorted(glob.glob(os.path.join(SAMP, "*.jpg")))
    origs = sorted(glob.glob(os.path.join(ORIG, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    onames = [os.path.basename(p)[:8] for p in origs]
    Ags = [load_gray(p) for p in origs]
    Adesc = [descriptors(a) for a in Ags]

    for p in outs:
        O = load_gray(p)
        Odesc = descriptors(O)
        n_o = Odesc.shape[0]
        print("=== %s  %dx%d" % (os.path.basename(p), O.shape[1], O.shape[0]))
        labels = []
        for b in range(n_o):
            best = None
            for ai in range(len(Ags)):
                idx, dist = match_rows(Odesc[b:b + 1], Ags[ai],
                                       Odesc[b:b + 1], Adesc[ai])
                sc = verify(O, Ags[ai], b, int(idx[0]))
                if sc >= 0.85 and (best is None or sc > best[2]):
                    best = (ai, int(idx[0]), sc)
            labels.append((best[0], best[1]) if best else (-1, -1))
        # print the segment map
        s = 0
        for k in range(1, n_o + 1):
            if k == n_o or labels[k] != labels[s]:
                if k - s >= 4:
                    ai, a = labels[s]
                    nm = onames[ai] if ai >= 0 else "----"
                    print("    out %5d..%5d (%5d rows) <- %s @ %5d"
                          % (s * DESC_H, k * DESC_H, (k - s) * DESC_H,
                             nm, a * DESC_H))
                s = k
        print("")


if __name__ == "__main__":
    main()
