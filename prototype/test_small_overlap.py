"""Reproduce the real-device failure: two screenshots with only a SMALL overlap.

Real case (from user's output images):
  output height 3384, seam at 2588 = top(321) + contentH(2267)
  3384 - 2588 = 796  -> algorithm chose d = 796
  But the user scrolled nearly a full screen, so the true d was much larger,
  leaving only ~100-300 px of overlap.

Hypothesis: when the overlap window is small, the correct d is rejected by
  n_tex >= MIN_MATCH_ROWS(30)  and  used/n_tex >= MIN_USED_FRAC(0.25)
so a spurious small-d match wins -> the middle of the conversation disappears.

ASCII-only prints (Windows GBK console).
"""
import numpy as np

import stitcher as S

W, H = 1206, 2622
TOP, BOT = 321, 34
CONTENT_H = H - TOP - BOT


def make_chat_content(seed=1, height=24000):
    """Dark chat background with sparse bubbles: most rows are uniform.

    This mimics WeChat/QQ dark mode, where a large share of rows carry almost
    no texture -- exactly the situation that starves the texture mask.
    """
    rng = np.random.default_rng(seed)
    img = np.full((height, W, 3), 30, np.uint8)
    y = 100
    while y < height - 200:
        h = int(rng.integers(60, 130))
        left = bool(rng.integers(0, 2))
        w = int(rng.integers(300, 800))
        x0 = 40 if left else W - 40 - w
        color = (95, 95, 95) if left else (60, 120, 60)
        img[y:y + h, x0:x0 + w] = color
        for ty in range(y + 10, y + h - 10, 22):
            img[ty:ty + 3, x0 + 14:x0 + w - 14] = (200, 200, 200)
        y += h + int(rng.integers(20, 60))
    return img


def make_shot(content, scroll_y):
    """Full screenshot: static chrome on top, content in the middle, home bar."""
    out = np.full((H, W, 3), 30, np.uint8)
    # static chrome (status bar + nav bar) -- identical in every screenshot
    out[0:TOP] = (28, 28, 28)
    out[40:72, 120:340] = (235, 235, 235)      # clock
    out[100:130, 900:1150] = (235, 235, 235)   # battery
    out[TOP - 60:TOP - 10, 60:520] = (235, 235, 235)  # title
    # scrolling content
    out[TOP:TOP + CONTENT_H] = content[scroll_y:scroll_y + CONTENT_H]
    # static home indicator
    out[H - BOT:] = (28, 28, 28)
    out[H - 30:H - 16, (W - 420) // 2:(W + 420) // 2] = (235, 235, 235)
    return out


def gray_of(rgb):
    g = rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    return g


def run_case(name, content, d_true):
    a = gray_of(make_shot(content, 0))
    b = gray_of(make_shot(content, d_true))
    top, bot = S.detect_overlays([a, b])
    overlap = CONTENT_H - d_true
    d, cost = S.find_offset(a, b, top, bot)
    lo = max(int(S.MIN_SCROLL_FRAC * (H - top - bot)), S.FINE_WINDOW)
    hi = H - bot - max(24, int(S.MIN_OVERLAP_FRAC * H)) - top
    ok = (d is not None) and abs(d - d_true) <= 1
    print("%-22s truth=%-5d got=%-6s cost=%.4f top=%-4d bot=%-3d "
          "overlap=%-5d window=[%d,%d] %s"
          % (name, d_true, str(d), cost, top, bot, overlap, lo, hi,
             "OK" if ok else "MISS"))
    return ok


def main():
    print("MIN_MATCH_ROWS=%d MIN_USED_FRAC=%.2f MIN_OVERLAP_FRAC=%.2f"
          % (S.MIN_MATCH_ROWS, S.MIN_USED_FRAC, S.MIN_OVERLAP_FRAC))
    results = []
    for seed in (1, 2, 3):
        content = make_chat_content(seed=seed)
        for overlap in (1600, 1000, 700, 400, 250, 150):
            d_true = CONTENT_H - overlap
            results.append(run_case("seed%d ovl%d" % (seed, overlap),
                                    content, d_true))
    print("")
    print("RESULT: %d/%d passed" % (sum(results), len(results)))


if __name__ == "__main__":
    main()
