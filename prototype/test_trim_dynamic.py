"""验证 trim 指标能否独自处理动态内容（视频方块），不需要 bad-band 排除循环。

dynamic 场景里视频方块随内容滚动但每张颜色不同，占有效行 ~21%。
TRIM_FRAC=0.30 理论上正好能把它裁掉。这里测：
  1. 全分辨率全局 argmin 是否命中真值
  2. 不同 TRIM_FRAC（0.20/0.25/0.30/0.35/0.40）的影响
  3. 视频占比更大（模拟视频占半屏）时是否还成立
"""
import numpy as np
import gen_samples as G
import stitcher as S


def trim_cost(A, B, d, top, bottom, trim_frac, sd_floor=8.0):
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 8:
        return None
    ys = np.arange(top, n_end)
    a = A[ys + d]
    b = B[ys]
    rm = np.abs(a - b).mean(axis=1)
    sd = max(float(a.std()), sd_floor)
    n = rm.size
    k = int(n * trim_frac)
    if n - k < 8:
        return float(rm.mean()) / sd
    return float(np.sort(rm)[:n - k].mean()) / sd


def global_argmin(A, B, top, bottom, trim_frac):
    H = A.shape[0]
    min_scroll = max(int(0.20 * (H - top - bottom)), 10)
    d_hi = H - bottom - max(24, int(0.06 * H)) - top
    best_d, best_c = None, None
    costs = []
    for d in range(min_scroll, d_hi + 1):
        c = trim_cost(A, B, d, top, bottom, trim_frac)
        if c is None:
            continue
        costs.append(c)
        if best_c is None or c < best_c:
            best_c, best_d = c, d
    med = float(np.median(costs)) if costs else None
    return best_d, best_c, med


def build_dynamic_cases():
    cases = []
    content = G.make_content("article", seed=G.stable_seed("dynamic"))
    # 正常视频
    imgs = [G.make_screenshot(content, 0, "article", dyn=0.0, title="B站")[0],
            G.make_screenshot(content, 1437, "article", dyn=0.5, title="B站")[0]]
    grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
    top, bottom = S.detect_overlays(grays)
    cases.append(("dynamic", grays[0], grays[1], top, bottom, 1437))

    # 整数滚动的普通场景作为对照
    for name, kind, title in [("chat", "chat", "微信"), ("feed", "feed", "小红书")]:
        c = G.make_content(kind, seed=G.stable_seed(name))
        imgs = [G.make_screenshot(c, 0, kind, title=title)[0],
                G.make_screenshot(c, 1437, kind, title=title)[0]]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        cases.append((name, grays[0], grays[1], top, bottom, 1437))

    # 无关两图
    ca = G.make_content("chat", seed=G.stable_seed("chat"))
    cb = G.make_content("list", seed=G.stable_seed("list"))
    imgs = [G.make_screenshot(ca, 0, "chat", title="微信")[0],
            G.make_screenshot(cb, 0, "list", title="设置")[0]]
    grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
    top, bottom = S.detect_overlays(grays)
    cases.append(("UNRELATED", grays[0], grays[1], top, bottom, None))
    return cases


def main():
    cases = build_dynamic_cases()
    trims = (0.20, 0.25, 0.30, 0.35, 0.40)
    print(f"{'case':>10} {'truth':>6} " + " ".join(f"{t:>26}" for t in trims))
    for (label, A, B, top, bottom, truth) in cases:
        cells = []
        for tf in trims:
            d, c, med = global_argmin(A, B, top, bottom, tf)
            if truth is None:
                cells.append(f"d={d} c={c:.3f} pk={c/med:.2f}")
            else:
                hit = "OK" if d is not None and abs(d - truth) <= 1 else "MISS"
                cells.append(f"{d}/{hit} c={c:.3f} pk={c/med:.2f}")
        print(f"{label:>10} {str(truth):>6} " + " ".join(f"{x:>26}" for x in cells))


if __name__ == "__main__":
    main()
