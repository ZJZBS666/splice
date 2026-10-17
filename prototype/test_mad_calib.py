"""标定 mad 指标的阈值。

背景（见 test_subpixel3.py 的结论）：
  真机滚动停在非整数像素位置时 iOS 会重采样，同一内容行在两图的像素值差 1~100，
  "整行完全匹配占比 frac" 在亚像素下恒为 0，彻底失效。
  而"区域平均绝对差 mad" 在正确偏移处明显最小，可以作为主判别指标。

这个脚本要回答三个问题：
  1. mad 在不同内容（纯色多 / 文字密）下的量级差多少 -> 是否必须归一化
  2. 正确偏移的 mad 与"错 1px / 2px / 3px"的 mad 相差多少倍 -> 相对判据的阈值
  3. 两张完全无关的截图，mad 是多少 -> 拒识阈值

归一化方式：rel = mad / (A 在有效区域内的灰度标准差)
  这样纯白页面（std 小）和文字页面（std 大）可以共用同一个阈值。
"""
import numpy as np
from PIL import Image
import gen_samples as G
import stitcher as S
from test_subpixel2 import make_textured_content


def make_shot(content, scroll_y, kind, title):
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
    if kind == "textured":
        G.draw_status_bar(img, 0)
        G.draw_nav(img, "微信")
    else:
        G.draw_status_bar(img, 0)
        G.draw_nav(img, title)
    G.draw_home_bar(img)
    return img


def cost_at(A, B, d, top, bottom):
    """返回 (rel_cost, frac_exact, match_rows)。"""
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 8:
        return None
    ys = np.arange(top, n_end)
    a = A[ys + d]
    b = B[ys]
    diff = np.abs(a - b)
    row_mad = diff.mean(axis=1)
    row_max = diff.max(axis=1)
    sd = float(a.std())
    if sd < 1e-3:
        sd = 1e-3
    return (float(row_mad.mean()) / sd,
            float((row_max < 0.5).mean()),
            int((row_max < 0.5).sum()))


def report(label, A, B, top, bottom, d_true):
    print(f"\n== {label} ==  d_true={d_true}")
    print(f"   {'d':>6} {'rel_cost':>9} {'frac':>7} {'match_rows':>10}")
    base = None
    for delta in (0, 1, -1, 2, -2, 3, -3, 6):
        d = d_true + delta
        c = cost_at(A, B, d, top, bottom)
        if c is None:
            continue
        if delta == 0:
            base = c[0]
        mark = "  <== correct" if delta == 0 else ""
        print(f"   {d:>6} {c[0]:>9.4f} {c[1]:>7.3f} {c[2]:>10}{mark}")
    # 正确处与错 1px 的比值
    c1 = cost_at(A, B, d_true + 1, top, bottom)
    c2 = cost_at(A, B, d_true + 2, top, bottom)
    if base and c1 and c2:
        print(f"   ratio correct/wrong1 = {base/c1[0]:.3f}   "
              f"correct/wrong2 = {base/c2[0]:.3f}")


def main():
    view_h = G.H - G.STATUS_H - G.NAV_H
    cases = []

    # 1) 5 个合成场景，整数滚动
    for name, kind, title in [("chat", "chat", "微信"), ("article", "article", "Safari"),
                              ("feed", "feed", "小红书"), ("list", "list", "设置"),
                              ("dynamic", "article", "B站")]:
        content = G.make_content(kind, seed=G.stable_seed(name))
        s0, s1 = 0.0, 1437.0
        imgs = [make_shot(content, s0, kind, title), make_shot(content, s1, kind, title)]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        cases.append((f"{name}(int)", grays[0], grays[1], top, bottom, 1437))

    # 2) 纹理内容，整数 + 三种小数尾巴
    tc = make_textured_content(seed=12345)
    for tail in (0.0, 0.25, 0.5, 0.75):
        s0, s1 = 0.0, 1437.0 + tail
        imgs = [make_shot(tc, s0, "textured", "微信"), make_shot(tc, s1, "textured", "微信")]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        cases.append((f"textured(tail={tail})", grays[0], grays[1], top, bottom,
                      int(round(s1))))

    # 3) 完全无关的两张（拒识基准）
    ca = G.make_content("chat", seed=G.stable_seed("chat"))
    cb = G.make_content("list", seed=G.stable_seed("list"))
    imgs = [make_shot(ca, 0.0, "chat", "微信"), make_shot(cb, 0.0, "list", "设置")]
    grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
    top, bottom = S.detect_overlays(grays)
    cases.append(("UNRELATED", grays[0], grays[1], top, bottom, 1437))

    for (label, A, B, top, bottom, d_true) in cases:
        report(label, A, B, top, bottom, d_true)


if __name__ == "__main__":
    main()
