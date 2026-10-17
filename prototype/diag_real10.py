"""Count how many times the bottom input bar of an original appears in an output.

Take a template = the bottom strip of a known original screenshot (the WeChat
input bar plus home indicator, rows H-260..H). In a correct long stitch that
strip must appear EXACTLY ONCE, at the very bottom. Each additional occurrence
marks a segment boundary.

Slide the template over every output image at every row and record rows whose
mean abs difference is tiny.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

SAMP = r"E:\DeepSeek\本地电脑\splice\samples"
ORIG = os.path.join(SAMP, "1")
TOL = 12.0


def load_gray(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32) @ \
        np.array([0.299, 0.587, 0.114], np.float32)


def find_hits(out, tpl, tol=TOL, colstep=4):
    """Rows in `out` where `tpl` matches. Returns [(y, score)]."""
    Th, W = tpl.shape
    Ho = out.shape[0]
    t = tpl[:, ::colstep]
    hits = []
    for y in range(0, Ho - Th + 1):
        s = float((np.abs(out[y:y + Th, ::colstep] - t) <= tol).mean())
        hits.append((y, s))
    return hits


def group(hits, thr):
    ys = [y for y, s in hits if s >= thr]
    out = []
    s = None
    prev = None
    for y in ys:
        if s is None:
            s = y
        elif y - prev > 3:
            out.append((s, prev))
            s = y
        prev = y
    if s is not None:
        out.append((s, prev))
    return out


def main():
    origs = sorted(glob.glob(os.path.join(ORIG, "*.jpg")),
                   key=lambda p: os.path.getmtime(p))
    # template from the 2nd original (plain chat, input bar visible)
    tpl_src = origs[1]
    g = load_gray(tpl_src)
    H = g.shape[0]
    tpl = g[H - 260:H]
    print("template from %s rows %d..%d  (%dx%d)"
          % (os.path.basename(tpl_src)[:8], H - 260, H, tpl.shape[1], tpl.shape[0]))
    print("")

    # sanity: how well does the template match its own original?
    own = find_hits(g, tpl)
    best = max(own, key=lambda t: t[1])
    print("self-match: y=%d score=%.4f" % best)
    print("")

    for p in sorted(glob.glob(os.path.join(SAMP, "*.jpg"))):
        o = load_gray(p)
        hits = find_hits(o, tpl)
        best = max(hits, key=lambda t: t[1])
        for thr in (0.95, 0.90, 0.85):
            gr = group(hits, thr)
            print("%s thr=%.2f  count=%d  groups=%s"
                  % (os.path.basename(p)[:8], thr, len(gr), gr))
        print("   best score=%.4f at y=%d  (output H=%d)"
              % (best[1], best[0], o.shape[0]))
        print("")

    print("=== interpretation ===")
    print("  exactly one hit at the bottom  -> correct stitch")
    print("  N hits                         -> N screenshots hard-glued together")


if __name__ == "__main__":
    main()
