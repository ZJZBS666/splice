"""画一张「设置页改版前 / 改版后」的对照示意图。

不是真机截图，是按 SwiftUI 里的实际数值（pt、圆角半径、间距、字号）
1:1 换算成像素画出来的示意图，用来在装包之前先确认排版方向。

用法：
    python mock_settings.py
输出：
    E:\\DeepSeek\\本地电脑\\Splice-设置页对比.png
"""

import os

from PIL import Image, ImageDraw, ImageFont

# ---- 全局尺度 ----
S = 2                       # 2x 像素
W_PT, H_PT = 402, 874       # iPhone 16 Pro 逻辑尺寸
W, H = W_PT * S, H_PT * S

REG = r"C:\Windows\Fonts\msyh.ttc"
BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

# iOS 语义色（浅色）
C_PAGE_GROUPED = (242, 242, 247)   # systemGroupedBackground
C_CARD = (255, 255, 255)           # systemBackground
C_LABEL = (0, 0, 0)
C_SECONDARY = (60, 60, 67, 153)    # secondaryLabel ~60%
C_TERTIARY = (60, 60, 67, 76)      # tertiaryLabel ~30%
C_SEG_TRACK = (239, 239, 240)      # 767680 @ 12%
C_SEP = (60, 60, 67, 74)           # separator


def font(path, pt):
    return ImageFont.truetype(path, int(pt * S))


F_NAV = font(BOLD, 17)
F_SECT = font(BOLD, 11)
F_BODY = font(REG, 15)
F_DETAIL = font(REG, 14)
F_HINT = font(REG, 12)
F_ABOUT = font(REG, 13)
F_SEG = font(REG, 13)


def px(v):
    return int(round(v * S))


def rounded(dr, box, r, fill, outline=None, width=1):
    dr.rounded_rectangle(box, radius=px(r), fill=fill, outline=outline, width=width)


def text(dr, xy, s, f, fill):
    dr.text((px(xy[0]), px(xy[1])), s, font=f, fill=fill)


def text_w(dr, s, f):
    return dr.textlength(s, font=f) / S


def wrap(dr, s, f, max_w):
    """按字符宽度硬折行（中文没有空格可断）。"""
    lines, cur = [], ""
    for ch in s:
        if text_w(dr, cur + ch, f) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def draw_segment(dr, x, y, w, h, labels, active=0):
    rounded(dr, [px(x), px(y), px(x + w), px(y + h)], 8, C_SEG_TRACK)
    seg_w = (w - 4) / len(labels)
    for i, lab in enumerate(labels):
        sx = x + 2 + i * seg_w
        if i == active:
            rounded(dr, [px(sx), px(y + 2), px(sx + seg_w), px(y + h - 2)],
                    7, C_CARD)
            # 选中投影（简化成一条浅灰线）
            dr.line([px(sx + 2), px(y + h - 1), px(sx + seg_w - 2), px(y + h - 1)],
                    fill=(0, 0, 0, 18), width=px(0.5))
        tw = text_w(dr, lab, F_SEG)
        text(dr, (sx + (seg_w - tw) / 2, y + (h - 13) / 2 - 1), lab, F_SEG,
             C_LABEL if i == active else (60, 60, 67, 153))


def draw_toggle(dr, x, y, w=51, h=31, on=True):
    rounded(dr, [px(x), px(y), px(x + w), px(y + h)], h / 2,
            (0, 0, 0) if on else (229, 229, 234))
    knob = h - 4
    kx = x + w - 2 - knob if on else x + 2
    dr.ellipse([px(kx), px(y + 2), px(kx + knob), px(y + 2 + knob)], fill=C_CARD)


def draw_status_bar(dr):
    text(dr, (26, 14), "2:37", font(BOLD, 15), C_LABEL)


def draw_nav(dr, y):
    tw = text_w(dr, "设置", F_NAV)
    text(dr, ((W_PT - tw) / 2, y), "设置", F_NAV, C_LABEL)
    # 「完成」
    dw = text_w(dr, "完成", F_NAV)
    text(dr, (W_PT - 20 - dw, y), "完成", F_NAV, C_LABEL)


def card_box(dr, x, y, w, h, r=14):
    rounded(dr, [px(x), px(y), px(x + w), px(y + h)], r, C_CARD)


