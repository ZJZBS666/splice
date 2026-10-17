"""决定性实验：texture-masked + 截尾平均，能否同时扛住「亚像素」和「有纹理的视频」。

前面已证：
  - frac（整行完全匹配占比）在亚像素滚动下恒为 0 -> 废弃
  - texture-masked 均值：亚像素正确处 0.10~0.21，错 1px 0.32~0.56，无关两图 0.52
    但 dynamic 场景之所以能做到 0.0000，是因为合成"视频"是纯色方块（低纹理被排除）。
    真实视频是**有纹理**的，不会被纹理掩码排除。

本脚本加入"有纹理的视频"（高频噪点方块，每张内容完全不同，占 ~21% 行），
测两种聚合：
  A) 纹理行的普通均值
  B) 纹理行去掉最差 25% 后的均值（截尾）
结论用于确定 Swift 的最终打分函数。
"""
import numpy as np
from PIL import Image, ImageDraw
import gen_samples as G
import stitcher as S


TEXTURE_MIN = 3.0
TRIM_FRAC = 0.25
SD_FLOOR = 8.0


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


def make_textured_video(seed, w=1000, h=550):
    """有纹理的"视频画面"：高频噪点 + 彩色块，每帧完全不同。"""
    rng = np.random.default_rng(seed)
    v = rng.integers(0, 255, size=(h, w, 3), dtype=np.uint8)
    # 加一些大色块，让它像真实画面而不是纯噪点
    for _ in range(8):
        y0 = int(rng.integers(0, h - 60))
        x0 = int(rng.integers(0, w - 60))
        v[y0:y0 + int(rng.integers(30, 120)), x0:x0 + int(rng.integers(30, 160))] = \
            rng.integers(0, 255, size=3)
    return v


def make_shot_with_video(content, scroll_y, video_img, video_abs_y, video_h, video_w):
    """截图 = 内容（小数滚动重采样）+ 有纹理视频贴在滚动位置 + 覆盖层。"""
    H = G.H
    y0 = int(np.floor(scroll_y))
    frac = scroll_y - y0
    t = content[y0:y0 + H].astype(np.float32)
    n = content[y0 + 1:y0 + 1 + H].astype(np.float32)
    if n.shape[0] < H:
        pad = np.repeat(content[-1:].astype(np.float32), H - n.shape[0], axis=0)
        n = np.concatenate([n, pad], axis=0)
    arr = np.clip(t * (1 - frac) + n * frac + 0.5, 0, 255).astype(np.uint8)

    # 视频的视口坐标 = 顶部覆盖层 + (绝对 y - 滚动量)
    vy = G.STATUS_H + G.NAV_H + int(video_abs_y - scroll_y)
    vx = (G.W - video_w) // 2
    y_start = max(0, vy)
    y_end = min(H, vy + video_h)
    if y_end > y_start:
        src_y0 = y_start - vy
        arr[y_start:y_end, vx:vx + video_w] = video_img[src_y0:src_y0 + (y_end - y_start)]

    img = Image.fromarray(arr)
    G.draw_status_bar(img, 0)
    G.draw_nav(img, "B站")
    G.draw_home_bar(img)
    return img


def row_costs(A, B, d, top, bottom):
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 8:
        return None, None, None
    ys = np.arange(top, n_end)
    a = A[ys + d]
    b = B[ys]
    row_sd = a.std(axis=1)
    tex = row_sd >= TEXTURE_MIN
    if int(tex.sum()) < 20:
        return None, None, None
    rm = np.abs(a - b).mean(axis=1)
    sd = max(float(a.std()), SD_FLOOR)
    tex_rm = rm[tex] / sd
    n = tex_rm.size
    k = int(n * TRIM_FRAC)
    trimmed = float(np.sort(tex_rm)[:n - k].mean()) if n - k >= 8 else float(tex_rm.mean())
    return float(tex_rm.mean()), trimmed, int(tex.sum())


def global_search(A, B, top, bottom, mode):
    H = A.shape[0]
    min_scroll = max(int(0.20 * (H - top - bottom)), 10)
    d_hi = H - bottom - max(24, int(0.06 * H)) - top
    idx = 0 if mode == "mean" else 1
    best_d, best_c = None, None
    costs = []
    for d in range(min_scroll, d_hi + 1):
        vals = row_costs(A, B, d, top, bottom)
        if vals[0] is None:
            continue
        c = vals[idx]
        costs.append(c)
        if best_c is None or c < best_c:
            best_c, best_d = c, d
    med = float(np.median(costs)) if costs else 1.0
    return best_d, best_c, med


def build_cases():
    cases = []
    # 有纹理视频 + 亚像素滚动
    tc = make_irregular_content(seed=777)
    for i, tail in enumerate((0.0, 0.25, 0.5, 0.75)):
        v0 = make_textured_video(seed=100 + i)
        v1 = make_textured_video(seed=200 + i)
        s0, s1 = 0.0, 1437.0 + tail
        imgs = [make_shot_with_video(tc, s0, v0, 2600, 550, 1000),
                make_shot_with_video(tc, s1, v1, 2600, 550, 1000)]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        cases.append((f"video+{tail}", grays[0], grays[1], top, bottom, int(round(s1))))

    # 无视频的亚像素对照
    for tail in (0.0, 0.5):
        s1 = 1437.0 + tail
        imgs = []
        for s in (0.0, s1):
            H = G.H
            y0 = int(np.floor(s))
            fr = s - y0
            t = tc[y0:y0 + H].astype(np.float32)
            n = tc[y0 + 1:y0 + 1 + H].astype(np.float32)
            if n.shape[0] < H:
                pad = np.repeat(tc[-1:].astype(np.float32), H - n.shape[0], axis=0)
                n = np.concatenate([n, pad], axis=0)
            im = Image.fromarray(np.clip(t * (1 - fr) + n * fr + 0.5, 0, 255).astype(np.uint8))
            G.draw_status_bar(im, 0)
            G.draw_nav(im, "微信")
            G.draw_home_bar(im)
            imgs.append(im)
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        cases.append((f"plain+{tail}", grays[0], grays[1], top, bottom, int(round(s1))))

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
    cases = build_cases()
    for mode in ("mean", "trim"):
        print(f"\n===== aggregation = {mode} =====")
        print(f"{'case':>12} {'truth':>6} {'argmin':>7} {'cost':>7} {'c+1':>7} "
              f"{'r1':>6} {'peak':>6} {'hit':>5}")
        for (label, A, B, top, bottom, truth) in cases:
            d, c, med = global_search(A, B, top, bottom, mode)
            idx = 0 if mode == "mean" else 1
            ref = truth if truth is not None else d
            c1 = row_costs(A, B, ref + 1, top, bottom)[idx]
            r1 = (c / c1) if (c and c1) else float('nan')
            hit = ""
            if truth is not None:
                hit = "OK" if d is not None and abs(d - truth) <= 1 else "MISS"
            print(f"{label:>12} {str(truth):>6} {str(d):>7} {c:>7.4f} "
                  f"{(c1 if c1 else 0):>7.4f} {r1:>6.3f} {c/med:>6.3f} {hit:>5}")


if __name__ == "__main__":
    main()
