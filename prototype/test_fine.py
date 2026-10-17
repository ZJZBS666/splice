# -*- coding: utf-8 -*-
"""精修阶段的代价预算：窗口半径与抽样步长对准确率/耗时的影响。

Swift 要在 iPhone 上跑，精修目前是 全分辨率 x 41 个候选 x 最多 8 个候选，
实测会到秒级。这里找"仍然 32/32 全对"的最省配置。
"""
import sys
import time
import stitcher as S
import test_hard as T


def run_with(win, f_row, f_col, topk):
    S.FINE_WINDOW = win
    S.FINE_ROW_STRIDE = f_row
    S.FINE_COL_STRIDE = f_col
    S.CAND_TOPK = topk
    t0 = time.time()
    ok = T.main()
    return ok, time.time() - t0


def main():
    configs = [
        (10, 1, 1, 8),
        (6, 1, 1, 8),
        (6, 2, 2, 8),
        (6, 2, 2, 4),
        (4, 2, 2, 4),
        (6, 2, 4, 4),
    ]
    for win, fr, fc, tk in configs:
        print("")
        print("######## win=%d fineRow=%d fineCol=%d topk=%d ########" % (win, fr, fc, tk))
        ok, el = run_with(win, fr, fc, tk)
        print(">>> win=%d fineRow=%d fineCol=%d topk=%d  passed=%s  %.1fs"
              % (win, fr, fc, tk, ok, el))


if __name__ == "__main__":
    main()
