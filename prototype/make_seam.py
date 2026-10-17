# -*- coding: utf-8 -*-
"""裁出接缝处的原分辨率局部图，用来肉眼确认有没有错位/重复。"""
from PIL import Image

import stitcher

cases = {
    "chat": 1525,
    "article": 1635,
    "feed": 1557,
    "list": 1534,
}

for name, d in cases.items():
    out = Image.open(f"out_{name}.png").convert("RGB")
    # 接缝位置：第一段内容高度（= 屏高 - top - bottom），即第二张图开始的地方
    grays = None
    # 直接用诊断里记录的内容高
    import numpy as np
    H = 2622
    top = 321
    bottom = {"chat": 200, "article": 34, "feed": 180, "list": 34}[name]
    seam = H - top - bottom
    y0 = max(0, seam - 300)
    y1 = min(out.height, seam + 300)
    crop = out.crop((0, y0, out.width, y1))
    crop.save(f"seam_{name}.png")
    print(f"{name}: seam at y={seam}, crop {y0}-{y1}, size {crop.size}")
