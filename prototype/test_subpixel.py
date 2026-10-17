"""真机风险实验：亚像素滚动。

合成样本里滚动量都是整数像素，所以相邻截图内容逐像素完全相同。
真机上 UIScrollView 滚动带惯性，停下来的位置是**小数**像素；
iOS 截图时会把内容按这个小数偏移重采样（双线性插值），
于是"同一行内容"在两张截图里的像素值会差 1~60，逐像素精确匹配全部失效。

这个脚本生成亚像素滚动的截图，测三种 eps 下 find_offset 还能不能命中。

用法：
    python test_subpixel.py
输出：每个场景每种 eps 的 d / frac / 是否命中真值。
"""
import numpy as np
from PIL import Image
import gen_samples as G
import stitcher as S


def make_shot_subpixel(content, scroll_y, kind, title, dyn=None):
    """按小数 scroll_y 从 content 重采样出一屏（模拟 iOS 双线性插值滚动）。"""
    H, W = G.H, G.W
    y0 = int(np.floor(scroll_y))
    frac = scroll_y - y0
    # 多取一行，用线性插值合成
    top = content[y0:y0 + H].astype(np.float32)
    nxt = content[y0 + 1:y0 + 1 + H].astype(np.float32)
    if nxt.shape[0] < H:
        pad = np.repeat(content[-1:].astype(np.float32), H - nxt.shape[0], axis=0)
        nxt = np.concatenate([nxt, pad], axis=0)
    blended = (top * (1.0 - frac) + nxt * frac)
    img = Image.fromarray(np.clip(blended + 0.5, 0, 255).astype(np.uint8))
    # 覆盖层是屏幕固定元素，不受滚动影响，必须重新画（不插值）
    if kind == "chat":
        G.draw_status_bar(img, 0)
        G.draw_nav(img, title)
    elif kind == "article":
        G.draw_status_bar(img, 0)
        G.draw_nav(img, title)
    elif kind == "feed":
        G.draw_status_bar(img, 0)
        G.draw_nav(img, title)
    elif kind == "list":
        G.draw_status_bar(img, 0)
        G.draw_nav(img, title)
    G.draw_home_bar(img)
    return img


def run_case(name, kind, title, fracs, eps_list):
    content = G.make_content(kind, seed=G.stable_seed(name))
    view_h = G.H - G.STATUS_H - G.NAV_H
    scrolls = [0.0]
    for f in fracs:
        scrolls.append(scrolls[-1] + f * view_h)

    imgs = [make_shot_subpixel(content, s, kind, title) for s in scrolls]
    rgbs = [np.asarray(im.convert("RGB")) for im in imgs]
    grays = [S.to_gray(r) for r in rgbs]
    top, bottom = S.detect_overlays(grays)
    truth = [int(round(scrolls[i + 1] - scrolls[i])) for i in range(len(scrolls) - 1)]

    print(f"\n== {name} == top={top} bottom={bottom}")
    print(f"   truth d = {truth}   (fractional: "
          f"{[round(scrolls[i+1]-scrolls[i], 2) for i in range(len(scrolls)-1)]})")
    for eps in eps_list:
        got = []
        fr = []
        for i in range(len(grays) - 1):
            d, f = S.find_offset_eps(grays[i], grays[i + 1], top, bottom, eps)
            got.append(d)
            fr.append(round(f, 3))
        hit = sum(1 for a, b in zip(got, truth) if a is not None and abs(a - b) <= 2)
        print(f"   eps={eps:>4}  d={got}  frac={fr}  hit={hit}/{len(truth)}")


def main():
    eps_list = [0.5, 3.0, 6.0, 12.0, 20.0]
    # 全整数（对照组）
    run_case("chat_int", "chat", "微信", [0.62, 0.71, 0.66], eps_list)
    # 全部 .5 像素
    run_case("chat_half", "chat", "微信", [0.6237, 0.7133, 0.6651], eps_list)
    # 接近整数的微小亚像素（0.15）
    run_case("chat_tiny", "chat", "微信", [0.6201, 0.7102, 0.6603], eps_list)


if __name__ == "__main__":
    main()
