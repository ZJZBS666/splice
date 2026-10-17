# -*- coding: utf-8 -*-
"""
闸门标定：把"真匹配"和"无关两图"的 (peak, cost) 分布都测出来，
用数据决定 MATCH_COST_THRESHOLD / PEAK_RATIO_THRESHOLD 该取多少。

只打印 ASCII，Windows 控制台安全。
"""
import numpy as np
from PIL import Image

import gen_samples as G
import stitcher as S
import test_hard as T


def gates(A, B, top, bottom):
    """复刻 find_offset 的两段式流程，返回 (d, coarse_peak, fine_cost, n_tex, used_frac)。"""
    H = A.shape[0]
    min_overlap = max(24, int(S.MIN_OVERLAP_FRAC * H))
    d_hi = H - bottom - min_overlap - top
    min_scroll = max(int(S.MIN_SCROLL_FRAC * (H - top - bottom)), S.FINE_WINDOW)
    lo, hi = min_scroll, d_hi
    if hi - lo < 8:
        return None, None, None, 0, 0.0

    sdA = S._row_sd(A, S.COARSE_COL_STRIDE)
    c_d, c_c, _, curve = S._exclusion_search(
        A, B, top, bottom, lo, hi, sdA,
        S.COARSE_ROW_STRIDE, S.COARSE_COL_STRIDE,
        max(8, S.BAD_BAND_MIN // S.COARSE_ROW_STRIDE), S.MAX_EXCLUDED_FRAC)
    if c_d is None or not curve:
        return None, None, None, 0, 0.0
    med = float(np.median(list(curve.values())))
    peak = 0.0 if med <= 1e-9 else c_c / med

    f_lo = max(lo, c_d - S.FINE_WINDOW * 2)
    f_hi = min(hi, c_d + S.FINE_WINDOW * 2)
    sdA1 = S._row_sd(A, 1)
    f_d, f_c, f_ex, _ = S._exclusion_search(
        A, B, top, bottom, f_lo, f_hi, sdA1, 1, 1,
        S.BAD_BAND_MIN, S.MAX_EXCLUDED_FRAC)
    if f_d is None:
        return None, peak, None, 0, 0.0
    got = S._cost_at(A, B, f_d, top, bottom, sdA1, 1, 1, exclude=f_ex)
    if got is None:
        return f_d, peak, None, 0, 0.0
    cost, used, ys, rne, tex = got
    n_tex = int(tex.sum())
    return f_d, peak, cost, n_tex, (used / n_tex if n_tex else 0.0)


def collect():
    pos, neg = [], []

    # --- 正例 1：20 个合成整数场景 pair
    scenes = G.build_all()
    for name, sc in scenes.items():
        grays = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
                 for p in sc["shots"]]
        st = S.static_rows(grays)
        top, bottom = S.detect_overlays(grays)
        for i in range(len(grays) - 1):
            d, peak, cost, n_tex, uf = gates(grays[i], grays[i + 1], top, bottom)
            truth = sc["deltas"][i]
            ok = d is not None and abs(d - truth) <= 1
            pos.append((name + "/p%d" % i, peak, cost, n_tex, uf, ok))

    # --- 正例 2：亚像素 + 视频
    for seed in (777, 888, 555):
        content = T.make_irregular_content(seed)
        for tail in (0.0, 0.25, 0.5, 0.75):
            A, B, truth = T.pair_gray(content, 1400.0, 1400.0 + 1437 + tail)
            d, peak, cost, n_tex, uf = gates(A, B, 0, 0)
            ok = d is not None and abs(d - truth) <= 1
            pos.append(("sub s%d t%.2f" % (seed, tail), peak, cost, n_tex, uf, ok))

    content = T.make_irregular_content(555)
    H = G.H
    vabs = 1400.0 + (G.STATUS_H + G.NAV_H) + (H // 2 - 550 // 2)
    for tail in (0.0, 0.25, 0.5):
        v0 = T.make_textured_video(11)
        v1 = T.make_textured_video(12)
        i0 = T.make_shot(content, 1400.0, v0, vabs, 550, 1000)
        i1 = T.make_shot(content, 1400.0 + 1437 + tail, v1, vabs, 550, 1000)
        d, peak, cost, n_tex, uf = gates(T.gray_of(i0), T.gray_of(i1), 0, 0)
        ok = d is not None and abs(d - 1437) <= 1
        pos.append(("video t%.2f" % tail, peak, cost, n_tex, uf, ok))

    # --- 负例：完全无关的两张截图（不同 seed 的随机内容，模拟两个不同 App）
    seeds = [(101, 202), (11, 22), (303, 404), (55, 66), (777, 101), (888, 202)]
    for s1, s2 in seeds:
        c1 = T.make_irregular_content(s1)
        c2 = T.make_irregular_content(s2)
        A = T.gray_of(T.make_shot(c1, 1400.0))
        B = T.gray_of(T.make_shot(c2, 1400.0))
        d, peak, cost, n_tex, uf = gates(A, B, 0, 0)
        neg.append(("unrel %d/%d" % (s1, s2), peak, cost, n_tex, uf, d is None))
    return pos, neg


def show(tag, rows):
    print("---- %s (%d)" % (tag, len(rows)))
    for name, peak, cost, n_tex, uf, ok in rows:
        print("  %-16s peak=%-8s cost=%-8s n_tex=%-6d used=%.2f  %s"
              % (name,
                 "None" if peak is None else "%.4f" % peak,
                 "None" if cost is None else "%.4f" % cost,
                 n_tex, uf, "OK" if ok else "MISS"))


def main():
    pos, neg = collect()
    show("POSITIVE (should match)", pos)
    show("NEGATIVE (should be gap)", neg)

    pp = [r[1] for r in pos if r[1] is not None]
    pc = [r[2] for r in pos if r[2] is not None]
    np_ = [r[1] for r in neg if r[1] is not None]
    nc = [r[2] for r in neg if r[2] is not None]
    print("")
    print("POS peak: min=%.4f max=%.4f" % (min(pp), max(pp)))
    print("POS cost: min=%.4f max=%.4f" % (min(pc), max(pc)))
    print("NEG peak: min=%.4f max=%.4f" % (min(np_), max(np_)))
    print("NEG cost: min=%.4f max=%.4f" % (min(nc), max(nc)))
    print("")
    print("peak separation: pos_max=%.4f  neg_min=%.4f  gap=%s"
          % (max(pp), min(np_), "YES" if max(pp) < min(np_) else "NO"))
    print("cost separation: pos_max=%.4f  neg_min=%.4f  gap=%s"
          % (max(pc), min(nc), "YES" if max(pc) < min(nc) else "NO"))


if __name__ == "__main__":
    main()
