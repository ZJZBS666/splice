# -*- coding: utf-8 -*-
"""
闸门候选对比：在"已找到的 d"上计算多个独立统计量，看哪个能把
真匹配（POS）和无关两图（NEG）分开。

候选：
  ncc      零均值归一化互相关（全局，抽样行）
  band_agr 把有效区间横切 3 段，每段各自 argmin 的 d 与全局 d 的最大偏差
           —— 真匹配时三段都指向同一个 d；无关图各段乱指
  used     参与打分的纹理行占比
只打印 ASCII。
"""
import numpy as np
from PIL import Image

import gen_samples as G
import stitcher as S
import test_hard as T

N_BANDS = 3


def stats_at(A, B, d, top, bottom):
    """在给定 d 上算 ncc / 分带一致性 / used。"""
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 8:
        return None
    ys = np.arange(top, n_end, 2)          # 抽样行，加速
    a = A[ys + d]
    b = B[ys]
    tex = a.std(axis=1) >= S.TEXTURE_MIN
    if int(tex.sum()) < 40:
        return None
    aa = a[tex].astype(np.float64)
    bb = b[tex].astype(np.float64)
    aa = aa - aa.mean()
    bb = bb - bb.mean()
    den = np.sqrt((aa * aa).sum() * (bb * bb).sum())
    ncc = float((aa * bb).sum() / den) if den > 1e-9 else 0.0

    # 分带一致性：每段单独找 argmin
    ys_tex = ys[tex]
    y_lo, y_hi = int(ys_tex.min()), int(ys_tex.max())
    span = y_hi - y_lo + 1
    bests = []
    for k in range(N_BANDS):
        b0 = y_lo + span * k // N_BANDS
        b1 = y_lo + span * (k + 1) // N_BANDS
        cand, cc = None, None
        for dd in range(max(1, d - 8), d + 9):
            e = H - bottom - dd
            if e <= b0 + 4:
                continue
            yy = np.arange(b0, min(b1, e), 2)
            if yy.size < 8:
                continue
            x1 = A[yy + dd]
            x2 = B[yy]
            t = x1.std(axis=1) >= S.TEXTURE_MIN
            if int(t.sum()) < 8:
                continue
            m = float(np.abs(x1[t] - x2[t]).mean())
            if cc is None or m < cc:
                cc, cand = m, dd
        bests.append(cand)
    got = [x for x in bests if x is not None]
    agr = (max(abs(x - d) for x in got) if got else 99)

    # used：带排除掩码复核
    sdA1 = S._row_sd(A, 1)
    _, _, f_ex, _ = S._exclusion_search(
        A, B, top, bottom, max(1, d - 2), d + 2, sdA1, 1, 1,
        S.BAD_BAND_MIN, S.MAX_EXCLUDED_FRAC)
    r = S._cost_at(A, B, d, top, bottom, sdA1, 1, 1, exclude=f_ex)
    used = 0.0
    if r:
        _, ur, _, _, tx = r
        used = ur / max(1, int(tx.sum()))
    return ncc, agr, used


def collect():
    pos, neg = [], []

    scenes = G.build_all()
    for name, sc in scenes.items():
        grays = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
                 for p in sc["shots"]]
        top, bottom = S.detect_overlays(grays)
        for i in range(len(grays) - 1):
            truth = sc["deltas"][i]
            s = stats_at(grays[i], grays[i + 1], truth, top, bottom)
            if s:
                pos.append((name + "/p%d" % i, s[0], s[1], s[2]))

    for seed in (777, 888, 555):
        content = T.make_irregular_content(seed)
        for tail in (0.0, 0.25, 0.5, 0.75):
            A, B, truth = T.pair_gray(content, 1400.0, 1400.0 + 1437 + tail)
            s = stats_at(A, B, truth, 0, 0)
            if s:
                pos.append(("sub s%d t%.2f" % (seed, tail), s[0], s[1], s[2]))

    content = T.make_irregular_content(555)
    H = G.H
    vabs = 1400.0 + (G.STATUS_H + G.NAV_H) + (H // 2 - 550 // 2)
    for tail in (0.0, 0.25, 0.5):
        v0 = T.make_textured_video(11)
        v1 = T.make_textured_video(12)
        i0 = T.make_shot(content, 1400.0, v0, vabs, 550, 1000)
        i1 = T.make_shot(content, 1400.0 + 1437 + tail, v1, vabs, 550, 1000)
        s = stats_at(T.gray_of(i0), T.gray_of(i1), 1437, 0, 0)
        if s:
            pos.append(("video t%.2f" % tail, s[0], s[1], s[2]))

    # 负例：无关两图。用 find_offset 给出的 d 作为"它以为的匹配"
    for s1, s2 in [(101, 202), (11, 22), (303, 404), (55, 66), (777, 101),
                   (888, 202)]:
        c1 = T.make_irregular_content(s1)
        c2 = T.make_irregular_content(s2)
        A = T.gray_of(T.make_shot(c1, 1400.0))
        B = T.gray_of(T.make_shot(c2, 1400.0))
        d, _ = S.find_offset(A, B, 0, 0)
        if d is None:
            neg.append(("unrel %d/%d" % (s1, s2), 1.0, 99, 0.0))
            continue
        s = stats_at(A, B, d, 0, 0)
        if s:
            neg.append(("unrel %d/%d d=%d" % (s1, s2, d), s[0], s[1], s[2]))
    return pos, neg


def main():
    pos, neg = collect()
    print("---- POSITIVE")
    for n, ncc, agr, used in pos:
        print("  %-18s ncc=%.4f band_dev=%-3d used=%.2f" % (n, ncc, agr, used))
    print("---- NEGATIVE")
    for n, ncc, agr, used in neg:
        print("  %-18s ncc=%.4f band_dev=%-3d used=%.2f" % (n, ncc, agr, used))

    pn = [r[1] for r in pos]
    nn = [r[1] for r in neg]
    pa = [r[2] for r in pos]
    na = [r[2] for r in neg]
    print("")
    print("ncc : pos min=%.4f  neg max=%.4f  sep=%s"
          % (min(pn), max(nn), "YES" if min(pn) > max(nn) else "NO"))
    print("band: pos max=%d  neg min=%d  sep=%s"
          % (max(pa), min(na), "YES" if max(pa) < min(na) else "NO"))


if __name__ == "__main__":
    main()
