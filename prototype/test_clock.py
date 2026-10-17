"""验证：状态栏时钟变化时，新的 static_rows（按改动像素占比）仍能认出覆盖层。

合成样本里状态栏完全一致，所以旧的"行内平均差"逻辑也能过。
真机上时钟从 9:41 变成 9:42，只有几十个像素不同，
但平均差会被拉到 40+，旧逻辑会把状态栏判成"非静止"，导致每段重复贴状态栏。
"""
import zlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

STATUS_H = 186
NAV_H = 132
W, H = 1206, 2622
STATIC_EPS = 1.5
CHANGE_EPS = 2.0
STATIC_CHANGED_FRAC = 0.10


def draw_clock(d, text, y=60):
    """在左上角画时钟文字（模拟真实状态栏）。"""
    try:
        font = ImageFont.load_default(size=52)
    except Exception:
        font = ImageFont.load_default()
    d.text((70, y), text, fill=(10, 10, 10), font=font)


def make(clock_text, scroll_y, seed=7):
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (W, H), (250, 250, 250))
    d = ImageDraw.Draw(img)
    # 内容：一堆灰条，随 scroll_y 移动
    yy = -scroll_y
    i = 0
    while yy < H:
        h = 60 + (i * 37) % 90
        x0 = 80
        x1 = W - 80 - (i * 53) % 300
        if yy + h > 0:
            d.rectangle([x0, yy, x1, yy + h], fill=(60, 60, 60))
        yy += h + 40
        i += 1
    # 顶部覆盖层：不透明背景 + 导航栏
    d.rectangle([0, 0, W, STATUS_H], fill=(250, 250, 250))
    draw_clock(d, clock_text)
    d.rectangle([0, STATUS_H, W, STATUS_H + NAV_H], fill=(245, 245, 245))
    d.text((60, STATUS_H + 40), "Title", fill=(10, 10, 10))
    # 底部覆盖层
    d.rectangle([0, H - 200, W, H], fill=(250, 250, 250))
    d.rectangle([(W - 420) // 2, H - 30, (W + 420) // 2, H - 16], fill=(20, 20, 20))
    return np.asarray(img.convert("RGB")).astype(np.float32)


def gray(rgb):
    return rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114


def static_rows_old(grays):
    Hh, Ww = grays[0].shape
    st = np.ones(Hh, dtype=bool)
    n = len(grays)
    for i in range(n):
        for j in range(i + 1, n):
            diff = np.abs(grays[i] - grays[j]).mean(axis=1)
            st &= diff < STATIC_EPS
    return st


def static_rows_new(grays):
    Hh, Ww = grays[0].shape
    st = np.ones(Hh, dtype=bool)
    max_changed = max(1, int(STATIC_CHANGED_FRAC * Ww))
    n = len(grays)
    for i in range(n):
        for j in range(i + 1, n):
            diff = np.abs(grays[i] - grays[j])
            changed = (diff >= CHANGE_EPS).sum(axis=1)
            st &= changed <= max_changed
    return st


def prefix_len(st, cap):
    t = 0
    while t < cap and st[t]:
        t += 1
    return t


def suffix_len(st, cap):
    b = 0
    while b < cap and st[len(st) - 1 - b]:
        b += 1
    return b


def main():
    cap = int(0.22 * H)
    # 场景 A：时钟不变（合成样本的情况）
    a1 = gray(make("9:41", 1000))
    a2 = gray(make("9:41", 2600))
    # 场景 B：时钟变了（真机的情况）
    b1 = gray(make("9:41", 1000))
    b2 = gray(make("9:43", 2600))

    for name, pair in (("clock-same", [a1, a2]), ("clock-changed", [b1, b2])):
        so = static_rows_old(pair)
        sn = static_rows_new(pair)
        print(f"[{name}]")
        print(f"  old: top={prefix_len(so, cap)} bottom={suffix_len(so, cap)}")
        print(f"  new: top={prefix_len(sn, cap)} bottom={suffix_len(sn, cap)}")
        print(f"  truth: top={STATUS_H + NAV_H} bottom=200")
        ok = (prefix_len(sn, cap) >= STATUS_H + NAV_H - 4
              and suffix_len(sn, cap) == 200)
        print(f"  new logic {'PASS' if ok else 'FAIL'}")

    # 统计时钟变化影响了多少像素
    d = np.abs(a1[0:STATUS_H] - gray(make("9:43", 1000))[0:STATUS_H])
    print(f"\nclock change: max diff={d.max():.0f}, "
          f"changed px per row (max)={(d >= CHANGE_EPS).sum(axis=1).max()}, "
          f"mean row diff (max)={d.mean(axis=1).max():.2f}")


if __name__ == "__main__":
    main()
