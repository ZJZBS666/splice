# -*- coding: utf-8 -*-
"""量真实尺寸（1206x2622）下 find_offset 的耗时，并测不同抽样步长是否仍准。

Swift 1:1 翻译后要在 iPhone 上跑，必须知道真实开销。
"""
import time
import numpy as np
import stitcher as S
import test_hard as T


def real_pair(seed, scroll0, delta):
    content = T.make_irregular_content(seed, height=9000)
    a = T.make_shot(content, scroll0)
    b = T.make_shot(content, scroll0 + delta)
    return T.gray_of(a), T.gray_of(b), int(round(delta))


def main():
    cases = [(777, 1200.0, 1437.0), (888, 1200.0, 1437.5), (555, 1200.0, 1650.0)]
    pairs = [real_pair(*c) for c in cases]
    for row_stride, col_stride in [(4, 2), (8, 4), (8, 2), (16, 4), (16, 8)]:
        S.COARSE_ROW_STRIDE = row_stride
        S.COARSE_COL_STRIDE = col_stride
        tot = 0.0
        print("== stride row=%d col=%d ==" % (row_stride, col_stride))
        for (seed, s0, delta), (A, B, truth) in zip(cases, pairs):
            t0 = time.time()
            d, c = S.find_offset(A, B, 321, 34)
            el = time.time() - t0
            tot += el
            err = "None" if d is None else str(d - truth)
            print("  seed%-4d truth=%-6d d=%-6s err=%-5s cost=%.4f  %.2fs"
                  % (seed, truth, str(d), err, c, el))
        print("  total %.2fs  avg %.2fs/pair" % (tot, tot / len(cases)))
    S.COARSE_ROW_STRIDE = 4
    S.COARSE_COL_STRIDE = 2


if __name__ == "__main__":
    main()
