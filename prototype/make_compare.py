# -*- coding: utf-8 -*-
"""生成"原截图 -> 拼接长图"的可视对比图，用于人工检查接缝。"""
import numpy as np
from PIL import Image, ImageDraw

import gen_samples
import stitcher

truth = gen_samples.build_all()

for name in truth:
    shots = [Image.open(p).convert("RGB") for p in truth[name]["shots"]]
    out = Image.open(f"out_{name}.png").convert("RGB")

    # 左边：4 张原截图横向排开（缩放到高 900）；右边：长图（缩放到高 900）
    TH = 900
    tiles = []
    for s in shots:
        w = int(s.width * TH / s.height)
        tiles.append(s.resize((w, TH), Image.LANCZOS))
    strip_w = sum(t.width for t in tiles) + 10 * (len(tiles) - 1)
    strip = Image.new("RGB", (strip_w, TH), (240, 240, 240))
    x = 0
    for t in tiles:
        strip.paste(t, (x, 0))
        x += t.width + 10

    ow = max(60, int(out.width * TH / out.height))
    longimg = out.resize((ow, TH), Image.LANCZOS)

    gap = 40
    canvas = Image.new("RGB", (strip_w + gap + ow, TH + 50), (255, 255, 255))
    canvas.paste(strip, (0, 50))
    canvas.paste(longimg, (strip_w + gap, 50))
    d = ImageDraw.Draw(canvas)
    d.text((10, 18), f"Splice test: {name}  ({len(shots)} shots -> 1 long image)", fill=(0, 0, 0))
    d.text((strip_w + gap + 10, 18), f"{out.width}x{out.height}", fill=(0, 0, 0))
    canvas.save(f"compare_{name}.png")
    print("saved compare_" + name + ".png", canvas.size)
