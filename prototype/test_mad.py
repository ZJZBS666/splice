"""测量"误差-偏移"曲线：找一个在亚像素滚动下仍有判别力的指标。

背景：真机滚动停在非整数像素位置时，iOS 会重采样，
同一内容行在两张截图里的像素值差 1~100，逐像素精确匹配（eps=0.5）全部失效。

本脚本对同一对截图，算出正确 d 与 d±1/2/4/8 处多种指标的取值，
看哪种指标"在正确 d 处明显最小"，那就是可以用的判别函数。

指标候选：
  frac_exact   : |diff| < 0.5 的行占比（现用，已知失效）
  mad_row      : 逐行平均绝对差的均值
  mad_row_med  : 逐行平均绝对差的中位数
  maxdiff_med  : 逐行最大差的中位数
  ncc          : 归一化互相关（越高越好）
  sad_norm     : 平均绝对差 / 行内标准差（相对误差）
"""
import numpy as np
from PIL import Image
import gen_samples as G
import stitcher as S
from test_subpixel2 import make_textured_content


def make_shot(content, scroll_y):
    H = G.H
    y0 = int(np.floor(scroll_y))
    frac = scroll_y - y0
    top = content[y0:y0 + H].astype(np.float32)
    nxt = content[y0 + 1:y0 + 1 + H].astype(np.float32)
    if nxt.shape[0] < H:
        pad = np.repeat(content[-1:].astype(np.float32), H - nxt.shape[0], axis=0)
        nxt = np.concatenate([nxt, pad], axis=0)
    blended = top * (1.0 - frac) + nxt * frac
    img = Image.fromarray(np.clip(blended + 0.5, 0, 255).astype(np.uint8))
    G.draw_status_bar(img, 0)
    G.draw_nav(img, "微信")
    G.draw_home_bar(img)
    return img


def metrics(A, B, d, top, bottom):
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 8:
        return None
    ys = np.arange(top, n_end)
    a = A[ys + d]
    b = B[ys]
    diff = np.abs(a - b)
    row_mad = diff.mean(axis=1)
    row_max = diff.max(axis=1)
    # NCC：整体归一化互相关
    av = a - a.mean()
    bv = b - b.mean()
    denom = np.sqrt((av * av).sum() * (bv * bv).sum())
    ncc = float((av * bv).sum() / denom) if denom > 0 else 0.0
    # 相对误差：平均绝对差 / 该区域灰度标准差
    scale = float(a.std()) + 1e-6
    return {
        "frac_exact": float((row_max < 0.5).mean()),
        "mad_row": float(row_mad.mean()),
        "mad_row_med": float(np.median(row_mad)),
        "maxdiff_med": float(np.median(row_max)),
        "ncc": ncc,
        "sad_norm": float(row_mad.mean()) / scale,
    }


def main():
    content = make_textured_content(seed=12345)
    view_h = G.H - G.STATUS_H - G.NAV_H
    # 故意用小数滚动
    scrolls = [0.0, 0.6237 * view_h, 0.6237 * view_h + 0.7133 * view_h]
    imgs = [make_shot(content, s) for s in scrolls]
    grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
    top, bottom = S.detect_overlays(grays)
    d_true = int(round(scrolls[1] - scrolls[0]))
    print(f"top={top} bottom={bottom} d_true={d_true} "
          f"(actual {scrolls[1]-scrolls[0]:.3f})")

    A, B = grays[0], grays[1]
    print(f"\n{'offset':>8} {'frac_exact':>11} {'mad_row':>9} {'mad_med':>9} "
          f"{'maxdiff_med':>12} {'ncc':>9} {'sad_norm':>9}")
    rows = []
    for delta in (0, 1, 2, 3, 4, 6, 8, 12, 20, 40):
        for sign in (0, -1) if delta == 0 else (1, -1):
            d = d_true + sign * delta
            m = metrics(A, B, d, top, bottom)
            if m is None:
                continue
            tag = f"{sign*delta:+d}" if delta else "0"
            print(f"{tag:>8} {m['frac_exact']:>11.3f} {m['mad_row']:>9.2f} "
                  f"{m['mad_row_med']:>9.2f} {m['maxdiff_med']:>12.2f} "
                  f"{m['ncc']:>9.5f} {m['sad_norm']:>9.4f}")
            rows.append((sign * delta, m))

    # 结论：哪个指标在 0 处取极值，且与相邻偏移有明显间隔
    print("\n判别力检查（正确偏移的值 vs 最接近的错误偏移的值）：")
    at0 = [m for (t, m) in rows if t == 0][0]
    for key, better in (("frac_exact", "high"), ("mad_row", "low"),
                        ("mad_row_med", "low"), ("maxdiff_med", "low"),
                        ("ncc", "high"), ("sad_norm", "low")):
        near = [m[key] for (t, m) in rows if t in (1, -1, 2, -2)]
        v0 = at0[key]
        if better == "high":
            sep = (v0 - max(near)) / max(abs(v0), 1e-9)
        else:
            sep = (min(near) - v0) / max(abs(v0), 1e-9)
        print(f"  {key:>12}: correct={v0:.4f}  nearest-wrong={[round(x,4) for x in near]}"
              f"  separation={sep*100:+.1f}%")


if __name__ == "__main__":
    main()
