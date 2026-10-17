"""Hypothesis: periodic chat layout creates aliases at d - k*period,
and find_offset picks a SMALLER d, which silently drops a whole chunk.

Evidence from the user's real output images:
  output height 3384 with keepFirstChrome -> sum(d) = 3384 - (2622-34) = 796
  autocorrelation of the output found strong periodicity at s=480 and s=960
  underestimating d by 960 loses exactly 960 px of content -> "middle missing"

ASCII-only prints.
"""
import numpy as np

import stitcher as S

W, H = 1206, 2622
TOP, BOT = 321, 34
CONTENT_H = H - TOP - BOT
PERIOD = 480


def make_periodic_chat(seed=1, height=26000, period=PERIOD):
    """Repeating identical blocks: exactly the alias trap.

    Each block has a few bubbles; the block pattern repeats with `period`.
    Timestamps inside the bubbles are the only thing that differs, which is
    what real chat screenshots look like.
    """
    rng = np.random.default_rng(seed)
    # build ONE block, then tile it
    block = np.full((period, W, 3), 30, np.uint8)
    y = 12
    k = 0
    while y < period - 80:
        h = int(rng.integers(52, 86))
        left = (k % 2 == 0)
        w = int(rng.integers(320, 700))
        x0 = 40 if left else W - 40 - w
        color = (92, 92, 92) if left else (58, 118, 58)
        block[y:y + h, x0:x0 + w] = color
        for ty in range(y + 8, y + h - 8, 20):
            block[ty:ty + 3, x0 + 14:x0 + w - 14] = (205, 205, 205)
        y += h + 14
        k += 1
    reps = height // period + 1
    return np.tile(block, (reps, 1, 1))[:height]


def make_shot(content, scroll_y, thumb_frac=None):
    out = np.full((H, W, 3), 30, np.uint8)
    out[0:TOP] = (28, 28, 28)
    out[40:72, 120:340] = (235, 235, 235)
    out[100:130, 900:1150] = (235, 235, 235)
    out[TOP - 60:TOP - 10, 60:520] = (235, 235, 235)
    out[TOP:TOP + CONTENT_H] = content[scroll_y:scroll_y + CONTENT_H]
    out[H - BOT:] = (28, 28, 28)
    out[H - 30:H - 16, (W - 420) // 2:(W + 420) // 2] = (235, 235, 235)
    if thumb_frac is not None:
        # moving scrollbar thumb on the right edge (mismatches every column check)
        th = 520
        ty = TOP + int(thumb_frac * (CONTENT_H - th))
        out[ty:ty + th, W - 30:W - 22] = (150, 150, 150)
    return out


def gray_of(rgb):
    return rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)


def curve_peaks(A, B, top, bot, lo, hi, k=8):
    sdA = S._row_sd(A, S.FINE_COL_STRIDE)
    curve = S._scan_curve(A, B, top, bot, lo, hi, sdA,
                          S.FINE_ROW_STRIDE, S.FINE_COL_STRIDE)
    best = sorted(curve.items(), key=lambda kv: kv[1][0])[:k]
    return [(kk, vv[0]) for kk, vv in best]


def run_case(name, content, d_true, use_thumb=False):
    a_rgb = make_shot(content, 0, 0.05 if use_thumb else None)
    b_rgb = make_shot(content, d_true, 0.85 if use_thumb else None)
    a, b = gray_of(a_rgb), gray_of(b_rgb)
    top, bot = S.detect_overlays([a, b])
    d, cost = S.find_offset(a, b, top, bot)
    lo = max(int(S.MIN_SCROLL_FRAC * (H - top - bot)), S.FINE_WINDOW)
    hi = H - bot - max(24, int(S.MIN_OVERLAP_FRAC * H)) - top
    peaks = curve_peaks(a, b, top, bot, lo, hi)
    ok = (d is not None) and abs(d - d_true) <= 1
    print("%-26s truth=%-5d got=%-6s cost=%.4f top=%-4d bot=%-3d %s"
          % (name, d_true, str(d), cost, top, bot, "OK" if ok else "MISS"))
    print("    curve best: %s"
          % ("  ".join("d=%d c=%.4f" % (kk, vv) for kk, vv in peaks),))
    gaps = sorted(set(d_true - kk for kk, _ in peaks if kk < d_true))
    print("    truth-minus-candidates: %s   (period=%d)" % (gaps, PERIOD))
    return ok


def main():
    print("PERIOD=%d  MIN_SCROLL_FRAC=%.2f  MIN_BAND_AGREE=%d  BAND_COUNT=%d"
          % (PERIOD, S.MIN_SCROLL_FRAC, S.MIN_BAND_AGREE, S.BAND_COUNT))
    print("")
    results = []
    for seed in (1, 2):
        content = make_periodic_chat(seed=seed)
        for d_true in (1810, 1900, 2290, 1330):
            results.append(run_case("seed%d d=%d" % (seed, d_true),
                                    content, d_true))
        results.append(run_case("seed%d d=1810 +thumb" % seed, content, 1810,
                                use_thumb=True))
    print("")
    print("RESULT: %d/%d passed" % (sum(results), len(results)))


if __name__ == "__main__":
    main()
