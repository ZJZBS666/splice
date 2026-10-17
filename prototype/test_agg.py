"""确定 mad 的聚合方式：mean / median / trimmed-mean 哪个在动态内容下仍稳。

前一步已确认：亚像素滚动下 "精确匹配行占比 frac" 恒为 0（失效），
而 "逐行平均绝对差的区域平均 mad" 有判别力。

但 dynamic 场景里有视频方块（占 ~17% 行，每张颜色都不同），
那部分行的误差恒为 ~255，会把"平均值"整体抬高，淹没真实信号。
这个脚本对比三种聚合方式在 6 种场景下的判别力。

判别力指标：correct 值 / 最接近的错误偏移值（越小越有判别力），
同时看 unrelated（无关两图）的最小值，作为拒识基准。
"""
import numpy as np
from PIL import Image
import gen_samples as G
import stitcher as S
from test_subpixel2 import make_textured_content


def make_shot(content, scroll_y, kind, title, dyn=None):
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
        # 复用 gen_samples 的覆盖层绘制（含 dynamic 的视频方块）
        return G.make_screenshot(content, int(round(scroll_y)), kind, dyn=dyn, title=title)[0]
    G.draw_home_bar(img)
    return img


def costs(A, B, d, top, bottom):
    """返回三种聚合的归一化代价，以及精确匹配行占比。"""
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
    sd = max(float(a.std()), 1.0)
    n = row_mad.size
    k = int(n * 0.30)
    trimmed = float(np.sort(row_mad)[:n - k].mean()) if n - k > 8 else float(row_mad.mean())
    return {
        "mean": float(row_mad.mean()) / sd,
        "median": float(np.median(row_mad)) / sd,
        "trim": trimmed / sd,
        "frac": float((row_max < 0.5).mean()),
    }


def build_cases():
    view_h = G.H - G.STATUS_H - G.NAV_H
    cases = []

    # 5 个合成场景（整数滚动）
    for name, kind, title in [("chat", "chat", "微信"), ("article", "article", "Safari"),
                              ("feed", "feed", "小红书"), ("list", "list", "设置")]:
        content = G.make_content(kind, seed=G.stable_seed(name))
        imgs = [G.make_screenshot(content, 0, kind, title=title)[0],
                G.make_screenshot(content, 1437, kind, title=title)[0]]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        cases.append((f"{name}", grays[0], grays[1], top, bottom, 1437))

    # dynamic：视频随内容滚动，每张颜色不同
    content = G.make_content("article", seed=G.stable_seed("dynamic"))
    imgs = [G.make_screenshot(content, 0, "article", dyn=0.0, title="B站")[0],
            G.make_screenshot(content, 1437, "article", dyn=0.25, title="B站")[0]]
    grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
    top, bottom = S.detect_overlays(grays)
    cases.append(("dynamic", grays[0], grays[1], top, bottom, 1437))

    # 纹理内容 + 亚像素
    tc = make_textured_content(seed=12345)
    for tail in (0.0, 0.25, 0.5, 0.75):
        s1 = 1437.0 + tail
        imgs = [make_shot(tc, 0.0, "textured", "微信"),
                make_shot(tc, s1, "textured", "微信")]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        cases.append((f"subpix{tail}", grays[0], grays[1], top, bottom, int(round(s1))))

    # 无关两图（拒识基准）
    ca = G.make_content("chat", seed=G.stable_seed("chat"))
    cb = G.make_content("list", seed=G.stable_seed("list"))
    imgs = [G.make_screenshot(ca, 0, "chat", title="微信")[0],
            G.make_screenshot(cb, 0, "list", title="设置")[0]]
    grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
    top, bottom = S.detect_overlays(grays)
    cases.append(("UNRELATED", grays[0], grays[1], top, bottom, 1437))
    return cases


def main():
    cases = build_cases()
    keys = ("mean", "median", "trim")
    print(f"{'case':>12} {'key':>7} {'correct':>9} {'wrong1':>9} {'wrong2':>9} "
          f"{'ratio1':>7} {'ratio2':>7}")
    summary = {k: [] for k in keys}
    for (label, A, B, top, bottom, d_true) in cases:
        row = {}
        for key in keys:
            c0 = costs(A, B, d_true, top, bottom)
            c1 = costs(A, B, d_true + 1, top, bottom)
            c2 = costs(A, B, d_true + 2, top, bottom)
            if not (c0 and c1 and c2):
                continue
            v0, v1, v2 = c0[key], c1[key], c2[key]
            r1 = v0 / v1 if v1 > 1e-9 else 0.0
            r2 = v0 / v2 if v2 > 1e-9 else 0.0
            print(f"{label:>12} {key:>7} {v0:>9.4f} {v1:>9.4f} {v2:>9.4f} "
                  f"{r1:>7.3f} {r2:>7.3f}")
            row[key] = (v0, r1, r2)
        for key in keys:
            if key in row:
                summary[key].append((label, row[key]))

    print("\n---- 判别力总结（ratio1 = correct/wrong1，越小越好）----")
    for key in keys:
        vals = [(lab, v[1]) for (lab, v) in summary[key]]
        worst = max(vals, key=lambda t: t[1])
        print(f"{key:>7}: ratio1 范围 {min(v for _, v in vals):.3f} ~ "
              f"{max(v for _, v in vals):.3f}   最差: {worst[0]} ({worst[1]:.3f})")

    print("\n---- 拒识基准：无关两图在正确 d 处的代价（越小越容易误判）----")
    for key in keys:
        for (lab, v) in summary[key]:
            if lab == "UNRELATED":
                print(f"{key:>7}: {v[0]:.4f}")


if __name__ == "__main__":
    main()
