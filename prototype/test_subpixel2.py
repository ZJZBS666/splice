"""真机风险实验：亚像素滚动 —— 严苛版（纹理内容）。

上一版 test_subpixel.py 用的大片纯色气泡，双线性插值后仍是同一个颜色，
所以 eps=0.5 也能匹配上，结论偏乐观。

真机上文字密集的页面（微信聊天、Safari 文章）几乎每一行都有笔画边缘，
亚像素重采样会让整行像素值都变，逐像素精确匹配会彻底失效。

这个脚本用"每行都有高频纹理"的内容重测，测出：
  1. 亚像素重采样后，正确偏移处的逐行误差到底有多大（决定 eps 该取多少）
  2. 各 eps 档位还能不能命中正确偏移
"""
import numpy as np
from PIL import Image, ImageDraw
import gen_samples as G
import stitcher as S


def make_textured_content(seed, height=14000):
    """每行都有高频纹理的内容：细密横线 + 竖线 + 随机噪点，模拟文字密集页面。"""
    rng = np.random.default_rng(seed)
    W = G.W
    img = np.full((height, W, 3), 250, dtype=np.uint8)
    # 细密横线（模拟一行行文字）
    for y in range(0, height, 9):
        img[y:y + 3, 40:W - 40] = 40
    # 竖直分隔
    for x in range(60, W - 60, 70):
        img[:, x:x + 2] = 90
    # 高频噪点
    noise = rng.integers(-30, 30, size=(height, W, 1), dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return img


def make_shot(content, scroll_y):
    """按小数 scroll_y 双线性重采样出一屏，再画固定覆盖层。"""
    H, W = G.H, G.W
    y0 = int(np.floor(scroll_y))
    frac = scroll_y - y0
    top = content[y0:y0 + H].astype(np.float32)
    nxt = content[y0 + 1:y0 + 1 + H].astype(np.float32)
    if nxt.shape[0] < H:
        pad = np.repeat(content[-1:].astype(np.float32), H - nxt.shape[0], axis=0)
        nxt = np.concatenate([nxt, pad], axis=0)
    blended = top * (1.0 - frac) + nxt * frac
    img = Image.fromarray(np.clip(blended + 0.5, 0, 255).astype(np.uint8))
    G.draw_status_bar(img, 0)
    G.draw_nav(img, "微信")
    G.draw_home_bar(img)
    return img


def measure_row_errors(grays, top, bottom, d_true):
    """正确偏移处，逐行最大差 errs 的分布。"""
    A, B = grays[0], grays[1]
    H = A.shape[0]
    ys = np.arange(top, H - bottom - d_true)
    errs = np.abs(B[ys] - A[ys + d_true]).max(axis=1)
    return errs


def main():
    content = make_textured_content(seed=12345)
    view_h = G.H - G.STATUS_H - G.NAV_H

    cases = {
        "integer":  [0.62, 0.71, 0.66],
        "half":     [0.6237, 0.7133, 0.6651],
        "quarter":  [0.6201, 0.7102, 0.6603],
    }

    for label, fracs in cases.items():
        scrolls = [0.0]
        for f in fracs:
            scrolls.append(scrolls[-1] + f * view_h)
        imgs = [make_shot(content, s) for s in scrolls]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        truth = [int(round(scrolls[i + 1] - scrolls[i])) for i in range(len(scrolls) - 1)]

        print(f"\n== {label} ==  top={top} bottom={bottom}  truth={truth}")
        # 正确偏移处的逐行误差分布
        errs = measure_row_errors(grays, top, bottom, truth[0])
        print(f"   row errs @correct d: mean={errs.mean():.1f} "
              f"median={np.median(errs):.1f} p90={np.percentile(errs, 90):.1f} "
              f"max={errs.max():.1f}")
        print(f"   rows with err<0.5: {(errs < 0.5).mean()*100:.1f}%   "
              f"err<3: {(errs < 3).mean()*100:.1f}%   "
              f"err<12: {(errs < 12).mean()*100:.1f}%   "
              f"err<30: {(errs < 30).mean()*100:.1f}%")

        for eps in (0.5, 3.0, 6.0, 12.0, 20.0, 30.0, 45.0):
            got, fr = [], []
            for i in range(len(grays) - 1):
                d, f = S.find_offset_eps(grays[i], grays[i + 1], top, bottom, eps)
                got.append(d)
                fr.append(round(f, 3))
            hit = sum(1 for a, b in zip(got, truth) if a is not None and abs(a - b) <= 2)
            print(f"   eps={eps:>5}  d={got}  frac={fr}  hit={hit}/{len(truth)}")

        # 默认 find_offset（严格 -> 宽容 两档）
        got, fr = [], []
        for i in range(len(grays) - 1):
            d, f = S.find_offset(grays[i], grays[i + 1], top, bottom)
            got.append(d)
            fr.append(round(f, 3))
        hit = sum(1 for a, b in zip(got, truth) if a is not None and abs(a - b) <= 2)
        print(f"   find_offset()   d={got}  frac={fr}  hit={hit}/{len(truth)}")


if __name__ == "__main__":
    main()
