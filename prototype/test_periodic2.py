"""Realistic periodicity: layout repeats but the TEXT differs per block.

test_periodic.py used byte-identical repeating blocks, which is unrealistically
periodic. Real chats have the same bubble layout but different text/avatars.

If aliases still win here, the alias theory explains the real-device bug.
If the true d wins here, the alias theory is too weak and the real bug is
elsewhere (e.g. grouping splits the screenshot set into 2-screenshot groups).

ASCII-only prints.
"""
import numpy as np

import stitcher as S

W, H = 1206, 2622
TOP, BOT = 321, 34
CONTENT_H = H - TOP - BOT
PERIOD = 480


def make_layout_periodic_chat(seed=1, height=26000, period=PERIOD):
    """Same bubble geometry every block, different text pattern every block."""
    rng = np.random.default_rng(seed)
    img = np.full((height, W, 3), 30, np.uint8)
    nblocks = height // period + 1
    for b in range(nblocks):
        base = b * period
        y = base + 12
        k = 0
        while y < base + period - 80:
            h = int(rng.integers(52, 86))
            left = (k % 2 == 0)
            w = int(rng.integers(320, 700))
            x0 = 40 if left else W - 40 - w
            color = (92, 92, 92) if left else (58, 118, 58)
            img[y:y + h, x0:x0 + w] = color
            # per-block-unique text: shift the text bars by a block-dependent
            # offset and vary their lengths -> breaks exact periodicity
            off = int(rng.integers(0, 14))
            ty = y + 8 + off
            while ty < y + h - 10:
                lw = int(rng.integers(int((w - 28) * 0.35), w - 28))
                img[ty:ty + 3, x0 + 14:x0 + 14 + lw] = (205, 205, 205)
                ty += 20
            y += h + 14
            k += 1
    return img


def make_shot(content, scroll_y):
    out = np.full((H, W, 3), 30, np.uint8)
    out[0:TOP] = (28, 28, 28)
    out[40:72, 120:340] = (235, 235, 235)
    out[100:130, 900:1150] = (235, 235, 235)
    out[TOP - 60:TOP - 10, 60:520] = (235, 235, 235)
    out[TOP:TOP + CONTENT_H] = content[scroll_y:scroll_y + CONTENT_H]
    out[H - BOT:] = (28, 28, 28)
    out[H - 30:H - 16, (W - 420) // 2:(W + 420) // 2] = (235, 235, 235)
    return out


def gray_of(rgb):
    return rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)


def run_case(name, content, d_true, show_peaks=True):
    a = gray_of(make_shot(content, 0))
    b = gray_of(make_shot(content, d_true))
    top, bot = S.detect_overlays([a, b])
    d, cost = S.find_offset(a, b, top, bot)
    ok = (d is not None) and abs(d - d_true) <= 1
    print("%-24s truth=%-5d got=%-6s cost=%.4f top=%-4d bot=%-3d %s"
          % (name, d_true, str(d), cost, top, bot, "OK" if ok else "MISS"))
    if show_peaks:
        lo = max(int(S.MIN_SCROLL_FRAC * (H - top - bot)), S.FINE_WINDOW)
        hi = H - bot - max(24, int(S.MIN_OVERLAP_FRAC * H)) - top
        sdA = S._row_sd(a, S.FINE_COL_STRIDE)
        curve = S._scan_curve(a, b, top, bot, lo, hi, sdA,
                              S.FINE_ROW_STRIDE, S.FINE_COL_STRIDE)
        best = sorted(curve.items(), key=lambda kv: kv[1][0])[:6]
        print("    peaks: %s"
              % ("  ".join("d=%d c=%.4f" % (kk, vv[0]) for kk, vv in best),))
    return ok


def main():
    print("realistic periodicity: layout repeats, text differs")
    print("")
    results = []
    for seed in (1, 2, 3):
        content = make_layout_periodic_chat(seed=seed)
        for d_true in (1810, 1900, 1330, 2290, 1000):
            results.append(run_case("seed%d d=%d" % (seed, d_true),
                                    content, d_true, show_peaks=(seed == 1)))
    print("")
    print("RESULT: %d/%d passed" % (sum(results), len(results)))


if __name__ == "__main__":
    main()
