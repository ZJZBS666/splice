"""在完整搜索流程里比较几种打分函数，选出既抗亚像素又抗动态内容的那一个。

背景：
  - 现用 frac（整行完全匹配占比）：亚像素滚动下恒为 0，彻底失效（test_subpixel3 已证）
  - 备选：行均差的聚合值，按 A 的灰度标准差归一化

聚合方式对比（test_agg 已测，但只在固定 d 上比）：
  mean    ：整数场景 0.000 vs 错1px 0.02（好）；亚像素场景 0.14~0.28（偏高）
  median  ：整数场景 0 vs 错1px 0（无判别力）
  trim30  ：去掉最差 30% 行后取均值。动态视频只占 ~17% 行，正好被裁掉

本脚本把打分函数接进完整的两段式搜索（粗搜 + 精修），跑全部场景，
输出：命中的 d、正确/错误代价比、无关两图的代价（拒识基准）。
"""
import numpy as np
from PIL import Image
import gen_samples as G
import stitcher as S
from test_subpixel2 import make_textured_content

COARSE = 4
TRIM_FRAC = 0.30
STD_FLOOR = 8.0


def downsample(g, s):
    h = g.shape[0] // s * s
    w = g.shape[1] // s * s
    return g[:h, :w].reshape(h // s, s, w // s, s).mean(axis=(1, 3))


def row_mads(A, B, d, top, bottom):
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 8:
        return None, None
    ys = np.arange(top, n_end)
    a = A[ys + d]
    b = B[ys]
    diff = np.abs(a - b)
    return diff.mean(axis=1), a


def score(A, B, d, top, bottom, kind):
    """返回代价（越小越好）；无法评估返回 None。"""
    rm, a = row_mads(A, B, d, top, bottom)
    if rm is None:
        return None
    sd = max(float(a.std()), STD_FLOOR)
    if kind == "frac":
        # 旧指标：整行完全匹配占比（返回 1-frac 使"越小越好"）
        H = A.shape[0]
        ys = np.arange(top, H - bottom - d)
        errs = np.abs(B[ys] - A[ys + d]).max(axis=1)
        return 1.0 - float((errs < 0.5).mean())
    if kind == "mean":
        return float(rm.mean()) / sd
    if kind == "median":
        return float(np.median(rm)) / sd
    if kind == "trim":
        n = rm.size
        k = int(n * TRIM_FRAC)
        if n - k < 8:
            return float(rm.mean()) / sd
        return float(np.sort(rm)[:n - k].mean()) / sd
    raise ValueError(kind)


def search(A, B, top, bottom, kind, min_scroll_frac=0.20):
    """两段式搜索，返回 (d, cost)。"""
    H = A.shape[0]
    min_overlap = max(24, int(0.06 * H))
    d_hi = H - bottom - min_overlap - top
    if d_hi <= 2:
        return None, None
    min_scroll = max(int(min_scroll_frac * (H - top - bottom)), 10)

    s = COARSE
    As, Bs = downsample(A, s), downsample(B, s)
    Hs = As.shape[0]
    tops, bots = top // s, bottom // s
    ds_hi = Hs - bots - max(6, min_overlap // s) - tops
    ds_lo = max(1, min_scroll // s)
    best_ds, best_c = None, None
    for d in range(ds_lo, ds_hi + 1):
        c = score(As, Bs, d, tops, bots, kind)
        if c is None:
            continue
        if best_c is None or c < best_c:
            best_c, best_ds = c, d
    if best_ds is None:
        return None, None

    lo = max(min_scroll, best_ds * s - 12)
    hi = min(d_hi, best_ds * s + 12)
    best_d, best_c = None, None
    for d in range(lo, hi + 1):
        c = score(A, B, d, top, bottom, kind)
        if c is None:
            continue
        if best_c is None or c < best_c:
            best_c, best_d = c, d
    return best_d, best_c


def make_shot_subpixel(content, scroll_y, kind, title):
    H = G.H
    y0 = int(np.floor(scroll_y))
    frac = scroll_y - y0
    t = content[y0:y0 + H].astype(np.float32)
    n = content[y0 + 1:y0 + 1 + H].astype(np.float32)
    if n.shape[0] < H:
        pad = np.repeat(content[-1:].astype(np.float32), H - n.shape[0], axis=0)
        n = np.concatenate([n, pad], axis=0)
    img = Image.fromarray(np.clip(t * (1 - frac) + n * frac + 0.5, 0, 255).astype(np.uint8))
    if kind == "textured":
        G.draw_status_bar(img, 0)
        G.draw_nav(img, "微信")
    G.draw_home_bar(img)
    return img


def build_cases():
    view_h = G.H - G.STATUS_H - G.NAV_H
    cases = []
    for name, kind, title in [("chat", "chat", "微信"), ("article", "article", "Safari"),
                              ("feed", "feed", "小红书"), ("list", "list", "设置")]:
        content = G.make_content(kind, seed=G.stable_seed(name))
        imgs = [G.make_screenshot(content, 0, kind, title=title)[0],
                G.make_screenshot(content, 1437, kind, title=title)[0]]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        cases.append((name, grays[0], grays[1], top, bottom, 1437))

    content = G.make_content("article", seed=G.stable_seed("dynamic"))
    imgs = [G.make_screenshot(content, 0, "article", dyn=0.0, title="B站")[0],
            G.make_screenshot(content, 1437, "article", dyn=0.5, title="B站")[0]]
    grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
    top, bottom = S.detect_overlays(grays)
    cases.append(("dynamic", grays[0], grays[1], top, bottom, 1437))

    tc = make_textured_content(seed=12345)
    for tail in (0.0, 0.25, 0.5, 0.75):
        s1 = 1437.0 + tail
        imgs = [make_shot_subpixel(tc, 0.0, "textured", "微信"),
                make_shot_subpixel(tc, s1, "textured", "微信")]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        cases.append((f"subpix{tail}", grays[0], grays[1], top, bottom, int(round(s1))))

    ca = G.make_content("chat", seed=G.stable_seed("chat"))
    cb = G.make_content("list", seed=G.stable_seed("list"))
    imgs = [G.make_screenshot(ca, 0, "chat", title="微信")[0],
            G.make_screenshot(cb, 0, "list", title="设置")[0]]
    grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
    top, bottom = S.detect_overlays(grays)
    cases.append(("UNRELATED", grays[0], grays[1], top, bottom, None))
    return cases


def main():
    cases = build_cases()
    kinds = ("frac", "mean", "median", "trim")
    print(f"{'case':>12} {'truth':>6} " + " ".join(f"{k:>22}" for k in kinds))
    print(f"{'':>12} {'':>6} " + " ".join(f"{'d / cost / ratio':>22}" for k in kinds))
    for (label, A, B, top, bottom, truth) in cases:
        cells = []
        for kind in kinds:
            d, c = search(A, B, top, bottom, kind)
            if d is None:
                cells.append("None")
                continue
            if truth is None:
                cells.append(f"d={d} c={c:.3f}")
            else:
                _, cw = search(A, B, top, bottom, kind)
                # 正确处与"错 1px"的比值：手动算错 1px 的代价
                c_wrong = score(A, B, truth + 1, top, bottom, kind)
                if c_wrong is None:
                    c_wrong = score(A, B, truth - 1, top, bottom, kind)
                hit = "OK" if abs(d - truth) <= 1 else "MISS"
                ratio = (c / c_wrong) if (c is not None and c_wrong) else float('nan')
                cells.append(f"{d}/{hit} c={c:.3f} r={ratio:.2f}")
        print(f"{label:>12} {str(truth):>6} " + " ".join(f"{x:>22}" for x in cells))


if __name__ == "__main__":
    main()
