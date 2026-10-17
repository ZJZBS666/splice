# -*- coding: utf-8 -*-
"""测试自动分组：把两组不同内容的截图混在一条时间线里，
算法应该在前一组最后一张与后一组第一张之间断开，分成两张长图。
"""
import numpy as np
from PIL import Image

import gen_samples
import stitcher

HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))


def load(p):
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.uint8)


def main():
    truth = gen_samples.build_all()
    # 用 chat 的 5 张 + list 的 5 张，模拟"先拼微信，再拼列表"
    n_chat = len(truth["chat"]["shots"])
    shots = truth["chat"]["shots"] + truth["list"]["shots"]
    rgbs = [load(p) for p in shots]

    # 时间线：第一组连拍（间隔 6 秒），中间隔了 5 分钟，第二组再连拍
    ts = [i * 6.0 for i in range(n_chat)]
    ts += [300.0 + i * 6.0 for i in range(len(rgbs) - n_chat)]

    results, diag = stitcher.stitch_all(rgbs, timestamps=ts, verbose=True)
    print("\ngroups =", diag["groups"])
    print("breaks =", diag["breaks"], diag["reasons"])
    print("too_tall =", diag["too_tall"], " total_h =", diag["height"])
    for k, (img, d) in enumerate(results):
        print(f"  group{k}: indices={d['indices']} size={img.shape[1]}x{img.shape[0]} "
              f"d_list={d['d_list']}")
        Image.fromarray(img).save(HERE + f"/group_test_{k}.png")

    exp_groups = [list(range(0, n_chat)), list(range(n_chat, len(rgbs)))]
    ok = diag["groups"] == exp_groups
    print("\n分组验证（靠时间间隔）：", "PASS" if ok else f"FAIL (期望 {exp_groups})")

    # 再测一遍：不给时间戳，只看内容匹配 —— 应该识别不出（记录局限）
    results2, diag2 = stitcher.stitch_all(rgbs, timestamps=None)
    print("无时间戳时 groups =", diag2["groups"],
          "->", "PASS" if diag2["groups"] == exp_groups else "无法仅靠内容分组（已知局限）")


if __name__ == "__main__":
    main()
