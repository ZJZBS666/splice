"""生成 Splice 的候选 App 图标（1024x1024 PNG，多方案对比用）。

每个方案画完都超采样 4 倍再缩小，边缘才平滑。
输出到 splice/icons_preview/，另外拼一张 contact sheet 方便挑选。
"""
import os
from PIL import Image, ImageDraw

SIZE = 1024
SS = 4
S = SIZE * SS

BG = (255, 255, 255)
INK = (10, 10, 10)
INK_SOFT = (58, 58, 60)
LINE = (255, 255, 255)
GREY = (168, 168, 172)


def new_canvas():
    img = Image.new("RGB", (S, S), BG)
    return img, ImageDraw.Draw(img)


def rrect(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


# ---------------------------------------------------------------- A 长图+内容线
def icon_a():
    """一条竖直长图，里面有几条浅灰文字行，两条白接缝横线。"""
    img, d = new_canvas()
    w = int(0.300 * S)
    h = int(0.640 * S)
    x0 = (S - w) // 2
    y0 = (S - h) // 2
    x1, y1 = x0 + w, y0 + h
    rrect(d, [x0, y0, x1, y1], int(0.062 * S), INK)

    # 模拟内容：几组横线，避开接缝位置
    pad = int(0.055 * S)
    th = int(0.0165 * S)
    seam_ys = [int(y0 + h * f) for f in (0.3333, 0.6667)]
    y = y0 + int(0.055 * S)
    k = 0
    while y < y1 - int(0.06 * S):
        if any(abs(y - sy) < int(0.055 * S) for sy in seam_ys):
            y += th + int(0.022 * S)
            continue
        lw = w - 2 * pad
        if k % 4 == 3:                      # 每 4 行短一截，像段落末尾
            lw = int(lw * 0.45)
        d.rounded_rectangle([x0 + pad, y, x0 + pad + lw, y + th],
                            radius=th // 2, fill=INK_SOFT)
        y += th + int(0.022 * S)
        k += 1

    # 接缝
    sh = int(0.0125 * S)
    inset = int(0.048 * S)
    for sy in seam_ys:
        d.rectangle([x0 + inset, sy - sh // 2, x1 - inset, sy + sh // 2], fill=LINE)

    return img.resize((SIZE, SIZE), Image.LANCZOS)


# ---------------------------------------------------------------- B 堆叠卡片
def icon_b():
    """三张独立的圆角卡片上下叠，之间有缝，像"几张截图"。"""
    img, d = new_canvas()
    w = int(0.360 * S)
    card_h = int(0.185 * S)
    gap = int(0.030 * S)
    total = card_h * 3 + gap * 2
    x0 = (S - w) // 2
    y0 = (S - total) // 2
    for i in range(3):
        y = y0 + i * (card_h + gap)
        # 中间那张稍微深一点，视觉上有"正在拼接"的层次
        col = INK if i != 1 else INK_SOFT
        rrect(d, [x0, y, x0 + w, y + card_h], int(0.042 * S), col)
        # 每张里两条内容线
        pad = int(0.052 * S)
        th = int(0.0150 * S)
        for j in range(2):
            yy = y + int(0.050 * S) + j * (th + int(0.026 * S))
            lw = w - 2 * pad
            if j == 1:
                lw = int(lw * 0.62)
            d.rounded_rectangle([x0 + pad, yy, x0 + pad + lw, yy + th],
                                radius=th // 2, fill=(255, 255, 255))
    return img.resize((SIZE, SIZE), Image.LANCZOS)


# ---------------------------------------------------------------- C 重叠消隐
def icon_c():
    """上下两块深色，中间重叠区用斜纹表示"重复部分被去掉"。"""
    img, d = new_canvas()
    w = int(0.400 * S)
    blk = int(0.290 * S)
    ov = int(0.120 * S)
    total = blk * 2 - ov
    x0 = (S - w) // 2
    y0 = (S - total) // 2

    top = [x0, y0, x0 + w, y0 + blk]
    bot = [x0, y0 + blk - ov, x0 + w, y0 + total]
    rrect(d, top, int(0.055 * S), INK)
    rrect(d, bot, int(0.055 * S), INK)

    # 重叠带画斜纹（浅色），表达"这段是重复的"
    ovt, ovb = bot[1], top[3]
    band = Image.new("RGB", (w, ovb - ovt), INK)
    bd = ImageDraw.Draw(band)
    step = int(0.030 * S)
    for i in range(-ovb + ovt, w + ovb - ovt, step * 2):
        bd.line([(i, 0), (i + (ovb - ovt), ovb - ovt)], fill=(255, 255, 255), width=int(0.010 * S))
    mask = Image.new("L", (w, ovb - ovt), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, ovb - ovt - 1],
                                           radius=int(0.020 * S), fill=255)
    img.paste(band, (x0, ovt), mask)
    d = ImageDraw.Draw(img)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


# ---------------------------------------------------------------- D 虚线缝合
def icon_d():
    """一条竖直长图，正中间一道白色虚线贯穿，像缝合。"""
    img, d = new_canvas()
    w = int(0.330 * S)
    h = int(0.660 * S)
    x0 = (S - w) // 2
    y0 = (S - h) // 2
    x1, y1 = x0 + w, y0 + h
    rrect(d, [x0, y0, x1, y1], int(0.058 * S), INK)

    cy = (y0 + y1) // 2
    dash = int(0.040 * S)
    gap = int(0.030 * S)
    th = int(0.0145 * S)
    inset = int(0.042 * S)
    x = x0 + inset
    while x < x1 - inset:
        xe = min(x + dash, x1 - inset)
        d.rectangle([x, cy - th // 2, xe, cy + th // 2], fill=LINE)
        x = xe + gap
    return img.resize((SIZE, SIZE), Image.LANCZOS)


# ---------------------------------------------------------------- E 对折渐变
def icon_e():
    """长图上下两段不同深浅，中间一条白线 —— 最克制的一版。"""
    img, d = new_canvas()
    w = int(0.330 * S)
    h = int(0.660 * S)
    x0 = (S - w) // 2
    y0 = (S - h) // 2
    x1, y1 = x0 + w, y0 + h
    rrect(d, [x0, y0, x1, y1], int(0.058 * S), INK)

    # 下半段叠一层浅灰，制造"两段"的感觉
    mid = (y0 + y1) // 2
    mask = Image.new("L", (w, mid - y0), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, mid - y0 - 1],
                                           radius=int(0.020 * S), fill=255)
    seg = Image.new("RGB", (w, mid - y0), INK_SOFT)
    img.paste(seg, (x0, mid), mask)
    d = ImageDraw.Draw(img)

    th = int(0.017 * S)
    d.rectangle([x0, mid - th // 2, x1, mid + th // 2], fill=LINE)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


# ---------------------------------------------------------------- F 字母 S
def icon_f():
    """深色圆角方块里一个白色 S，S 的中间断开一道缝。"""
    img, d = new_canvas()
    side = int(0.680 * S)
    x0 = (S - side) // 2
    y0 = (S - side) // 2
    rrect(d, [x0, y0, x0 + side, y0 + side], int(0.225 * S), INK)

    # 用两段圆弧拼一个 S
    cx = S // 2
    r = int(0.150 * S)
    lw = int(0.042 * S)
    box_up = [cx - r, y0 + int(0.150 * S), cx + r, y0 + int(0.150 * S) + 2 * r]
    box_dn = [cx - r, y0 + side - int(0.150 * S) - 2 * r, cx + r, y0 + side - int(0.150 * S)]
    d.arc(box_up, start=200, end=20, fill=LINE, width=lw)
    d.arc(box_dn, start=20, end=200, fill=LINE, width=lw)

    # 中间横缝
    th = int(0.020 * S)
    cy = (y0 + side // 2)
    d.rectangle([cx - int(0.155 * S), cy - th // 2, cx + int(0.155 * S), cy + th // 2], fill=BG)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


ICONS = [("A", "长图+内容线", icon_a),
         ("B", "三张卡片堆叠", icon_b),
         ("C", "重叠消隐", icon_c),
         ("D", "虚线缝合", icon_d),
         ("E", "对折两段", icon_e),
         ("F", "字母 S", icon_f)]


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

    # contact sheet: 3 列 x 2 行
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
        # 圆角裁一下，更像真机图标
        m = Image.new("L", (cell, cell), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, cell - 1, cell - 1], radius=int(cell * 0.22), fill=255)
        sheet.paste(thumb, (x, y), m)
        sd.text((x + 6, y + cell + 8), "%s  %s" % (key, name), fill=(40, 40, 40))
    p = os.path.join(out_dir, "_sheet.png")
    sheet.save(p, "PNG")
    print("wrote", p, sheet.size)


if __name__ == "__main__":
    main()
