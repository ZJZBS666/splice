"""Reverse-engineer which originals each App output image was built from.

If the three output long-images in splice/samples/ really came from the six
originals in splice/samples/1/, this script finds the exact placement offsets,
and the differences between placements reveal the d values the device used.

Method: for each (output O, original A) pair take a set of strongly textured
rows from A and slide them over O, scoring the fraction of sampled pixels that
agree within TOL. A real containment gives a sharp score near 1.0.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

SAMP = r"E:\DeepSeek\本地电脑\splice\samples"
ORIG = os.path.join(SAMP, "1")
TOL = 16.0
DS = 2


def gray_ds(path, ds=DS):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    g = a @ np.array([0.299, 0.587, 0.114], np.float32)
    return g[::ds, ::ds]


def containment(O, A, seed=0, nrows=40, colstep=24):
    """Best offset o such that A[y] ~= O[y + o]. Returns (o, score)."""
    Ha, Wa = A.shape
    Ho, Wo = O.shape
    sd = A.std(axis=1)
    idx = np.argsort(-sd)[:800]
    idx = idx[idx < Ha]
    rng = np.random.RandomState(seed)
    k = min(nrows, len(idx))
    rows = np.sort(rng.choice(idx, size=k, replace=False))
    cols = np.arange(0, min(Wa, Wo), colstep)
    T = A[np.ix_(rows, cols)]
    best_o, best_s = None, -1.0
    lo = -int(rows.max())
    hi = Ho - int(rows.min())
    for o in range(lo, hi):
        rr = rows + o
        if rr.min() < 0 or rr.max() >= Ho:
            continue
        S = O[np.ix_(rr, cols)]
        s = float((np.abs(S - T) <= TOL).mean())
        if s > best_s:
            best_s = s
            best_o = o
    return best_o, best_s


def matched_runs(O, A, o, thr=0.95, min_len=40):
    """Contiguous row ranges of A that match O at offset o."""
    Ha = A.shape[0]
    Ho = O.shape[0]
    y0 = max(0, -o)
    y1 = min(Ha, Ho - o)
    if y1 - y0 < min_len:
        return []
    ys = np.arange(y0, y1, 2)
    diff = np.abs(A[ys] - O[ys + o])
    cf = (diff <= TOL).mean(axis=1)
    ok = cf >= thr
    runs = []
    s = None
    for k, v in enumerate(ok):
        if v and s is None:
            s = k
        elif not v and s is not None:
            if (k - s) * 2 >= min_len:
                runs.append((int(ys[s]), int(ys[k - 1])))
            s = None
    if s is not None and (len(ok) - s) * 2 >= min_len:
        runs.append((int(ys[s]), int(ys[-1])))
    return runs


def main():
    outs = sorted(glob.glob(os.path.join(SAMP, "*.jpg")))
    origs = sorted(glob.glob(os.path.join(ORIG, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    onames = [os.path.basename(p)[:8] for p in origs]
    print("outputs: %d   originals: %d   (downsampled by %d)"
          % (len(outs), len(origs), DS))
    print("")
    Ogs = [gray_ds(p) for p in outs]
    Ags = [gray_ds(p) for p in origs]

    for oi, (p, O) in enumerate(zip(outs, Ogs)):
        print("=== output %d: %s  size=%dx%d"
              % (oi, os.path.basename(p), O.shape[1] * DS, O.shape[0] * DS))
        res = []
        for ai, A in enumerate(Ags):
            o, s = containment(O, A)
            res.append((ai, o, s))
        res.sort(key=lambda t: -t[2])
        for ai, o, s in res:
            tag = ""
            if s >= 0.95:
                tag = "  <== CONTAINED"
            elif s >= 0.80:
                tag = "  <== partial"
            print("    %s  best_o=%-6d score=%.4f%s"
                  % (onames[ai], o, s, tag))
        # matched runs for the contained ones
        for ai, o, s in res:
            if s < 0.80:
                continue
            runs = matched_runs(O, Ags[ai], o)
            if runs:
                print("      %s placed at o=%d, matching A-rows: %s"
                      % (onames[ai], o, runs))
        print("")

    print("=== how to read this ===")
    print("  if output i contains A at offset o_A and B at offset o_B,")
    print("  then the device used d = o_A - o_B for that seam.")


if __name__ == "__main__":
    main()