def draw_new(dr):
    """改版后：grouped 底 + 白色分组卡片。"""
    dr.rectangle([0, 0, W, H], fill=C_PAGE_GROUPED)
    draw_status_bar(dr)
    draw_nav(dr, 34)

    pad = 20           # 页面左右边距
    inner = 16         # 卡片内左右边距
    cw = W_PT - pad * 2
    iw = cw - inner * 2
    y = 84

    # ---- 外观 ----
    text(dr, (pad + 4, y), "外观", F_SECT, C_TERTIARY)
    y += 8 + 11          # sectionTitle 高 + 8pt 间距
    hint_lines = wrap(dr, "选「跟随系统」时，Splice 会跟着 iPhone 的浅色/深色设置自动切换。", F_HINT, iw)
    ch = 12 + 32 + 10 + len(hint_lines) * 16 + 12
    card_box(dr, pad, y, cw, ch)
    draw_segment(dr, pad + inner, y + 12, iw, 32,
                 ["跟随系统", "浅色", "深色"], active=0)
    hy = y + 12 + 32 + 10
    for ln in hint_lines:
        text(dr, (pad + inner, hy), ln, F_HINT, C_TERTIARY)
        hy += 16
    y += ch + 22

    # ---- 识别范围 ----
    text(dr, (pad + 4, y), "识别范围", F_SECT, C_TERTIARY)
    y += 8 + 11
    ch = 12 + 32 + 10 + 16 + 12
    card_box(dr, pad, y, cw, ch)
    draw_segment(dr, pad + inner, y + 12, iw, 32,
                 ["10 分钟", "30 分钟", "1 小时", "3 小时"], active=1)
    text(dr, (pad + inner, y + 12 + 32 + 10), "Splice 只在这个时间范围里找截图。", F_HINT, C_TERTIARY)
    y += ch + 22

    # ---- 顶部保留 ----
    text(dr, (pad + 4, y), "顶部保留", F_SECT, C_TERTIARY)
    y += 8 + 11
    ch = 12 + 40 + 10 + 16 + 12
    card_box(dr, pad, y, cw, ch)
    text(dr, (pad + inner, y + 12 + 1), "保留第一张的状态栏和导航栏", F_BODY, C_LABEL)
    text(dr, (pad + inner, y + 12 + 21), "关掉后长图顶部直接是内容", F_HINT, C_TERTIARY)
    draw_toggle(dr, pad + cw - inner - 51, y + 12 + 5)
    text(dr, (pad + inner, y + 12 + 40 + 10), "顶部这一条只会保留一次。", F_HINT, C_TERTIARY)
    y += ch + 22

    # ---- 关于 ----
    text(dr, (pad + 4, y), "关于", F_SECT, C_TERTIARY)
    y += 8 + 11
    about = "Splice 会把最近的截图按时间顺序自动识别重叠部分，去掉重复后拼成一张长图。识别不出来时会在接缝处加一条细分隔线，你可以拖动接缝微调。"
    lines = wrap(dr, about, F_ABOUT, iw)
    ch = 12 + len(lines) * 19 + 12
    card_box(dr, pad, y, cw, ch)
    ay = y + 12
    for ln in lines:
        text(dr, (pad + inner, ay), ln, F_ABOUT, C_SECONDARY)
        ay += 19
    y += ch + 22

    # ---- 作者 / 项目源码 ----
    ch = 12 + 50 + 1 + 50 + 12
    card_box(dr, pad, y, cw, ch)
    ry = y + 12
    for icon, title, detail in (("person", "作者", "ZJZBS666"),
                                ("code", "项目源码", "ZJZBS666/splice")):
        # 图标位置先画一个占位圆角方块
        rounded(dr, [px(pad + inner + 8), px(ry + 15), px(pad + inner + 32), px(ry + 39)],
                6, (0, 0, 0, 22))
        text(dr, (pad + inner + 52, ry + 16), title, F_BODY, C_LABEL)
        dw = text_w(dr, detail, F_DETAIL)
        text(dr, (pad + cw - inner - 8 - 14 - dw, ry + 17), detail, F_DETAIL, C_SECONDARY)
        # chevron
        cx = pad + cw - inner - 8 - 6
        dr.line([px(cx), px(ry + 20), px(cx + 5), px(ry + 25)], fill=(60, 60, 67, 76), width=px(1.6))
        dr.line([px(cx + 5), px(ry + 25), px(cx), px(ry + 30)], fill=(60, 60, 67, 76), width=px(1.6))
        ry += 50
        if title == "作者":
            dr.line([px(pad + inner + 44), px(ry), px(pad + cw - inner), px(ry)],
                    fill=C_SEP, width=px(0.5))


