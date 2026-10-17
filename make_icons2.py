"""Splice 候选图标 第二轮：深色底 + 更清晰的图形语言。

设计原则（来自第一轮的教训）：
- 第一轮全是白底黑图，在主屏上和别的图标挤在一起缺乏辨识度，且"白底"其实
  和系统默认图标撞色。这一轮改成深色圆角底 + 白色图形，对比强、缩小后仍可读。
- 图形语言只保留一种动作：**两段 -> 一段**（拼接），不画"内容线"这种细节，
  因为图标在桌面上只有 60pt，细节全糊。
"""
import os
from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
SS = 4
S = SIZE * SS

DARK = (12, 12, 14)
DARK2 = (34, 34, 38)
WHITE = (255, 255, 255)
GREY = (120, 120, 126)


def canvas(bg=DARK, rounded_bg=True):
    img = Image.new("RGB", (S, S), bg)
    d = ImageDraw.Draw(img)
    if rounded_bg:
        pass  # iOS 会自己切圆角，这里画满即可
    return img, d


def rrect(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


# ------------------------------------------------------------ G 两段合一（深色）
def icon_g():
    """上下两块深灰，中间一条白色粗接缝，接缝两端各一个小缺口 —— 拼接。"""
    img, d = canvas()
    w = int(0.400 * S)
    h = int(0.620 * S)
    x0 = (S - w) // 2
    y0 = (S - h) // 2
    x1, y1 = x0 + w, y0 + h
    rrect(d, [x0, y0, x1, y1], int(0.075 * S), DARK2)

    # 接缝：白色横条，贯穿但两端留 8% 缺口，暗示"这是两张拼的"
    cy = (y0 + y1) // 2
    th = int(0.032 * S)
    inset = int(0.075 * S)
    d.rounded_rectangle([x0 + inset, cy - th // 2, x1 - inset, cy + th // 2],
                        radius=th // 2, fill=WHITE)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


# ------------------------------------------------------------ H 台阶（深色）
def icon_h():
    """左侧一条高、右侧一条矮，中间错开 —— 像两段不同长度的截图对齐。"""
    img, d = canvas()
    bw = int(0.190 * S)
    gap = int(0.070 * S)
    total_w = bw * 2 + gap
    x0 = (S - total_w) // 2
    h1 = int(0.560 * S)
    h2 = int(0.380 * S)
    cy = S // 2

    rrect(d, [x0, cy - h1 // 2, x0 + bw, cy + h1 // 2], int(0.048 * S), WHITE)
    x2 = x0 + bw + gap
    rrect(d, [x2, cy - h2 // 2, x2 + bw, cy + h2 // 2], int(0.048 * S), GREY)

    # 中间一条细白横线把两段连起来
    th = int(0.020 * S)
    d.rectangle([x0 + bw, cy - th // 2, x2, cy + th // 2], fill=WHITE)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


# ------------------------------------------------------------ I 长图 + 缝合针脚
def icon_i():
    """一条很高的白色长图，中间一道虚线的缝，两端超出长图 —— 像真的缝起来。"""
    img, d = canvas()
    w = int(0.310 * S)
    h = int(0.700 * S)
    x0 = (S - w) // 2
    y0 = (S - h) // 2
    x1, y1 = x0 + w, y0 + h
    rrect(d, [x0, y0, x1, y1], int(0.070 * S), WHITE)

    # 长图内部：上下两段用深色隔开（视觉上"两段"）
    cy = (y0 + y1) // 2
    th = int(0.030 * S)
    d.rectangle([x0, cy - th // 2, x1, cy + th // 2], fill=DARK)

    # 缝合线：虚线穿过接缝，两端各出头一点
    dash = int(0.038 * S)
    dgap = int(0.026 * S)
    lth = int(0.014 * S)
    lx0 = x0 - int(0.035 * S)
    lx1 = x1 + int(0.035 * S)
    x = lx0
    while x < lx1:
        xe = min(x + dash, lx1)
        d.rounded_rectangle([x, cy - lth // 2, xe, cy + lth // 2],
                            radius=lth // 2, fill=DARK if x > x0 - 1 and xe < x1 + 1 else WHITE)
        x = xe + dgap
    return img.resize((SIZE, SIZE), Image.LANCZOS)


# ------------------------------------------------------------ J 字母 S（修正）
def icon_j():
    """深色圆角底 + 白色 S，S 中间被一道横向缺口切断。用字体保证形状正确。"""
    img, d = canvas()
    side = int(0.720 * S)
    x0 = (S - side) // 2
    y0 = (S - side) // 2
    rrect(d, [x0, y0, x0 + side, y0 + side], int(0.235 * S), DARK2)

    font = ImageFont.truetype("C:\\Windows\\Fonts\\seguibl.ttf", int(0.560 * S))
    txt = "S"
    bb = d.textbbox((0, 0), txt, font=font)
    tw, th_ = bb[2] - bb[0], bb[3] - bb[1]
    tx = S // 2 - tw // 2 - bb[0]
    ty = S // 2 - th_ // 2 - bb[1]
    d.text((tx, ty), txt, font=font, fill=WHITE)

    # 中间横切一道，露出底色 —— 表达"两段"
    cy = S // 2
    cut = int(0.026 * S)
    d.rectangle([x0 + int(0.02 * S), cy - cut // 2,
                 x0 + side - int(0.02 * S), cy + cut // 2], fill=DARK2)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


# ------------------------------------------------------------ K 卷轴
def icon_k():
    """长图卷成一卷的意象：一个白色圆角竖条 + 底部一条深色横带（卷边）。"""
    img, d = canvas()
    w = int(0.320 * S)
    h = int(0.640 * S)
    x0 = (S - w) // 2
    y0 = (S - h) // 2
    x1, y1 = x0 + w, y0 + h
    rrect(d, [x0, y0, x1, y1], int(0.070 * S), WHITE)

    # 上三分之一处一条深色细缝
    cy = y0 + int(h * 0.36)
    th = int(0.024 * S)
    d.rectangle([x0 + int(0.055 * S), cy - th // 2,
                 x1 - int(0.055 * S), cy + th // 2], fill=DARK)
    # 下三分之一再来一条
    cy2 = y0 + int(h * 0.68)
    d.rectangle([x0 + int(0.055 * S), cy2 - th // 2,
                 x1 - int(0.055 * S), cy2 + th // 2], fill=DARK)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


# ------------------------------------------------------------ L 渐变长图
def icon_l():
    """竖直长图，从白渐变到深灰，中间一条深色接缝 —— 最有"高级感"的一版。"""
    img, d = canvas()
    w = int(0.330 * S)
    h = int(0.680 * S)
    x0 = (S - w) // 2
    y0 = (S - h) // 2
    x1, y1 = x0 + w, y0 + h

    grad = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grad)
    for yy in range(h):
        t = yy / max(h - 1, 1)
        v = int(255 - t * 190)
        gd.line([(0, yy), (w, yy)], fill=(v, v, v))
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=int(0.070 * S), fill=255)
    img.paste(grad, (x0, y0), m)
    d = ImageDraw.Draw(img)

    cy = (y0 + y1) // 2
    th = int(0.030 * S)
    d.rectangle([x0 + int(0.048 * S), cy - th // 2,
                 x1 - int(0.048 * S), cy + th // 2], fill=DARK)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


ICONS = [("G", "两段合一", icon_g),
         ("H", "错落两段", icon_h),
         ("I", "长图缝合", icon_i),
         ("J", "字母S", icon_j),
         ("K", "双接缝", icon_k),
         ("L", "渐变长图", icon_l)]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "icons_preview")
    os.makedirs(out_dir, exist_ok=True)

    imgs = []
    for key, name, fn in ICONS:
        im = fn()
        p = os.path.join(out_dir, "%s_%s.png" % (key, name))
        im.save(p, "PNG")
        print("wrote", p)
        imgs.append((key, name, im))

    cell = 340
    gap = 18
    cols, rows = 3, 2
    lab = 34
    cw = cell * cols + gap * (cols + 1)
    ch = (cell + lab) * rows + gap * (rows + 1)
    sheet = Image.new("RGB", (cw, ch), (245, 245, 247))
    sd = ImageDraw.Draw(sheet)
    for i, (key, name, im) in enumerate(imgs):
        c, r = i % cols, i // cols
        x = gap + c * (cell + gap)
        y = gap + r * (cell + lab + gap)
        thumb = im.resize((cell, cell), Image.LANCZOS)
        m = Image.new("L", (cell, cell), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, cell - 1, cell - 1],
                                            radius=int(cell * 0.22), fill=255)
        sheet.paste(thumb, (x, y), m)
        sd.text((x + 6, y + cell + 8), "%s  %s" % (key, name), fill=(40, 40, 40))
    p = os.path.join(out_dir, "_sheet2.png")
    sheet.save(p, "PNG")
    print("wrote", p, sheet.size)


if __name__ == "__main__":
    main()
