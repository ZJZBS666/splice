# -*- coding: utf-8 -*-
"""验证 Swift 的 render / renderWithGaps 与 Python 的 assemble 输出完全一致。

背景：本机没有 Swift 编译器，无法直接跑 Swift 代码。这里用 numpy 把
`E:\\DeepSeek\\本地电脑\\splice\\Splice\\Core\\Stitcher.swift` 里的
render / renderWithGaps 逐行 1:1 模拟一遍（含新加的"补回最后一张底部覆盖层"
那段），再和已经通过 verify_pixels.py 逐像素验证的 Python assemble 对比。

覆盖：
  - 5 个合成场景（chat/article/feed/list/dynamic） × keep_first_chrome ∈ {True, False}
  - 真实 4 图（samples/2）
  - 每个场景再分三种走法：全有 d（plan+render）、含断开（renderWithGaps）、
    非默认 cuts（模拟用户拖过接缝）
"""
import os
import numpy as np
from PIL import Image

import gen_samples
import stitcher as S

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- Swift 侧模拟

def starts(offsets):
    """Stitcher.starts"""
    if not offsets:
        return [0]
    S_ = [0] * (len(offsets) + 1)
    for i in range(1, len(offsets) + 1):
        S_[i] = S_[i - 1] + offsets[i - 1]
    return S_


def default_cuts(offsets, content_h):
    """Stitcher.defaultCuts"""
    S_ = starts(offsets)
    return [S_[i] + content_h for i in range(len(offsets))]


def plan(offsets, content_h, cuts):
    """Stitcher.plan -> [(imageIndex, startRow, rowCount)]"""
    m = len(offsets) + 1
    if m == 1:
        return [(0, 0, content_h)]
    S_ = starts(offsets)
    G = S_[m - 1] + content_h
    segs = [(0, 0, cuts[0])]
    if m > 2:
        for i in range(1, m - 1):
            segs.append((i, cuts[i - 1] - S_[i], cuts[i] - cuts[i - 1]))
    segs.append((m - 1, cuts[m - 2] - S_[m - 1], G - cuts[m - 2]))
    return segs


def swift_render(images, segs, top, bottom, chrome_h):
    """Stitcher.render 的 numpy 等价实现（含 tail 补回）"""
    H0 = images[0].shape[0]
    W = images[0].shape[1]
    last = images[-1]
    tail_rows = max(0, min(bottom, last.shape[0]))
    max_row = max(0, H0 - bottom)

    total_h = tail_rows + sum((chrome_h if s[0] == 0 else 0) + s[2] for s in segs)
    out = np.full((max(total_h, 1), W, 3), 255, dtype=np.uint8)
    cursor = 0

    def copy_rows(src, frm, rows):
        nonlocal cursor
        if rows <= 0:
            return
        s0 = min(max(frm, 0), min(src.shape[0], max_row))
        take = min(rows, min(src.shape[0], max_row) - s0)
        if take <= 0:
            return
        out[cursor:cursor + take] = src[s0:s0 + take]
        cursor += take
        if take < rows:                       # 数据不足补白
            pad = rows - take
            out[cursor:cursor + pad] = 255
            cursor += pad

    for (idx, start_row, row_count) in segs:
        src = images[idx]
        has_chrome = (idx == 0 and chrome_h > 0)
        if has_chrome:
            copy_rows(src, 0, chrome_h)
        base = chrome_h if has_chrome else top
        copy_rows(src, base + start_row, row_count)

    if tail_rows > 0:
        out[cursor:cursor + tail_rows] = last[last.shape[0] - tail_rows:]
        cursor += tail_rows

    return out[:cursor]


