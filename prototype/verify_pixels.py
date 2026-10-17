# -*- coding: utf-8 -*-
"""逐像素验证：拼接结果应当和"真值内容图"完全一致。

保留第一张状态栏+导航栏后：
    out[0 : top]  = 第一张原图的 [0 : top]
    out[top : ]   = 内容坐标 [top : top + (out高 - top)]
"""
import os
import numpy as np
from PIL import Image

import gen_samples
import stitcher

HERE = os.path.dirname(os.path.abspath(__file__))

# 生成器把动态视频画在"绝对内容坐标" STATUS_H+NAV_H+2600 处，高 420（含边界共 421 行）
VIDEO_ABS = gen_samples.STATUS_H + gen_samples.NAV_H + 2600
VIDEO_H = 421

cache = {}
_orig = gen_samples.make_content


def _patched(kind, seed):
    k = (kind, seed)
    if k not in cache:
        cache[k] = _orig(kind, seed)
    return cache[k]


gen_samples.make_content = _patched


def main():
    truth = gen_samples.build_all()
    all_ok = True
    for name, info in truth.items():
        out = np.asarray(Image.open(os.path.join(HERE, f"out_{name}.png")).convert("RGB"))
        content = cache[(gen_samples.SCENARIOS[name]["content"], gen_samples.stable_seed(name))]

        top = stitcher.detect_overlays(
            [stitcher.to_gray(np.asarray(Image.open(p).convert("RGB"))) for p in info["shots"]])[0]

        # 重建期望图：第一张原图整张（含状态栏/导航栏）+ 内容 [top : top+rest]
        first = np.asarray(Image.open(info["shots"][0]).convert("RGB"))
        rest_h = out.shape[0] - top
        expect = np.concatenate([first[:top], content[top:top + rest_h]], axis=0)

        d = np.abs(out.astype(np.int32) - expect.astype(np.int32))

        video_band = None
        if name == "dynamic":
            # 保留顶部覆盖层后，out 的行号与内容行号直接对齐（out[y] == content[y]，y>=top）
            video_band = (VIDEO_ABS, VIDEO_ABS + VIDEO_H)
            mask = np.ones(d.shape[0], dtype=bool)
            mask[max(0, video_band[0]):video_band[1]] = False
            d = d[mask]

        diff_rows = int((d.max(axis=(1, 2)) > 0).sum())
        ok = d.max() == 0
        all_ok = all_ok and ok
        note = f" (已排除动态视频区 {video_band[0]}-{video_band[1]})" if video_band else ""
        print(f"{name:9s} {out.shape[1]}x{out.shape[0]}  "
              f"mean={d.mean():.3f} max={d.max()} 差异行={diff_rows}  "
              f"{'PASS' if ok else 'FAIL'}{note}")

    print("\n逐像素验证：", "全部通过" if all_ok else "存在差异")


if __name__ == "__main__":
    main()
