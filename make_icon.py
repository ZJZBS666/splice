"""生成 Splice 的正式 App 图标（1024x1024 PNG）。

设计（用户从 12 个候选里选定的 A 方案）：
  极简白底 + 一条竖直的黑色圆角长图，长图里画几行灰色文字横线，
  中间两条接缝横线 —— 直接表达"几张截图拼成一张长图"。
  上面那条接缝用白色；下面那条用 #FC8E03（橙），给纯黑白的画面一个落点。

选 A 而不是用深色底方案的理由：用户在 Windows 上看到的就是白底效果，
在浅色壁纸的主屏上白底图标更干净；且"长图 + 内容行"最直白地说明用途。
"""
import os
from PIL import Image, ImageDraw

SIZE = 1024
SS = 4  # 超采样倍数，画完再缩小，边缘才平滑
S = SIZE * SS

BG = (255, 255, 255)
INK = (10, 10, 10)
INK_SOFT = (58, 58, 60)
# 下面那条接缝用的橙色 #FC8E03
ACCENT = (0xFC, 0x8E, 0x03)


def main():
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)

    # 长图本体：竖直黑色圆角矩形
    w = int(0.300 * S)
    h = int(0.640 * S)
    x0 = (S - w) // 2
    y0 = (S - h) // 2
    x1, y1 = x0 + w, y0 + h
    d.rounded_rectangle([x0, y0, x1, y1], radius=int(0.062 * S), fill=INK)

    # 模拟内容：几组灰色横线，避开接缝位置
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

    # 两条接缝：横线两端内缩，保持外轮廓仍是完整的一张长图。
    # 上面一条白色，下面一条 #FC8E03。
    sh = int(0.0125 * S)
    inset = int(0.048 * S)
    seam_colors = [BG, ACCENT]
    for sy, col in zip(seam_ys, seam_colors):
        d.rectangle([x0 + inset, sy - sh // 2, x1 - inset, sy + sh // 2], fill=col)

    img = img.resize((SIZE, SIZE), Image.LANCZOS)

    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "Splice", "Resources", "Assets.xcassets",
                           "AppIcon.appiconset")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "AppIcon-1024.png")
    img.save(out, "PNG")
    print("wrote", out, img.size)


if __name__ == "__main__":
    main()