def swift_render_with_gaps(images, offsets, top, bottom, content_h, chrome_h):
    """Stitcher.renderWithGaps 的 numpy 等价实现（含 tail 补回）"""
    W = images[0].shape[1]
    first_start = 0 if chrome_h > 0 else top
    first_rows = max(0, images[0].shape[0] - bottom - first_start)
    last = images[-1]
    tail_rows = max(0, min(bottom, last.shape[0]))
    max_row = max(0, images[0].shape[0] - bottom)

    total_h = first_rows + tail_rows
    for i, d in enumerate(offsets):
        if d is not None:
            total_h += d
        else:
            total_h += S.DIVIDER_HEIGHT + (images[i + 1].shape[0] - top - bottom)

    out = np.full((max(total_h, 1), W, 3), 255, dtype=np.uint8)
    cursor = 0

    def append(src, frm, rows):
        nonlocal cursor
        if rows <= 0:
            return
        s0 = min(max(frm, 0), min(src.shape[0], max_row))
        take = min(rows, min(src.shape[0], max_row) - s0)
        if take <= 0:
            return
        out[cursor:cursor + take] = src[s0:s0 + take]
        cursor += take

    def divider():
        nonlocal cursor
        out[cursor:cursor + S.DIVIDER_HEIGHT] = np.array(S.DIVIDER_COLOR, dtype=np.uint8)
        cursor += S.DIVIDER_HEIGHT

    append(images[0], first_start, first_rows)
    for i, d in enumerate(offsets):
        src = images[i + 1]
        if d is not None:
            append(src, top + (content_h - d), d)
        else:
            divider()
            append(src, top, content_h)

    if tail_rows > 0:
        out[cursor:cursor + tail_rows] = last[last.shape[0] - tail_rows:]
        cursor += tail_rows

    return out[:cursor]


# ---------------------------------------------------------------- Python 侧

def py_render(images, offsets, top, bottom, keep_first_chrome, cuts=None):
    """Python assemble（已知 d、且 cuts 为默认值的情况）"""
    H = images[0].shape[0]
    content_h = H - top - bottom
    cropped = []
    for i, r in enumerate(images):
        y0 = 0 if (i == 0 and keep_first_chrome) else top
        cropped.append(r[y0:H - bottom])
    tail = images[-1][H - bottom:H] if bottom > 0 else None
    return S.assemble(cropped, list(offsets), content_h=content_h,
                      first_kept_chrome=(keep_first_chrome and top > 0),
                      first_top=top, last_tail=tail)


def py_render_by_crops(images, offsets, top, bottom, keep_first_chrome, cuts):
    """非默认 cuts 的参考实现。**故意用最朴素的写法**：先把每张裁成内容区
    副本，再按 cuts 逐段切片拼接 —— 与 Swift 里"直接从原图取行"的写法完
    全不同的实现路径，两者一致才说明取行坐标换算没错。

    注意：Python 生产代码的 assemble() 只支持默认 cuts（它总是"上一张全
    保留、下一张只取新内容"），所以拖接缝这条路径必须单独写参考实现。
    """
    H = images[0].shape[0]
    W = images[0].shape[1]
    content_h = H - top - bottom
    chrome_h = top if keep_first_chrome else 0
    m = len(offsets) + 1
    S_ = starts(offsets)
    G = S_[-1] + content_h

    cropped = []
    for i, r in enumerate(images):
        y0 = 0 if (i == 0 and keep_first_chrome) else top
        cropped.append(r[y0:H - bottom])

    parts = []
    if keep_first_chrome and chrome_h > 0:
        parts.append(cropped[0][:chrome_h])

    if m == 1:
        parts.append(cropped[0][chrome_h:chrome_h + content_h])
    else:
        # 第 0 段：内容坐标 [0, cuts[0])
        parts.append(cropped[0][chrome_h:chrome_h + cuts[0]])
        for i in range(1, m - 1):
            st = cuts[i - 1] - S_[i]
            parts.append(cropped[i][st:st + (cuts[i] - cuts[i - 1])])
        i = m - 1
        st = cuts[m - 2] - S_[m - 1]
        parts.append(cropped[i][st:st + (G - cuts[m - 2])])

    out = np.concatenate(parts, axis=0)
    if bottom > 0:
        out = np.concatenate([out, images[-1][H - bottom:H]], axis=0)
    return out


