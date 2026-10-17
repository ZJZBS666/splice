"""关键实验：只对"有纹理的行"打分（texture-masked mean）。

问题链条（前面几步已证）：
  1. 亚像素滚动 -> "整行完全匹配占比 frac" 恒为 0，失效
  2. 改用行均差的平均值 mad -> 亚像素下有判别力，但会被动态视频(21%行)抬高
  3. 改用截尾均值 trim -> 在纯色多的页面上退化成 0，因为纯色行在任何偏移都相同

根因：**纯色行不含信息，任何偏移都能"匹配"**，它们只会稀释判别力。
所以只统计"行内有纹理"（行内灰度标准差够大）的行。

本脚本测：
  - 5 个合成场景（整数滚动，含纯色气泡的 chat）
  - 非周期纹理 + 亚像素（0/0.25/0.5/0.75）
  - 动态视频场景
  - 无关两图（拒识基准）
指标：score = mean(rowMAD over textured rows) / 全局std
输出：正确 d 处的 score、错 1/2px 处的 score、比值，以及无关图的 score。
"""
import numpy as np
from PIL import Image
import gen_samples as G
import stitcher as S


TEXTURE_MIN = 3.0    # 行内灰度标准差 >= 它才算"有纹理的行"


def make_irregular_content(seed, height=14000):
    rng = np.random.default_rng(seed)
    W = G.W
    img = np.full((height, W, 3), 248, dtype=np.uint8)
    y = 30
    while y < height - 20:
        line_h = int(rng.integers(2, 5))
        x0 = int(rng.integers(30, 120))
        x1 = int(rng.integers(W - 260, W - 30))
        img[y:y + line_h, x0:x1] = int(rng.integers(20, 70))
        y += int(rng.integers(6, 22))
    for _ in range(40):
        x = int(rng.integers(30, W - 30))
        h = int(rng.integers(200, 900))
        y0 = int(rng.integers(0, height - h))
        img[y0:y0 + h, x:x + int(rng.integers(2, 6))] = int(rng.integers(60, 140))
    noise = rng.integers(-18, 18, size=(height, W, 1), dtype=np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def make_shot(content, scroll_y, draw_overlays=True):
    H = G.H
    y0 = int(np.floor(scroll_y))
    frac = scroll_y - y0
    t = content[y0:y0 + H].astype(np.float32)
    n = content[y0 + 1:y0 + 1 + H].astype(np.float32)
    if n.shape[0] < H:
        pad = np.repeat(content[-1:].astype(np.float32), H - n.shape[0], axis=0)
        n = np.concatenate([n, pad], axis=0)
    img = Image.fromarray(np.clip(t * (1 - frac) + n * frac + 0.5, 0, 255).astype(np.uint8))
    if draw_overlays:
        G.draw_status_bar(img, 0)
        G.draw_nav(img, "微信")
        G.draw_home_bar(img)
    return img


def texture_masked_cost(A, B, d, top, bottom, texture_min=TEXTURE_MIN):
    """只统计有纹理的行。返回 (cost, textured_row_count)。"""
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 8:
        return None, 0
    ys = np.arange(top, n_end)
    a = A[ys + d]
    b = B[ys]
    # 行内纹理度：用 A 的行标准差衡量（A 是参考图，纹理是内容属性）
    row_sd = a.std(axis=1)
    tex = row_sd >= texture_min
    ntex = int(tex.sum())
    if ntex < 20:
        return None, ntex
    rm = np.abs(a - b).mean(axis=1)
    sd = max(float(a.std()), 8.0)
    return float(rm[tex].mean()) / sd, ntex


def global_search(A, B, top, bottom, texture_min=TEXTURE_MIN):
    H = A.shape[0]
    min_scroll = max(int(0.20 * (H - top - bottom)), 10)
    d_hi = H - bottom - max(24, int(0.06 * H)) - top
    best_d, best_c = None, None
    costs = []
    for d in range(min_scroll, d_hi + 1):
        c, ntex = texture_masked_cost(A, B, d, top, bottom, texture_min)
        if c is None:
            continue
        costs.append(c)
        if best_c is None or c < best_c:
            best_c, best_d = c, d
    med = float(np.median(costs)) if costs else 1.0
    return best_d, best_c, med


def build_cases():
    cases = []
    for name, kind, title in [("chat", "chat", "微信"), ("article", "article", "Safari"),
                              ("feed", "feed", "小红书"), ("list", "list", "设置")]:
        content = G.make_content(kind, seed=G.stable_seed(name))
        imgs = [G.make_screenshot(content, 0, kind, title=title)[0],
                G.make_screenshot(content, 1437, kind, title=title)[0]]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        cases.append((f"{name}", grays[0], grays[1], top, bottom, 1437))

    content = G.make_content("article", seed=G.stable_seed("dynamic"))
    imgs = [G.make_screenshot(content, 0, "article", dyn=0.0, title="B站")[0],
            G.make_screenshot(content, 1437, "article", dyn=0.5, title="B站")[0]]
    grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
    top, bottom = S.detect_overlays(grays)
    cases.append(("dynamic", grays[0], grays[1], top, bottom, 1437))

    for seed in (777, 888):
        tc = make_irregular_content(seed=seed)
        for tail in (0.0, 0.25, 0.5, 0.75):
            s1 = 1437.0 + tail
            imgs = [make_shot(tc, 0.0), make_shot(tc, s1)]
            grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
            top, bottom = S.detect_overlays(grays)
            cases.append((f"irr{seed}+{tail}", grays[0], grays[1], top, bottom,
                          int(round(s1))))

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
    print(f"{'case':>14} {'truth':>6} {'argmin':>7} {'cost':>7} {'c+1':>7} {'c+2':>7} "
          f"{'r1':>6} {'r2':>6} {'peak':>6} {'tex_rows':>8}")
    for (label, A, B, top, bottom, truth) in cases:
        d, c, med = global_search(A, B, top, bottom)
        c1, _ = texture_masked_cost(A, B, (truth or d) + 1, top, bottom)
        c2, _ = texture_masked_cost(A, B, (truth or d) + 2, top, bottom)
        _, ntex = texture_masked_cost(A, B, truth if truth else d, top, bottom)
        r1 = (c / c1) if (c and c1) else float('nan')
        r2 = (c / c2) if (c and c2) else float('nan')
        hit = ""
        if truth is not None:
            hit = "OK" if d is not None and abs(d - truth) <= 1 else "MISS"
        print(f"{label:>14} {str(truth):>6} {str(d):>7} {c:>7.4f} "
              f"{(c1 if c1 else 0):>7.4f} {(c2 if c2 else 0):>7.4f} "
              f"{r1:>6.3f} {r2:>6.3f} {c/med:>6.3f} {ntex:>8} {hit}")


if __name__ == "__main__":
    main()
