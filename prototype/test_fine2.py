# -*- coding: utf-8 -*-
"""只测 find_offset 本身在真实尺寸下的耗时（排除内容生成的干扰）。"""
import time
import stitcher as S
import test_hard as T


def main():
    cases = [(777, 1200.0, 1437.0), (888, 1200.0, 1437.5), (555, 1200.0, 1650.0)]
    pairs = []
    for seed, s0, delta in cases:
        content = T.make_irregular_content(seed, height=9000)
        a = T.gray_of(T.make_shot(content, s0))
        b = T.gray_of(T.make_shot(content, s0 + delta))
        pairs.append((a, b, int(round(delta))))

    for fw, fr, fc, tk in [(10, 1, 1, 8), (10, 2, 2, 8), (6, 2, 2, 8),
                           (6, 2, 2, 4), (4, 2, 2, 4), (4, 4, 4, 4)]:
        S.FINE_WINDOW = fw
        S.FINE_ROW_STRIDE = fr
        S.FINE_COL_STRIDE = fc
        S.CAND_TOPK = tk
        tot = 0.0
        line = []
        for a, b, truth in pairs:
            t0 = time.time()
            d, c = S.find_offset(a, b, 321, 34)
            el = time.time() - t0
            tot += el
            err = "None" if d is None else str(d - truth)
            line.append("%s(err=%s)" % (str(d), err))
        print("win=%-2d fine=%d/%d topk=%d  avg=%.2fs/pair  %s"
              % (fw, fr, fc, tk, tot / len(pairs), " ".join(line)))


if __name__ == "__main__":
    main()
