# -*- coding: utf-8 -*-
"""
分带一致性闸门 —— 用与主指标一致的归一化 L1（sum/sum）重算，
确认分离度是否保持。同时给出投票计数版判据。

POS: 真匹配。NEG: 无关两图在全局 argmin 处。
判据 = "指向同一偏移（偏差 <= 1）的分段数量"。
"""
import numpy as np
from PIL import Image

import gen_samples as G
import stitcher as S
import test_hard as T

N_BANDS = 4
BAND_WIN = 8
AGREE_TOL = 1


def band_cost(A, B, d, y0, y1, sdA, col_stride):
    """[y0,y1) 内、偏移 d 的归一化 L1 代价（只统计纹理行）。"""
    H = A.shape[0]
    y1 = min(y1, H - d)
    if y1 <= y0 + 4:
        return None
    ys = np.arange(y0, y1)
    a = A[ys + d][:, ::col_stride]
    b = B[ys][:, ::col_stride]
    sd = sdA[ys + d]
    tex = sd >= S.TEXTURE_MIN
    if int(tex.sum()) < 8:
        return None
    mad = np.abs(a - b).mean(axis=1)
    den = float(sd[tex].sum())
    if den < 1e-6:
        return None
    return float(mad[tex].sum() / den)


def band_votes(A, B, d, top, bottom, n_bands=N_BANDS, win=BAND_WIN,
               col_stride=S.COARSE_COL_STRIDE):
    """返回 (agree, devs)。agree = 偏差 <= AGREE_TOL 的分段数。"""
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 16:
        return 0, []
    sdA = S._row_sd(A, col_stride)
    ys_all = np.arange(top, n_end)
    tex = sdA[ys_all + d] >= S.TEXTURE_MIN
    ys_tex = ys_all[tex]
    if ys_tex.size < n_bands * 8:
        return 0, []
    y_lo, y_hi = int(ys_tex[0]), int(ys_tex[-1])
    span = y_hi - y_lo + 1
    devs = []
    for k in range(n_bands):
        b0 = y_lo + span * k // n_bands
        b1 = y_lo + span * (k + 1) // n_bands
        best_dd, best_c = None, None
        for dd in range(max(1, d - win), d + win + 1):
            c = band_cost(A, B, dd, b0, b1, sdA, col_stride)
            if c is None:
                continue
            if best_c is None or c < best_c:
                best_c, best_dd = c, dd
        if best_dd is not None:
            devs.append(best_dd - d)
    agree = sum(1 for x in devs if abs(x) <= AGREE_TOL)
    return agree, devs


def collect():
    pos, neg = [], []

    scenes = G.build_all()
    for name, sc in scenes.items():
        grays = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
                 for p in sc["shots"]]
        top, bottom = S.detect_overlays(grays)
        for i in range(len(grays) - 1):
            truth = sc["deltas"][i]
            ag, dv = band_votes(grays[i], grays[i + 1], truth, top, bottom)
            pos.append((name + "/p%d" % i, ag, dv))

    for seed in (777, 888, 555):
        content = T.make_irregular_content(seed)
        for tail in (0.0, 0.25, 0.5, 0.75):
            A, B, truth = T.pair_gray(content, 1400.0, 1400.0 + 1437 + tail)
            ag, dv = band_votes(A, B, truth, 0, 0)
            pos.append(("sub s%d t%.2f" % (seed, tail), ag, dv))

    content = T.make_irregular_content(555)
    H = G.H
    vabs = 1400.0 + (G.STATUS_H + G.NAV_H) + (H // 2 - 550 // 2)
    for tail in (0.0, 0.25, 0.5):
        v0 = T.make_textured_video(11)
        v1 = T.make_textured_video(12)
        i0 = T.make_shot(content, 1400.0, v0, vabs, 550, 1000)
        i1 = T.make_shot(content, 1400.0 + 1437 + tail, v1, vabs, 550, 1000)
        ag, dv = band_votes(T.gray_of(i0), T.gray_of(i1), 1437, 0, 0)
        pos.append(("video t%.2f" % tail, ag, dv))

    for s1, s2 in [(101, 202), (11, 22), (303, 404), (55, 66), (777, 101),
                   (888, 202), (1234, 5678)]:
        c1 = T.make_irregular_content(s1)
        c2 = T.make_irregular_content(s2)
        A = T.gray_of(T.make_shot(c1, 1400.0))
        B = T.gray_of(T.make_shot(c2, 1400.0))
        Hh = A.shape[0]
        min_scroll = max(int(S.MIN_SCROLL_FRAC * Hh), S.FINE_WINDOW)
        d_hi = Hh - max(24, int(S.MIN_OVERLAP_FRAC * Hh))
        sdA = S._row_sd(A, S.COARSE_COL_STRIDE)
        cd, cc, _, _ = S._exclusion_search(
            A, B, 0, 0, min_scroll, d_hi, sdA,
            S.COARSE_ROW_STRIDE, S.COARSE_COL_STRIDE,
            max(8, S.BAD_BAND_MIN // S.COARSE_ROW_STRIDE), S.MAX_EXCLUDED_FRAC)
        if cd is None:
            neg.append(("unrel %d/%d" % (s1, s2), 0, []))
            continue
        ag, dv = band_votes(A, B, cd, 0, 0)
        neg.append(("unrel %d/%d d=%d" % (s1, s2, cd), ag, dv))
    return pos, neg


def main():
    import sys
    global N_BANDS
    if len(sys.argv) > 1:
        N_BANDS = int(sys.argv[1])
    pos, neg = collect()
    print("N_BANDS = %d  AGREE_TOL = %d  BAND_WIN = %d"
          % (N_BANDS, AGREE_TOL, BAND_WIN))
    print("---- POSITIVE")
    for n, ag, dv in pos:
        print("  %-18s agree=%d/%d devs=%s" % (n, ag, N_BANDS, str(dv)))
    print("---- NEGATIVE")
    for n, ag, dv in neg:
        print("  %-18s agree=%d/%d devs=%s" % (n, ag, N_BANDS, str(dv)))

    pa = [r[1] for r in pos]
    na = [r[1] for r in neg]
    print("")
    print("pos agree: min=%d" % min(pa))
    print("neg agree: max=%d" % max(na))
    print("separation: %s" % ("YES" if min(pa) > max(na) else "NO"))
    if min(pa) > max(na):
        print("suggest MIN_BAND_AGREE in (%d, %d]" % (max(na), min(pa)))


if __name__ == "__main__":
    main()
