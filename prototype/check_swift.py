# -*- coding: utf-8 -*-
"""粗查 Swift 源码里的括号是否配平（本机没有 Swift 编译器，只能做静态检查）。"""
import os
import re
import sys

TARGETS = [
    r"E:\DeepSeek\本地电脑\splice\Splice\App\RootView.swift",
    r"E:\DeepSeek\本地电脑\splice\Splice\App\SpliceApp.swift",
    r"E:\DeepSeek\本地电脑\splice\Splice\App\SpliceModel.swift",
    r"E:\DeepSeek\本地电脑\splice\Splice\App\Theme.swift",
    r"E:\DeepSeek\本地电脑\splice\Splice\Core\Stitcher.swift",
    r"E:\DeepSeek\本地电脑\splice\Splice\Core\ImageBuffer.swift",
    r"E:\DeepSeek\本地电脑\splice\Splice\Core\PhotoLibrary.swift",
]

STR = re.compile(r'"(?:\\.|[^"\\])*"')
LINE_COMMENT = re.compile(r"//[^\n]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def strip(src):
    # 顺序很重要：必须**先**去掉字符串字面量，再去注释。
    # 否则 "https://github.com/..." 里的 `//` 会被当成注释开头，
    # 把后面半行连括号一起吃掉，报出根本不存在的括号不平。
    src = STR.sub('""', src)
    src = BLOCK_COMMENT.sub("", src)
    src = LINE_COMMENT.sub("", src)
    return src


def main():
    bad = 0
    for p in TARGETS:
        if not os.path.isfile(p):
            print("missing", p)
            bad += 1
            continue
        s = strip(open(p, encoding="utf-8").read())
        counts = [(s.count(a), s.count(b), n) for a, b, n in
                  [("{", "}", "brace"), ("(", ")", "paren"), ("[", "]", "brack")]]
        line = "  ".join(f"{n} {x}/{y}" for x, y, n in counts)
        ok = all(x == y for x, y, n in counts)
        if not ok:
            bad += 1
        print(f"{os.path.basename(p):22s} {line}  {'OK' if ok else 'UNBALANCED'}")
    print("\n结果:", "全部配平" if bad == 0 else f"{bad} 个文件有问题")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
