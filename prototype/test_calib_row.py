"""标定「逐行归一化误差」阈值，用于动态遮挡区段（视频/进度条）排除。

要回答两个问题：
  1) 正确偏移处，正常内容行的 rne = rowMAD / max(rowSD, 8) 有多大？
     （亚像素重采样会让它变高，不能定太低，否则把正常行也排掉）
  2) 正确偏移处，动态视频行的 rne 有多大？错偏移处呢？
据此选 BAD_ROW_COST，使「正常行不被排、视频行被排、错偏移不会靠排除作弊」。
"""
import numpy as np
import gen_samples as G
import stitcher as S
from test_video import (make_irregular_content, make_textured_video,
                        make_shot_with_video)


SD_FLOOR = 8.0


def rne_stats(A, B, d, top, bottom):
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top + 8:
        return None
    ys = np.arange(top, n_end)
    a = A[ys + d]
    b = B[ys]
    row_sd = a.std(axis=1)
    rm = np.abs(a - b).mean(axis=1)
    rne = rm / np.maximum(row_sd, SD_FLOOR)
    tex = row_sd >= 3.0
    if int(tex.sum()) < 10:
        return None
    return rne[tex]


def pct(v, q):
    return float(np.percentile(v, q))


def report(label, A, B, top, bottom, d_true, video_rows=None):
    v = rne_stats(A, B, d_true, top, bottom)
    if v is None:
        print(f"{label:>16} (no data)")
        return
    print(f"{label:>16} d={d_true:>5} n={v.size:>4} "
          f"p50={pct(v,50):>6.2f} p90={pct(v,90):>6.2f} p99={pct(v,99):>6.2f} "
          f"max={v.max():>6.2f} frac>=1.0={(v>=1.0).mean():>5.2f} "
          f">=1.5={(v>=1.5).mean():>5.2f} >=2.0={(v>=2.0).mean():>5.2f} "
          f">=2.5={(v>=2.5).mean():>5.2f} >=3.0={(v>=3.0).mean():>5.2f}")
    if video_rows is not None:
        n_all = A.shape[0]
        ys = np.arange(top, n_all - bottom - d_true)
        row_sd = A[ys + d_true].std(axis=1)
        rm = np.abs(A[ys + d_true] - B[ys]).mean(axis=1)
        rne = rm / np.maximum(row_sd, SD_FLOOR)
        tex = row_sd >= 3.0
        vy0, vy1 = video_rows
        inv = np.zeros(ys.size, bool)
        lo = max(0, vy0 - ys[0])
        hi = min(ys.size, vy1 - ys[0])
        inv[lo:hi] = True
        sel = tex & inv
        if sel.sum() > 5:
            print(f"{'  ->video rows':>16} n={int(sel.sum()):>4} "
                  f"p50={pct(rne[sel],50):>6.2f} min={rne[sel].min():>6.2f}")


def main():
    print("=== A. 5 synthetic scenes, integer scroll, correct d ===")
    truth = G.build_all()
    for name in ("chat", "article", "feed", "list", "dynamic"):
        info = truth[name]
        from PIL import Image
        rgbs = [np.asarray(Image.open(p).convert("RGB"), dtype=np.uint8)
                for p in info["shots"]]
        grays = [S.to_gray(r) for r in rgbs]
        top, bottom = S.detect_overlays(grays)
        d = int(info["deltas"][0])
        report(name, grays[0], grays[1], top, bottom, d)

    print("\n=== B. textured content, subpixel, correct d ===")
    tc = make_irregular_content(seed=777)
    for tail in (0.0, 0.25, 0.5, 0.75):
        H = G.H
        imgs = []
        s1 = 1437.0 + tail
        for s in (0.0, s1):
            y0 = int(np.floor(s))
            fr = s - y0
            t = tc[y0:y0 + H].astype(np.float32)
            n = tc[y0 + 1:y0 + 1 + H].astype(np.float32)
            if n.shape[0] < H:
                pad = np.repeat(tc[-1:].astype(np.float32), H - n.shape[0], axis=0)
                n = np.concatenate([n, pad], axis=0)
            from PIL import Image
            im = Image.fromarray(np.clip(t * (1 - fr) + n * fr + 0.5, 0, 255).astype(np.uint8))
            G.draw_status_bar(im, 0)
            G.draw_nav(im, "微信")
            G.draw_home_bar(im)
            imgs.append(im)
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        report(f"plain+{tail}", grays[0], grays[1], top, bottom, int(round(s1)))

    print("\n=== C. textured VIDEO, subpixel, correct d (video band marked) ===")
    for i, tail in enumerate((0.0, 0.25, 0.5, 0.75)):
        v0 = make_textured_video(seed=100 + i)
        v1 = make_textured_video(seed=200 + i)
        s1 = 1437.0 + tail
        imgs = [make_shot_with_video(tc, 0.0, v0, 2600, 550, 1000),
                make_shot_with_video(tc, s1, v1, 2600, 550, 1000)]
        grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
        top, bottom = S.detect_overlays(grays)
        vy = G.STATUS_H + G.NAV_H + int(2600 - s1)
        report(f"video+{tail}", grays[0], grays[1], top, bottom,
               int(round(s1)), video_rows=(vy, vy + 550))

    print("\n=== D. WRONG offsets (cheating risk) ===")
    info = truth["chat"]
    from PIL import Image
    rgbs = [np.asarray(Image.open(p).convert("RGB"), dtype=np.uint8)
            for p in info["shots"]]
    grays = [S.to_gray(r) for r in rgbs]
    top, bottom = S.detect_overlays(grays)
    d_true = int(info["deltas"][0])
    for off in (1, 2, 5, 20, 200, 600):
        report(f"chat d_true+{off}", grays[0], grays[1], top, bottom, d_true + off)

    print("\n=== E. UNRELATED pair ===")
    ca = G.make_content("chat", seed=G.stable_seed("chat"))
    cb = G.make_content("list", seed=G.stable_seed("list"))
    imgs = [G.make_screenshot(ca, 0, "chat", title="微信")[0],
            G.make_screenshot(cb, 0, "list", title="设置")[0]]
    grays = [S.to_gray(np.asarray(im.convert("RGB"))) for im in imgs]
    top, bottom = S.detect_overlays(grays)
    for d in (400, 1200, 2014):
        report(f"unrel d={d}", grays[0], grays[1], top, bottom, d)


if __name__ == "__main__":
    main()
