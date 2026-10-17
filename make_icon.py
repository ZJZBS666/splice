"""生成 Splice 的 App 图标（1024x1024 PNG）。

设计：极简白底 + 一条竖直的黑色长图，中间两处白色接缝横线微微出头，
像"两段拼在一起"的痕迹。符合 App 的极简白底风格。
"""
import os
from PIL import Image, ImageDraw

SIZE = 1024
SS = 4  # 超采样倍数，画完再缩小，边缘才平滑


def rounded(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def main():
    S = SIZE * SS
    img = Image.new("RGB", (S, S), (255, 255, 255))
    d = ImageDraw.Draw(img)

    # 长图本体：竖直黑色圆角矩形
    col_w = int(0.3125 * S)          # 320/1024
    col_h = int(0.6094 * S)          # 624/1024
    x0 = (S - col_w) // 2
    y0 = (S - col_h) // 2
    x1 = x0 + col_w
    y1 = y0 + col_h
    rounded(d, [x0, y0, x1, y1], int(0.039 * S), (10, 10, 10))

    # 两条接缝：白色横线，两端内缩，保持外轮廓仍是完整的一张长图
    seam_h = int(0.0137 * S)         # 14/1024
    inset = int(0.055 * S)           # 56/1024
    for frac in (0.3333, 0.6667):
        cy = int(y0 + col_h * frac)
        d.rectangle([x0 + inset, cy - seam_h // 2,
                     x1 - inset, cy + seam_h // 2 + 1],
                    fill=(255, 255, 255))

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