def py_render_gaps(images, offsets, top, bottom, keep_first_chrome):
    H = images[0].shape[0]
    content_h = H - top - bottom
    chrome_h = top if keep_first_chrome else 0
    cropped = []
    for i, r in enumerate(images):
        y0 = 0 if (i == 0 and keep_first_chrome) else top
        cropped.append(r[y0:H - bottom])
    tail = images[-1][H - bottom:H] if bottom > 0 else None
    return S.assemble(cropped, list(offsets), content_h=content_h,
                      first_kept_chrome=(keep_first_chrome and top > 0),
                      first_top=top, last_tail=tail)


# ---------------------------------------------------------------- 用例

def load(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def check(name, a, b):
    if a.shape != b.shape:
        print(f"  {name:52s} SHAPE-DIFF {a.shape} vs {b.shape}  FAIL")
        return False
    d = np.abs(a.astype(np.int32) - b.astype(np.int32))
    ok = d.max() == 0
    print(f"  {name:52s} {a.shape[1]}x{a.shape[0]}  max={d.max()}  {'SAME' if ok else 'DIFF'}")
    return ok


def run_group(tag, images):
    ok = True
    grays = [S.to_gray(r) for r in images]
    top, bottom = S.detect_overlays(grays)
    n = len(images)
    d_list = [S.find_offset(grays[i], grays[i + 1], top, bottom)[0] for i in range(n - 1)]
    top2, bottom2 = S.refine_overlays(grays, d_list, top, bottom)
    if (top2, bottom2) != (top, bottom):
        top, bottom = top2, bottom2
        d_list = [S.find_offset(grays[i], grays[i + 1], top, bottom)[0]
                  for i in range(n - 1)]
    print(f"\n===== {tag}  top={top} bottom={bottom} d={d_list} =====")

    for keep in (True, False):
        k = f"keep={keep}"
        chrome_h = top if keep else 0
        content_h = images[0].shape[0] - top - bottom

        if all(d is not None for d in d_list):
            ints = [d for d in d_list]
            cuts = default_cuts(ints, content_h)
            segs = plan(ints, content_h, cuts)
            got = swift_render(images, segs, top, bottom, chrome_h)
            exp = py_render(images, ints, top, bottom, keep, cuts)
            ok &= check(f"{k} plan+render", got, exp)

            # 非默认 cuts：把每条接缝往回拖一点，模拟用户手动微调
            cuts2 = [max(S_last, c - 40) for c, S_last in
                     zip(cuts, [starts(ints)[i + 1] for i in range(len(ints))])]
            segs2 = plan(ints, content_h, cuts2)
            got2 = swift_render(images, segs2, top, bottom, chrome_h)
            exp2 = py_render_by_crops(images, ints, top, bottom, keep, cuts2)
            ok &= check(f"{k} dragged-cuts", got2, exp2)

        # 断开（renderWithGaps）这条路径要**无条件**测一遍：
        # 正常样本里所有对都能匹配上，不强制注入 None 就永远走不到这个分支，
        # 等于没验证。这里把第一条接缝强制改成断开。
        gap1 = [None] + [d for d in d_list[1:]]
        got3 = swift_render_with_gaps(images, gap1, top, bottom, content_h, chrome_h)
        exp3 = py_render_gaps(images, gap1, top, bottom, keep)
        ok &= check(f"{k} first-gap", got3, exp3)

        # 全断开
        allgap = [None] * len(d_list)
        got4 = swift_render_with_gaps(images, allgap, top, bottom, content_h, chrome_h)
        exp4 = py_render_gaps(images, allgap, top, bottom, keep)
        ok &= check(f"{k} all-gaps", got4, exp4)
    return ok


def main():
    truth = gen_samples.build_all()
    ok = True
    for name, info in truth.items():
        imgs = [load(p) for p in info["shots"]]
        ok &= run_group(name, imgs)

    real = r"E:\DeepSeek\本地电脑\splice\samples\2"
    if os.path.isdir(real):
        imgs = [load(os.path.join(real, f"{i}.jpg")) for i in range(1, 5)]
        ok &= run_group("samples/2", imgs)
    else:
        print("skip samples/2 (not found)")

    print("\n渲染等价验证：", "全部 SAME" if ok else "存在 DIFF")


if __name__ == "__main__":
    main()