def draw_old(dr):
    """改版前：白底、无卡片、只有小标题分隔。"""
    dr.rectangle([0, 0, W, H], fill=C_CARD)
    draw_status_bar(dr)
    draw_nav(dr, 34)

    pad = 24
    iw = W_PT - pad * 2
    y = 84

    text(dr, (pad, y), "外观", F_SECT, C_TERTIARY)
    y += 11 + 10
    draw_segment(dr, pad, y, iw, 32, ["跟随系统", "浅色", "深色"], active=0)
    y += 32 + 8
    for ln in wrap(dr, "选「跟随系统」时，Splice 会跟着 iPhone 的浅色/深色设置自动切换。", F_HINT, iw):
        text(dr, (pad, y), ln, F_HINT, C_TERTIARY)
        y += 16
    y += 26

    text(dr, (pad, y), "识别范围", F_SECT, C_TERTIARY)
    y += 11 + 10
    draw_segment(dr, pad, y, iw, 32, ["10 分钟", "30 分钟", "1 小时", "3 小时"], active=1)
    y += 32 + 8
    text(dr, (pad, y), "Splice 只在这个时间范围里找截图。", F_HINT, C_TERTIARY)
    y += 16 + 26

    text(dr, (pad, y), "顶部保留", F_SECT, C_TERTIARY)
    y += 11 + 10
    text(dr, (pad, y + 1), "保留第一张的状态栏和导航栏", F_BODY, C_LABEL)
    text(dr, (pad, y + 21), "关掉后长图顶部直接是内容", F_HINT, C_TERTIARY)
    draw_toggle(dr, W_PT - pad - 51, y + 5)
    y += 40 + 26

    text(dr, (pad, y), "关于", F_SECT, C_TERTIARY)
    y += 11 + 10
    for ln in wrap(dr, "Splice 会把最近的截图按时间顺序自动识别重叠部分，去掉重复后拼成一张长图。识别不出来时会在接缝处加一条细分隔线，你可以拖动接缝微调。", F_ABOUT, iw):
        text(dr, (pad, y), ln, F_ABOUT, C_SECONDARY)
        y += 19

    y += 18
    dr.line([0, px(y), W, px(y)], fill=C_SEP, width=px(0.5))
    ry = y
    for title, detail in (("作者", "ZJZBS666"), ("项目源码", "ZJZBS666/splice")):
        rounded(dr, [px(24), px(ry + 15), px(48), px(ry + 39)], 6, (0, 0, 0, 22))
        text(dr, (24 + 24 + 12, ry + 16), title, F_BODY, C_LABEL)
        dw = text_w(dr, detail, F_DETAIL)
        text(dr, (W_PT - 24 - 14 - dw, ry + 17), detail, F_DETAIL, C_SECONDARY)
        ry += 50
        dr.line([px(52), px(ry), px(W_PT), px(ry)], fill=C_SEP, width=px(0.5))


def main():
    gap = 24
    label_h = 78
    canvas = Image.new("RGB", (W * 2 + gap * 3, H + gap * 2 + label_h), (238, 238, 241))
    dr = ImageDraw.Draw(canvas, "RGBA")

    for i, (title, sub, fn) in enumerate((
        ("改版前", "白底平铺，圆角半径小、只有按钮有圆角", draw_old),
        ("改版后", "分组卡片 + 连续曲率（continuous）圆角", draw_new),
    )):
        panel = Image.new("RGB", (W, H), C_CARD)
        pdr = ImageDraw.Draw(panel, "RGBA")
        fn(pdr)
        x = gap + i * (W + gap)
        canvas.paste(panel, (x, label_h + gap))
        f1, f2 = font(BOLD, 16), font(REG, 12)
        tw = text_w(dr, title, f1)
        dr.text((x + (W - tw) / 2, 10), title, font=f1, fill=(30, 30, 30))
        sw = text_w(dr, sub, f2)
        dr.text((x + (W - sw) / 2, 48), sub, font=f2, fill=(120, 120, 125))
        dr.rectangle([x, label_h + gap, x + W, label_h + gap + H],
                     outline=(200, 200, 205), width=2)

    out = r"E:\DeepSeek\本地电脑\Splice-设置页对比.png"
    canvas.save(out, "PNG")
    print("wrote", out, canvas.size)


if __name__ == "__main__":
    main()
