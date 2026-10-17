"""验证 Swift 新版 render / renderWithGaps 的坐标换算是否正确。

Windows 上没法跑 Swift，所以这里用 Python 把新版 Swift 的取行逻辑
1:1 模拟一遍，再和已经逐像素验证过的旧写法对比。

新版 Swift 的关键变化：不再先给每张图做一份 `cropped` 副本，
而是直接从未裁剪原图按坐标取行（省约 130MB 内存）。
坐标换算写错就会整体错位、把底部覆盖层抄进长图，或让第一张丢失状态栏，
所以必须单独验证。

对应关系：
  cropped[i] = images[i][ (0 if i==0 and chrome else top) : H-bottom ]
  render_new(images, segments, top, bottom, chromeH)
    必须 == render_cropped_old(cropped, segments, chromeH)
"""
import numpy as np
from PIL import Image
import stitcher as S


# ---------------------------------------------------------------- Swift 新版模拟

def render_new(images, segments, top, bottom, chrome_h):
    """1:1 模拟 Swift Stitcher.render(_:segments:top:bottom:chromeH:)"""
    W = images[0].shape[1]
    total_h = 0
    for (img_idx, start_row, row_count) in segments:
        total_h += (chrome_h if img_idx == 0 else 0) + row_count
    out = np.zeros((max(total_h, 1), W, 3), dtype=np.uint8)
    cursor = 0
    max_row = max(0, images[0].shape[0] - bottom)

    def copy_rows(src, frm, rows):
        nonlocal cursor
        if rows <= 0:
            return
        s = min(max(frm, 0), min(src.shape[0], max_row))
        take = min(rows, min(src.shape[0], max_row) - s)
        if take <= 0:
            return
        out[cursor:cursor + take] = src[s:s + take]
        cursor += take
        if take < rows:
            pad = rows - take
            out[cursor:cursor + pad] = 255
            cursor += pad

    for (img_idx, start_row, row_count) in segments:
        src = images[img_idx]
        has_chrome = (img_idx == 0 and chrome_h > 0)
        if has_chrome:
            copy_rows(src, 0, chrome_h)
        base = chrome_h if has_chrome else top
        copy_rows(src, base + start_row, row_count)
    return out[:cursor]


def render_with_gaps_new(images, offsets, top, bottom, content_h, chrome_h):
    """1:1 模拟 Swift Stitcher.renderWithGaps(_:offsets:top:bottom:contentHeight:chromeH:)"""
    W = images[0].shape[1]
    first_start = 0 if chrome_h > 0 else top
    first_rows = max(0, images[0].shape[0] - bottom - first_start)
    total_h = first_rows
    for i, d in enumerate(offsets):
        if d is not None:
            total_h += d
        else:
            total_h += S.DIVIDER_HEIGHT + (images[i + 1].shape[0] - top - bottom)
    out = np.zeros((max(total_h, 1), W, 3), dtype=np.uint8)
    cursor = 0
    max_row = max(0, images[0].shape[0] - bottom)

    def append(src, frm, rows):
        nonlocal cursor
        if rows <= 0:
            return
        s = min(max(frm, 0), min(src.shape[0], max_row))
        take = min(rows, min(src.shape[0], max_row) - s)
        if take <= 0:
            return
        out[cursor:cursor + take] = src[s:s + take]
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
    return out[:cursor]


# ---------------------------------------------------------------- 旧写法（已逐像素验证）

def render_cropped_old(cropped, segments, chrome_h):
    W = cropped[0].shape[1]
    total_h = 0
    for (img_idx, start_row, row_count) in segments:
        total_h += (chrome_h if img_idx == 0 else 0) + row_count
    out = np.zeros((max(total_h, 1), W, 3), dtype=np.uint8)
    cursor = 0

    def copy_rows(src, frm, rows):
        nonlocal cursor
        if rows <= 0:
            return
        s = min(max(frm, 0), src.shape[0])
        take = min(rows, src.shape[0] - s)
        if take <= 0:
            return
        out[cursor:cursor + take] = src[s:s + take]
        cursor += take
        if take < rows:
            pad = rows - take
            out[cursor:cursor + pad] = 255
            cursor += pad

    for (img_idx, start_row, row_count) in segments:
        src = cropped[img_idx]
        if img_idx == 0 and chrome_h > 0:
            copy_rows(src, 0, chrome_h)
            copy_rows(src, chrome_h + start_row, row_count)
        else:
            copy_rows(src, start_row, row_count)
    return out[:cursor]


