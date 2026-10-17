# -*- coding: utf-8 -*-
"""
分带一致性闸门（严格版）。

思路：真匹配时，把有效区间切成 N 段，每段各自在 [d-8, d+8] 内找最优，
得到的 d 应该都落在真值附近（误差 <= 1）。无关两图即使全局 argmin 落在
某个 d，各段的最优也会乱指。

与 calib_bands.py 的区别：这里不依赖 stats_at 的提前返回，
每段都强制返回一个 d（该段内最小误差的候选），因此 NEG 不会退化成 99。
"""
import numpy as np
from PIL import Image

import gen_samples as G
import stitcher as S
import test_hard as T

N_BANDS = 4
BAND_WIN = 8


def band_devs(A, B, d, top, bottom, n_bands=N_BANDS, win=BAND_WIN):
    """返回每段各自 argmin 相对 d 的偏差列表（全部为整数，不返回 None）。"""
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 16:
        return []
    ys_all = np.arange(top, n_end)
    tex = A[ys_all + d].std(axis=1) >= S.TEXTURE_MIN
    ys_tex = ys_all[tex]
    if ys_tex.size < n_bands * 8:
        return []
    y_lo, y_hi = int(ys_tex[0]), int(ys_tex[-1])
    span = y_hi - y_lo + 1
    devs = []
    for k in range(n_bands):
        b0 = y_lo + span * k // n_bands
        b1 = y_lo + span * (k + 1) // n_bands
        best_dd, best_m = None, None
        for dd in range(max(1, d - win), d + win + 1):
            e = H - bottom - dd
            hi = min(b1, e)
            if hi <= b0 + 4:
                continue
            yy = np.arange(b0, hi)
            if yy.size < 8:
                continue
            x1 = A[yy + dd]
            x2 = B[yy]
            t = x1.std(axis=1) >= S.TEXTURE_MIN
            if int(t.sum()) < 8:
                continue
            m = float(np.abs(x1[t] - x2[t]).mean())
            if best_m is None or m < best_m:
                best_m, best_dd = m, dd
        if best_dd is not None:
            devs.append(best_dd - d)
    return devs


def collect():
    pos, neg = [], []

    scenes = G.build_all()
    for name, sc in scenes.items():
        grays = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
                 for p in sc["shots"]]
        top, bottom = S.detect_overlays(grays)
        for i in range(len(grays) - 1):
            truth = sc["deltas"][i]
            dv = band_devs(grays[i], grays[i + 1], truth, top, bottom)
            if dv:
                pos.append((name + "/p%d" % i, dv))

    for seed in (777, 888, 555):
        content = T.make_irregular_content(seed)
        for tail in (0.0, 0.25, 0.5, 0.75):
            A, B, truth = T.pair_gray(content, 1400.0, 1400.0 + 1437 + tail)
            dv = band_devs(A, B, truth, 0, 0)
            if dv:
                pos.append(("sub s%d t%.2f" % (seed, tail), dv))

    content = T.make_irregular_content(555)
    H = G.H
    vabs = 1400.0 + (G.STATUS_H + G.NAV_H) + (H // 2 - 550 // 2)
    for tail in (0.0, 0.25, 0.5):
        v0 = T.make_textured_video(11)
        v1 = T.make_textured_video(12)
        i0 = T.make_shot(content, 1400.0, v0, vabs, 550, 1000)
        i1 = T.make_shot(content, 1400.0 + 1437 + tail, v1, vabs, 550, 1000)
        dv = band_devs(T.gray_of(i0), T.gray_of(i1), 1437, 0, 0)
        if dv:
            pos.append(("video t%.2f" % tail, dv))

    # 负例：把"无关两图"的全局 argmin 当作候选 d（算法会选它），看分带是否一致
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
            neg.append(("unrel %d/%d" % (s1, s2), None))
            continue
        dv = band_devs(A, B, cd, 0, 0)
        neg.append(("unrel %d/%d d=%d" % (s1, s2, cd), dv))
    return pos, neg


def main():
    pos, neg = collect()
    print("---- POSITIVE (devs should be small)")
    for n, dv in pos:
        print("  %-18s devs=%-24s maxabs=%d" % (n, str(dv), max(abs(x) for x in dv)))
    print("---- NEGATIVE (devs should be scattered)")
    for n, dv in neg:
        if not dv:
            print("  %-18s devs=None (no candidate)" % n)
        else:
            print("  %-18s devs=%-24s maxabs=%d"
                  % (n, str(dv), max(abs(x) for x in dv)))

    pm = [max(abs(x) for x in dv) for _, dv in pos if dv]
    nm = [max(abs(x) for x in dv) for _, dv in neg if dv]
    print("")
    print("pos maxabs: max=%d" % max(pm))
    print("neg maxabs: min=%d" % (min(nm) if nm else -1))
    print("separation: %s" % ("YES" if pm and nm and max(pm) < min(nm) else "NO"))


if __name__ == "__main__":
    main()
