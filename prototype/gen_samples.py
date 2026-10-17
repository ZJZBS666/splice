# -*- coding: utf-8 -*-
"""
生成仿 iPhone 截图样本，用于验证拼接算法。
这些是合成数据，不是真实截图 —— 用来在电脑上先把算法调准，再翻译成 Swift。
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W = 1206
H = 2622

STATUS_H = 186      # 状态栏
NAV_H = 132         # 导航栏（标题栏）
HOME_BAR_H = 34     # 底部小横条占的高度
HOME_BAR_ZONE = 34  # 小白条 + 其下方背景的整段高度（H-34 到 H-1），系统覆盖层

OUT = os.path.join(os.path.dirname(__file__), "samples")


def load_font(size, bold=False):
    cands = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for p in cands:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


F_TITLE = load_font(46, bold=True)
F_BODY = load_font(40)
F_SMALL = load_font(32)
F_STATUS = load_font(38, bold=True)


def make_content(kind, seed):
    """造一张很长的『内容图』，宽度 = W，高度足够长。"""
    rng = np.random.default_rng(seed)
    total_h = 16000
    img = Image.new("RGB", (W, total_h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    y = 0

    if kind == "chat":
        # 聊天记录：左右气泡
        while y < total_h - 400:
            who = rng.integers(0, 2)
            lines = int(rng.integers(1, 4))
            bh = 60 + lines * 56
            bw = int(rng.integers(320, 720))
            if who == 0:
                x0 = 40
                color = (255, 255, 255)
                outline = (225, 225, 225)
            else:
                x0 = W - 40 - bw
                color = (149, 236, 105)
                outline = None
            d.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=14,
                                fill=color, outline=outline, width=2)
            for i in range(lines):
                ly = y + 26 + i * 56
                lw = int(bw * rng.uniform(0.45, 0.86))
                d.rectangle([x0 + 24, ly, x0 + 24 + lw, ly + 26],
                            fill=(30, 30, 30) if rng.random() > 0.3 else (90, 90, 90))
            y += bh + int(rng.integers(30, 70))

    elif kind == "article":
        # 长文章：标题 + 段落 + 插图
        d.rectangle([60, 40, W - 60, 150], fill=(20, 20, 20))
        y = 200
        while y < total_h - 600:
            if rng.random() < 0.12:
                ih = int(rng.integers(400, 700))
                c1 = tuple(int(v) for v in rng.integers(40, 220, 3))
                c2 = tuple(int(v) for v in rng.integers(40, 220, 3))
                for yy in range(0, ih, 4):
                    t = yy / ih
                    col = tuple(int(c1[k] * (1 - t) + c2[k] * t) for k in range(3))
                    d.rectangle([60, y + yy, W - 60, y + yy + 4], fill=col)
                y += ih + 40
            else:
                n = int(rng.integers(2, 6))
                for i in range(n):
                    lw = int(rng.uniform(0.55, 1.0) * (W - 120))
                    d.rectangle([60, y, 60 + lw, y + 30], fill=(60, 60, 60))
                    y += 62
                y += 34

    elif kind == "feed":
        # 信息流：卡片 + 图片 + 标题
        y = 30
        while y < total_h - 900:
            ch = int(rng.integers(700, 1000))
            d.rounded_rectangle([30, y, W - 30, y + ch], radius=22,
                                fill=(252, 252, 252), outline=(238, 238, 238), width=2)
            d.ellipse([56, y + 30, 136, y + 110], fill=tuple(int(v) for v in rng.integers(60, 230, 3)))
            d.rectangle([160, y + 46, 160 + int(rng.integers(160, 380)), y + 84], fill=(70, 70, 70))
            iy = y + 140
            ih = int(rng.integers(380, 560))
            c1 = tuple(int(v) for v in rng.integers(50, 230, 3))
            c2 = tuple(int(v) for v in rng.integers(50, 230, 3))
            for yy in range(0, ih, 6):
                t = yy / ih
                col = tuple(int(c1[k] * (1 - t) + c2[k] * t) for k in range(3))
                d.rectangle([56, iy + yy, W - 56, iy + yy + 6], fill=col)
            ty = iy + ih + 26
            for i in range(2):
                lw = int(rng.uniform(0.4, 0.92) * (W - 160))
                d.rectangle([56, ty + i * 54, 56 + lw, ty + i * 54 + 28], fill=(45, 45, 45))
            y += ch + 34

    elif kind == "list":
        # 设置页：一行行高度几乎一样（考验重复内容）
        y = 0
        i = 0
        while y < total_h - 200:
            d.rectangle([0, y, W, y + 2], fill=(238, 238, 238))
            d.rectangle([50, y + 30, 50 + int(rng.integers(120, 300)), y + 66], fill=(35, 35, 35))
            d.rectangle([W - 90, y + 34, W - 50, y + 62], fill=(190, 190, 190))
            y += 118
            i += 1
        d.rectangle([0, y, W, y + 2], fill=(238, 238, 238))

    return np.asarray(img, dtype=np.uint8)


def draw_status_bar(img, t):
    d = ImageDraw.Draw(img)
    # 真实 iOS 截图的系统栏是不透明背景，内容不会透出来
    d.rectangle([0, 0, W, STATUS_H], fill=(250, 250, 250))
    d.text((70, 46), "9:41", font=F_STATUS, fill=(0, 0, 0))
    # 信号 / wifi / 电池
    for i in range(4):
        d.rectangle([W - 330 + i * 22, 80 - i * 10, W - 318 + i * 22, 92], fill=(0, 0, 0))
    d.arc([W - 220, 56, W - 160, 100], 200, 340, fill=(0, 0, 0), width=6)
    d.rounded_rectangle([W - 130, 56, W - 40, 96], radius=8, outline=(0, 0, 0), width=4)
    d.rectangle([W - 126, 64, W - 60, 88], fill=(0, 0, 0))


def draw_nav(img, title):
    d = ImageDraw.Draw(img)
    d.rectangle([0, STATUS_H, W, STATUS_H + NAV_H], fill=(250, 250, 250))
    d.text((60, STATUS_H + 36), title, font=F_TITLE, fill=(10, 10, 10))
    d.rectangle([0, STATUS_H + NAV_H, W, STATUS_H + NAV_H + 2], fill=(232, 232, 232))


def draw_home_bar(img):
    """iOS 底部小白条。真实截图里它下面是系统背景色（不透明），
    内容不会透出来 —— 所以先铺一层背景，再画横条。"""
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - HOME_BAR_ZONE, W, H], fill=(250, 250, 250))
    bw = 420
    d.rounded_rectangle([(W - bw) // 2, H - 30, (W + bw) // 2, H - 16],
                        radius=7, fill=(0, 0, 0))


def make_screenshot(content, scroll_y, kind, dyn=None, title="微信"):
    """从 content 里裁一个视口，加上固定覆盖层。"""
    img = Image.fromarray(content[scroll_y:scroll_y + H].copy())
    if kind == "chat":
        draw_status_bar(img, 0)
        draw_nav(img, title)
        d = ImageDraw.Draw(img)
        # 底部输入框（固定覆盖）
        d.rectangle([0, H - 200, W, H], fill=(247, 247, 247))
        d.rectangle([0, H - 200, W, H - 198], fill=(228, 228, 228))
        d.rounded_rectangle([40, H - 168, W - 150, H - 52], radius=16, fill=(255, 255, 255),
                            outline=(220, 220, 220), width=2)
        d.rounded_rectangle([W - 130, H - 168, W - 30, H - 52], radius=16, fill=(7, 193, 96))
    elif kind == "article":
        draw_status_bar(img, 0)
        draw_nav(img, "Safari")
    elif kind == "feed":
        draw_status_bar(img, 0)
        draw_nav(img, "小红书")
        d = ImageDraw.Draw(img)
        d.rectangle([0, H - 180, W, H], fill=(252, 252, 252))
        d.rectangle([0, H - 180, W, H - 178], fill=(230, 230, 230))
        for i in range(5):
            cx = int(W * (i + 0.5) / 5)
            d.rectangle([cx - 30, H - 140, cx + 30, H - 80], fill=(150, 150, 150))
    elif kind == "list":
        draw_status_bar(img, 0)
        draw_nav(img, "设置")

    # 动态内容：随内容一起滚动（真实的动图/视频在信息流里就是这样）
    dyn_region = None
    if dyn is not None:
        d = ImageDraw.Draw(img)
        abs_y = 2600                                  # 在"内容坐标系"里的固定位置
        vy = STATUS_H + NAV_H + (abs_y - scroll_y)    # 换算到视口坐标
        if STATUS_H + NAV_H < vy < H - 200:
            d.rectangle([60, vy, W - 60, vy + 420], fill=(20, 20, 20))
            d.ellipse([W // 2 - 60, vy + 160, W // 2 + 60, vy + 280],
                      fill=(int(60 + 150 * dyn), 60, int(240 - 150 * dyn)))
            dyn_region = (vy, vy + 420)

    draw_home_bar(img)
    return img, dyn_region


SCENARIOS = {
    "chat":    dict(content="chat",    step=(0.60, 0.80), dyn=False, title="微信"),
    "article": dict(content="article", step=(0.65, 0.85), dyn=False, title="Safari"),
    "feed":    dict(content="feed",    step=(0.55, 0.78), dyn=False, title="小红书"),
    "list":    dict(content="list",    step=(0.62, 0.80), dyn=False, title="设置"),
    "dynamic": dict(content="article", step=(0.60, 0.82), dyn=True,  title="B站"),
}


def stable_seed(name):
    """Python 的 hash() 对字符串是每进程随机化的（PYTHONHASHSEED），
    跨进程会得到不同的内容，测试就无法复现。用 crc32 保证稳定。"""
    import zlib
    return zlib.crc32(name.encode("utf-8")) % 10000


def build_all(seed=7):
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(seed)
    truth = {}
    for name, cfg in SCENARIOS.items():
        content = make_content(cfg["content"], seed=stable_seed(name))
        # 内容可视高度 = H - 状态栏 - 导航栏 - 底部栏
        bottom_bar = {"chat": 200, "feed": 180}.get(cfg["content"], 0)
        view_h = H - STATUS_H - NAV_H - bottom_bar
        shots = []
        scrolls = [0]
        cur = 0
        for i in range(4):
            frac = rng.uniform(*cfg["step"])
            cur = cur + int(frac * view_h)
            scrolls.append(cur)
        for i, s in enumerate(scrolls):
            dyn = (i / 4.0) if cfg["dyn"] else None
            img, _dyn_region = make_screenshot(content, s, cfg["content"], dyn=dyn, title=cfg["title"])
            p = os.path.join(OUT, f"{name}_{i}.png")
            img.save(p)
            shots.append(p)
        truth[name] = {
            "shots": shots,
            "scrolls": scrolls,
            "deltas": [scrolls[i + 1] - scrolls[i] for i in range(len(scrolls) - 1)],
            "content_top": STATUS_H + NAV_H,
            # 小白条是系统覆盖层，任何界面都在，必须计入底部覆盖层
            "content_bottom_bar": max(bottom_bar, HOME_BAR_ZONE),
        }
    return truth


if __name__ == "__main__":
    t = build_all()
    for k, v in t.items():
        print(k, "deltas =", v["deltas"])
    print("samples ->", OUT)
