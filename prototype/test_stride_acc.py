# -*- coding: utf-8 -*-
"""把 test_hard.py 的全部用例在若干组抽样步长下重跑，确认加大步长不牺牲准确率。"""
import stitcher as S
import test_hard as T


def main():
    for rs, cs in [(4, 2), (8, 4), (8, 2), (16, 4)]:
        S.COARSE_ROW_STRIDE = rs
        S.COARSE_COL_STRIDE = cs
        print("")
        print("######## stride row=%d col=%d ########" % (rs, cs))
        T.main()
    S.COARSE_ROW_STRIDE = 4
    S.COARSE_COL_STRIDE = 2


if __name__ == "__main__":
    main()
