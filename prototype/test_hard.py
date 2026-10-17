# -*- coding: utf-8 -*-
"""
困难场景端到端回归：直接调用生产函数 find_offset / stitch_group。

覆盖三类真机必然遇到、但整数合成样本覆盖不到的情况：
  1. 亚像素滚动（UIScrollView 停下时是小数位移，截图会双线性重采样）
  2. 有纹理的视频 / 动图（占 ~21% 屏幕，每帧内容不同）
  3. 完全无关的两张截图（必须判"断开"，不能瞎拼）

只用 ASCII 输出，Windows 控制台 GBK 不会炸。
"""

import numpy as np
from PIL import Image

import gen_samples as G
import stitcher as S

TRUTH_TOL = 1          # 亚像素下允许 1px 误差
BAD_COST = 0.65


def make_irregular_content(seed, height=16000):
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
    rng = np.random.default_rng(seed)
    v = rng.integers(0, 255, size=(h, w, 3), dtype=np.uint8)
    for _ in range(8):
        y0 = int(rng.integers(0, h - 60))
        x0 = int(rng.integers(0, w - 60))
        v[y0:y0 + int(rng.integers(30, 120)), x0:x0 + int(rng.integers(30, 160))] = \
            rng.integers(0, 255, size=3)
    return v


def make_shot(content, scroll_y, video=None, video_abs_y=0, video_h=0, video_w=0):
    H = G.H
    y0 = int(np.floor(scroll_y))
    frac = scroll_y - y0
    t = content[y0:y0 + H].astype(np.float32)
    n = content[y0 + 1:y0 + 1 + H].astype(np.float32)
    if n.shape[0] < H:
        pad = np.repeat(content[-1:].astype(np.float32), H - n.shape[0], axis=0)
        n = np.concatenate([n, pad], axis=0)
    arr = np.clip(t * (1 - frac) + n * frac + 0.5, 0, 255).astype(np.uint8)

    if video is not None:
        vy = G.STATUS_H + G.NAV_H + int(video_abs_y - scroll_y)
        vx = (G.W - video_w) // 2
        y_start = max(0, vy)
        y_end = min(H, vy + video_h)
        if y_end > y_start:
            src = y_start - vy
            arr[y_start:y_end, vx:vx + video_w] = video[src:src + (y_end - y_start)]

    img = Image.fromarray(arr)
    G.draw_status_bar(img, 0)
    G.draw_nav(img, "B站")
    G.draw_home_bar(img)
    return img


def gray_of(img):
    return S.to_gray(np.asarray(img.convert("RGB")))


def pair_gray(content, s0, s1, video=None, video_abs_y=0):
    """返回 (A_gray, B_gray, truth_d)。truth_d 取整数部分（亚像素下允许 1px 差）。"""
    i0 = make_shot(content, s0, video, video_abs_y, 550, 1000) if video is not None \
        else make_shot(content, s0)
    i1 = make_shot(content, s1, video, video_abs_y, 550, 1000) if video is not None \
        else make_shot(content, s1)
    return gray_of(i0), gray_of(i1), int(round(s1 - s0))


def run_case(name, A, B, truth, tol=TRUTH_TOL, expect_gap=False):
    d, cost = S.find_offset(A, B, 0, 0)
    if expect_gap:
        ok = d is None
        tag = "OK" if ok else "FAIL"
        print("  %-26s d=%-8s cost=%.4f  expect=GAP  %s"
              % (name, str(d), cost, tag))
        return ok
    if d is None:
        print("  %-26s d=None (判断开)  truth=%d  FAIL" % (name, truth))
        return False
    err = abs(d - truth)
    ok = err <= tol
    print("  %-26s d=%-6d truth=%-6d err=%-3d cost=%.4f  %s"
          % (name, d, truth, err, cost, "OK" if ok else "FAIL"))
    return ok


def main():
    results = []

    print("== 1. 亚像素滚动（irregular 纹理内容） ==")
    for seed in (777, 888):
        content = make_irregular_content(seed)
        for tail in (0.0, 0.25, 0.5, 0.75):
            base = 1400.0
            A, B, truth = pair_gray(content, base, base + 1437 + tail)
            results.append(run_case("seed%d tail=%.2f" % (seed, tail), A, B, truth))

    print("== 2. 有纹理视频（占 ~21% 屏幕，每帧不同） ==")
    content = make_irregular_content(555)
    for tail in (0.0, 0.25, 0.5):
        v0 = make_textured_video(11)
        v1 = make_textured_video(12)
        H = G.H
        base = 1400.0
        d_true = 1437
        # 视频绝对位置取屏幕中部，保证两张里都可见
        vabs = 1400.0 + (G.STATUS_H + G.NAV_H) + (H // 2 - 550 // 2)
        i0 = make_shot(content, base, v0, vabs, 550, 1000)
        i1 = make_shot(content, base + d_true + tail, v1, vabs, 550, 1000)
        A, B = gray_of(i0), gray_of(i1)
        results.append(run_case("video tail=%.2f" % tail, A, B, d_true))

    print("== 3. 完全无关的两张截图（必须判断开） ==")
    c1 = make_irregular_content(101)
    c2 = make_irregular_content(202)
    A = gray_of(make_shot(c1, 1400.0))
    B = gray_of(make_shot(c2, 1400.0))
    results.append(run_case("unrelated irr101/irr202", A, B, 0, expect_gap=True))

    print("== 4. 合成场景（整数滚动，必须精确） ==")
    scenes = G.build_all()
    for name, sc in scenes.items():
        grays = [S.to_gray(np.asarray(Image.open(p).convert("RGB")))
                 for p in sc["shots"]]
        st = S.static_rows(grays)
        top, bottom = S.detect_overlays(grays)
        for i in range(len(grays) - 1):
            d, cost = S.find_offset(grays[i], grays[i + 1], top, bottom)
            truth = sc["deltas"][i]
            ok = (d is not None and abs(d - truth) <= TRUTH_TOL)
            print("  %-10s pair%d d=%-6s truth=%-6d cost=%.4f  %s"
                  % (name, i, str(d), truth, cost, "OK" if ok else "FAIL"))
            results.append(ok)

    ok_n = sum(1 for r in results if r)
    print("")
    print("hard cases: %d/%d passed" % (ok_n, len(results)))
    print("RESULT: " + ("ALL PASS" if ok_n == len(results) else "SOME FAILED"))


if __name__ == "__main__":
    main()