def assemble_cropped_old(cropped, d_list, content_h, first_kept_chrome, first_top):
    """旧版 Python assemble()，已通过 verify_pixels.py 逐像素验证。"""
    W = cropped[0].shape[1]
    parts = [cropped[0]]
    for i, d in enumerate(d_list):
        if d is None:
            parts.append(np.full((S.DIVIDER_HEIGHT, W, 3), S.DIVIDER_COLOR, dtype=np.uint8))
            parts.append(cropped[i + 1])
        else:
            parts.append(cropped[i + 1][content_h - d:])
    return np.concatenate(parts, axis=0)


def make_cropped(images, top, bottom, chrome_h):
    out = []
    for i, img in enumerate(images):
        y0 = 0 if (i == 0 and chrome_h > 0) else top
        out.append(img[y0:img.shape[0] - bottom])
    return out


# ---------------------------------------------------------------- Swift plan/defaultCuts 模拟

def starts(offsets):
    S_ = [0] * (len(offsets) + 1)
    for i in range(1, len(offsets) + 1):
        S_[i] = S_[i - 1] + offsets[i - 1]
    return S_


def default_cuts(offsets, content_h):
    S_ = starts(offsets)
    return [S_[i] + content_h for i in range(len(offsets))]


def plan(offsets, content_h, cuts):
    m = len(offsets) + 1
    S_ = starts(offsets)
    G = S_[m - 1] + content_h
    segs = [(0, 0, cuts[0])]
    for i in range(1, m - 1):
        segs.append((i, cuts[i - 1] - S_[i], cuts[i] - cuts[i - 1]))
    segs.append((m - 1, cuts[m - 2] - S_[m - 1], G - cuts[m - 2]))
    return segs


# ---------------------------------------------------------------- 主流程

def main():
    samples = ["chat", "article", "feed", "list", "dynamic"]
    fails = 0
    for name in samples:
        imgs = [np.asarray(Image.open(f"samples/{name}_{i}.png").convert("RGB"))
                for i in range(4)]
        grays = [S.to_gray(r) for r in imgs]
        H = grays[0].shape[0]
        top, bottom = S.detect_overlays(grays)
        ds = [S.find_offset(grays[i], grays[i + 1], top, bottom)[0] for i in range(3)]
        content_h = H - top - bottom

        for keep in (True, False):
            chrome_h = top if keep else 0
            cropped = make_cropped(imgs, top, bottom, chrome_h)

            cuts = default_cuts(ds, content_h)
            segs = plan(ds, content_h, cuts)
            old = render_cropped_old(cropped, segs, chrome_h)
            new = render_new(imgs, segs, top, bottom, chrome_h)
            same = old.shape == new.shape and np.array_equal(old, new)
            print(f"{name:8s} keep={str(keep):5s} plan  "
                  f"old={old.shape} new={new.shape} {'SAME' if same else 'DIFF'}")
            fails += 0 if same else 1

            offs = [ds[0], None, ds[2]]
            oldg = assemble_cropped_old(cropped, offs, content_h, keep, top)
            newg = render_with_gaps_new(imgs, offs, top, bottom, content_h, chrome_h)
            sameg = oldg.shape == newg.shape and np.array_equal(oldg, newg)
            print(f"{name:8s} keep={str(keep):5s} gaps  "
                  f"old={oldg.shape} new={newg.shape} {'SAME' if sameg else 'DIFF'}")
            fails += 0 if sameg else 1

            # 拖动接缝后重拼：用一组非默认 cuts 再验一次
            mid = [(cuts[i] + (cuts[i + 1] if i + 1 < len(cuts) else
                               starts(ds)[-1] + content_h)) // 2 for i in range(len(cuts))]
            segs2 = plan(ds, content_h, mid)
            old2 = render_cropped_old(cropped, segs2, chrome_h)
            new2 = render_new(imgs, segs2, top, bottom, chrome_h)
            same2 = old2.shape == new2.shape and np.array_equal(old2, new2)
            print(f"{name:8s} keep={str(keep):5s} drag  "
                  f"old={old2.shape} new={new2.shape} {'SAME' if same2 else 'DIFF'}")
            fails += 0 if same2 else 1

    print()
    print("ALL SAME" if fails == 0 else f"{fails} DIFF")


if __name__ == "__main__":
    main()
