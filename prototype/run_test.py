# -*- coding: utf-8 -*-
"""跑测试：用合成样本验证算法，并和真值对比。

语义约定（务必牢记，Swift 实现完全相同）：
    截图 B 是 A 向下滚动 delta 像素后的样子，故  B[y] == A[y + delta]
    所以算法求出的 d 就等于 delta，拼接时新内容为 B[HC-d : HC]，高度正好 d。

保留第一张顶部覆盖层（keep_first_chrome=True）时：
    总高 = H + sum(deltas)
    因为 = (H - bottom) + sum(deltas) + bottom
    最后那个 bottom 是"最后一张被裁掉的底部覆盖层"，它后面没有下一张能补，必须原样补回。
    out[0 : top] 是第一张的状态栏+导航栏，out[top:] 是纯内容，out 末尾 bottom 行是最后一张的底部。
"""
import os
import numpy as np
from PIL import Image

import gen_samples
import stitcher

HERE = os.path.dirname(os.path.abspath(__file__))


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def main():
    truth = gen_samples.build_all()
    ok_all = True
    for name, info in truth.items():
        print(f"\n===== {name} =====")
        rgbs = [load_rgb(p) for p in info["shots"]]
        out, diag = stitcher.stitch_group(rgbs, verbose=True, keep_first_chrome=True)

        H = rgbs[0].shape[0]
        exp_top = info["content_top"]
        exp_bottom = info["content_bottom_bar"]
        exp_deltas = info["deltas"]

        top_ok = abs(diag["top"] - exp_top) <= 8
        bot_ok = abs(diag["bottom"] - exp_bottom) <= 8
        if not (top_ok and bot_ok):
            ok_all = False
        print(f"  top    真值 {exp_top:4d}  实测 {diag['top']:4d}  {'OK' if top_ok else 'MISMATCH'}")
        print(f"  bottom 真值 {exp_bottom:4d}  实测 {diag['bottom']:4d}  {'OK' if bot_ok else 'MISMATCH'}")

        for p in diag["pairs"]:
            i = p["index"]
            exp_d = exp_deltas[i]
            if p["gap"]:
                ok_all = False
                print(f"  pair{i}: 判定为断开  WRONG (真值 {exp_d})")
            else:
                err = abs(p["d"] - exp_d)
                flag = "OK" if err <= 3 else ("CLOSE" if err <= 10 else "WRONG")
                if err > 10:
                    ok_all = False
                print(f"  pair{i}: 实测 {p['d']:4d}  真值 {exp_d:4d}  误差 {err:3d}px  {flag}")

        # 总高 = (H - bottom) + sum(deltas) + bottom（补回最后一张的底部覆盖层）= H + sum(deltas)
        exp_total = H + sum(exp_deltas)
        err_h = abs(out.shape[0] - exp_total)
        if err_h > 12:
            ok_all = False
        print(f"  总高 真值 {exp_total}  实测 {out.shape[0]}  差 {err_h}px")

        Image.fromarray(out).save(os.path.join(HERE, f"out_{name}.png"))
        print(f"  已保存 out_{name}.png ({out.shape[1]}x{out.shape[0]})")

    print("\n===== 总结 =====")
    print("全部通过 OK" if ok_all else "有失败项，见上面 WRONG/MISMATCH/断开")


if __name__ == "__main__":
    main()
