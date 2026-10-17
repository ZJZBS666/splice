"""真·亚像素实验：滚动量落在 0.5 / 0.25 / 0.75 像素上。

上一次 test_mad.py 里 0.6237 * 2304 = 1437.005，其实几乎是整数，
所以"逐像素精确匹配"还能到 77.8%，结论偏乐观。

这里直接把滚动量构造成带小数尾巴的值，测量正确偏移处的逐行误差到底多大，
以及 mad_row（区域平均绝对差）这个指标是否仍然有判别力。

结论用于决定 Swift 版的主判别指标：
  A) 保持"精确匹配行占比 frac"（亚像素下会失效）
  B) 改用"平均绝对差 mad"，阈值化
  C) 两段式：先用 mad 找候选，再用 frac 精修
"""
import numpy as np
from PIL import Image
import gen_samples as G
import stitcher as S
from test_subpixel2 import make_textured_content


def make_shot(content, scroll_y):
    H = G.H
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


def stats(A, B, d, top, bottom):
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 8:
        return None
    ys = np.arange(top, n_end)
    diff = np.abs(B[ys] - A[ys + d])
    row_max = diff.max(axis=1)
    row_mad = diff.mean(axis=1)
    return {
        "frac": float((row_max < 0.5).mean()),
        "frac3": float((row_max < 3.0).mean()),
        "mad": float(row_mad.mean()),
        "mad_med": float(np.median(row_mad)),
    }


def main():
    content = make_textured_content(seed=12345)
    view_h = G.H - G.STATUS_H - G.NAV_H
    base = 1437.0

    for tail in (0.0, 0.25, 0.5, 0.75):
        scrolls = [0.0, base + tail, 2 * base + 2 * tail]
        imgs = [make_shot(content, s) for s in scrolls]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        A, B = grays[0], grays[1]
        d_true = int(round(scrolls[1]))

        print(f"\n===== fractional tail = {tail} =====")
        print(f"  top={top} bottom={bottom} d_true={d_true} "
              f"(actual {scrolls[1]:.3f})")
        print(f"  {'d':>6} {'frac':>7} {'frac3':>7} {'mad':>8} {'mad_med':>8}")
        for delta in (0, 1, -1, 2, -2, 4, -4):
            d = d_true + delta
            st = stats(A, B, d, top, bottom)
            if st is None:
                continue
            mark = "  <== correct" if delta == 0 else ""
            print(f"  {d:>6} {st['frac']:>7.3f} {st['frac3']:>7.3f} "
                  f"{st['mad']:>8.3f} {st['mad_med']:>8.3f}{mark}")

        # 用 mad 做判别：取 mad 最小的 d，看是否命中
        cands = []
        for d in range(d_true - 6, d_true + 7):
            st = stats(A, B, d, top, bottom)
            if st is not None:
                cands.append((st["mad"], d))
        cands.sort()
        print(f"  argmin(mad) = {cands[0][1]} (mad={cands[0][0]:.3f})  "
              f"-> {'HIT' if cands[0][1] == d_true else 'MISS'}")
        cands2 = sorted((st["frac"], d) for st in
                        [stats(A, B, d, top, bottom) for d in range(d_true - 6, d_true + 7)]
                        if st is not None)
        print(f"  argmax(frac) = {cands2[-1][1]} (frac={cands2[-1][0]:.3f})  "
              f"-> {'HIT' if cands2[-1][1] == d_true else 'MISS'}")


if __name__ == "__main__":
    main()
