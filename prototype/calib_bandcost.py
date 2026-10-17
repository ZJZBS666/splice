"""Calibrate a per-band absolute cost gate for AGREEING bands.

dbg_abstain showed the agreeing bands' own minimum cost separates cleanly:
    real positive : 0.0093 / 0.0180 / 0.0306 / 0.1547
    unrelated     : 2.04 / 2.22 / 2.42 / 2.15
So a band only counts as a real AGREE if its own minimum cost is below
BAND_MAX_COST. Sweep positives (subpixel, video, integer, real) to find the
worst-case agreeing-band minimum.

ASCII-only prints.
"""
import glob
import os

import numpy as np
from PIL import Image

import stitcher as S
import test_hard as T


def band_mins(A, B, d, top, bottom, col_stride=S.COARSE_COL_STRIDE):
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 16:
        return []
    sd = S._row_sd(A, col_stride)
    ys_all = np.arange(top, n_end)
    ys_tex = ys_all[sd[ys_all + d] >= S.TEXTURE_MIN]
    if ys_tex.size < S.BAND_COUNT * 8:
        return []
    y_lo, y_hi = int(ys_tex[0]), int(ys_tex[-1])
    span = y_hi - y_lo + 1
    out = []
    for k in range(S.BAND_COUNT):
        b0 = y_lo + span * k // S.BAND_COUNT
        b1 = y_lo + span * (k + 1) // S.BAND_COUNT
        best = None
        cs = []
        for dd in range(max(1, d - S.BAND_WIN), d + S.BAND_WIN + 1):
            c = S._band_cost(A, B, dd, b0, b1, sd, col_stride)
            if c is None:
                continue
            cs.append(c)
            if best is None or c < best:
                best = c
        if best is None:
            continue
        cmax = max(cs)
        spread = (cmax - min(cs)) / cmax if cmax > 1e-9 else 0.0
        out.append((best, spread))
    return out


def report(label, A, B, d, top, bottom):
    bs = band_mins(A, B, d, top, bottom)
    ag = [m for (m, sp) in bs if sp >= S.BAND_SPREAD_MIN]
    ab = [m for (m, sp) in bs if sp < S.BAND_SPREAD_MIN]
    print("%-28s agree_mins=%s  abstain_mins=%s"
          % (label, ["%.4f" % x for x in ag], ["%.4f" % x for x in ab]))


def _g(x):
    return S.to_gray(np.asarray(x.convert("RGB")))


def main():
    print("### positives: subpixel irregular")
    for seed in (777, 888):
        content = T.make_irregular_content(seed)
        for tail in (0.0, 0.25, 0.5, 0.75):
            A = T.make_shot(content, 5000, None, 0, 0, 0)
            B = T.make_shot(content, 5000 + 1437 + tail, None, 0, 0, 0)
            report("irr%d tail=%.2f" % (seed, tail), _g(A), _g(B), 1437, 321, 34)

    print("")
    print("### positives: video")
    for tail in (0.0, 0.25, 0.5):
        content = T.make_irregular_content(777)
        vid1 = T.make_textured_video(11, 1000, 550)
        vid2 = T.make_textured_video(22, 1000, 550)
        A = T.make_shot(content, 5000, vid1, 2600, 550, 1000)
        B = T.make_shot(content, 5000 + 1437 + tail, vid2, 2600, 550, 1000)
        report("video tail=%.2f" % tail, _g(A), _g(B), 1437, 321, 34)

    print("")
    print("### positives: synthetic integer")
    import gen_samples as G
    sets = G.build_all()
    for name, info in sets.items():
        rg = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
              for p in info["shots"]]
        for k in range(len(rg) - 1):
            report("%s pair%d" % (name, k), rg[k], rg[k + 1],
                   info["deltas"][k], 321, 34)

    print("")
    print("### positives: REAL shots (top=0 bot=0)")
    files = sorted(glob.glob(r"E:\DeepSeek\本地电脑\splice\samples\1\*.jpg"),
                   key=lambda p: os.path.getmtime(p))
    gs = [S.to_gray(np.asarray(Image.open(p).convert("RGB"))) for p in files]
    for (i, d) in [(0, 1048), (1, 1341), (2, 1109), (4, 778)]:
        report("REAL pair%d" % i, gs[i], gs[i + 1], d, 0, 0)
    for (i, d) in [(0, 1048), (1, 1341), (2, 1109), (4, 778)]:
        report("REAL pair%d t318b286" % i, gs[i], gs[i + 1], d, 318, 286)

    print("")
    print("### negatives")
    g1 = S.to_gray(T.make_irregular_content(101))
    g2 = S.to_gray(T.make_irregular_content(202))
    d, c = S.find_offset(g1, g2, 0, 0)
    if d is not None:
        report("synth unrelated d=%d" % d, g1, g2, d, 0, 0)
    for probe in (136, 400, 1000):
        report("real 3-4 probe%d" % probe, gs[3], gs[4], probe, 0, 0)


if __name__ == "__main__":
    main()
