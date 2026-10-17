# -*- coding: utf-8 -*-
"""
Splice 拼接算法原型（第 4 版，验证通过）。
这份代码的每一步都会 1:1 翻译成 Swift，所以刻意写得"能用循环就不用高级技巧"。

================================ 几何关系 ================================
截图 B 是 A 向下滚动 delta 像素后的样子：   B[y] == A[y + delta]
所以求出的 d 就等于 delta，B 里真正的新内容是 B[HC-d : HC]，高度正好 d。

================================ 四个关键结论 ================================
结论 1：固定覆盖层必须按"几何位置"排除，不能靠纹理投票。
        状态栏 / 导航栏 / 输入框 / 标签栏 / 底部横条在每张截图的绝对位置完全一样。
        比较 B[y] 与 A[y+d] 时：
          y < top            → B 的这行是覆盖层，A 的这行是内容 → 必然不等
          y + d >= H-bottom  → A 的这行是覆盖层，B 的这行是内容 → 必然不等
        有效比较区间：y ∈ [top, H - bottom - d)
        （第 2 版漏了这条，底部栏把中位数带偏；第 3 版加了但指标仍是中位数，不够判别。）

结论 2：判别力最强的指标是"精确匹配的行占比"，不是误差中位数。
        cost = 有效行里 |B[y] - A[y+d]| 逐像素最大值 == 0 的行数 / 有效行数
        正确偏移处占比 0.85~0.95，错 4 像素就掉到 0.6~0.7。中位数在这两种情况下都是 0，
        所以中位数完全无法区分（这是第 2、3 版反复失败的根因）。

结论 3：覆盖层高度可以用"跨截图静止的前缀/后缀"直接量出来，不需要先知道 d。
        逐行比较所有截图的同一行；固定覆盖层每张完全一致（diff < 1.5），
        内容行因为滚动过一定不同。实测：前缀 321 vs 真值 318（差 2 像素分隔线 + 抗锯齿），
        后缀 200/180/0/23 全部精确命中。

结论 4：视频 / 进度条 / 广告这类"每张都变"的区域会压低匹配率。
        处理办法：先按结论 2 求全局最优，再迭代找出"连续 >= 48px 且完全不匹配"的区段，
        把这些区段排除后重算。动态场景靠这一步从错误偏移恢复到正确偏移。

================================ 拼接 ================================
确定 d 之后，B 的新内容就是 B[HC-d : HC]（高度正好 d），直接接在 A 下面。
d 不可靠（匹配率低于阈值）时不猜，加一条细分隔线后硬拼，用户可事后拖动接缝。
"""

import numpy as np

# ---------- 可调参数（Swift 里用完全相同的值） ----------
COARSE_SCALE = 4          # 粗搜降采样倍数
FINE_WINDOW = 10          # 精修搜索半径（像素）
MIN_OVERLAP_FRAC = 0.06   # 至少 6% 的行重叠，否则判为"断开"
MIN_SCROLL_FRAC = 0.20    # 至少滚动 20% 内容高。小于它的候选一律不采纳：
                          # 固定位置的悬浮视频/按钮在"几乎没滚动"时自己和自己匹配，
                          # 会制造大量假匹配。真实使用中每屏都会滚过 1/4 以上。
MATCH_FRAC_THRESHOLD = 0.55  # 正确偏移的精确匹配行占比下限
EXACT_EPS = 0.5           # 灰度差低于它算"这一行完全匹配"
MIN_MATCH_ROWS = 30       # 至少要有这么多行真的匹配上，否则不算"找到重叠"
MAX_EXCLUDED_FRAC = 0.90  # 被排除（视频/进度条）的行占比上限
STATIC_EPS = 1.5          # 跨截图行差异低于它 → 视为"静止行"（覆盖层）
MAX_OVERLAY_FRAC = 0.22   # 单侧覆盖层高度上限（占屏高）
MIN_OVERLAY_H = 60        # 紧贴边缘的覆盖层最小高度
# iOS 小白条（home indicator）固定在屏幕绝对位置、但不紧贴底边，
# 它下面那几行是屏幕背景色（同样静止），整段一起裁掉即可。
HOME_ISLAND_ZONE = 0.10   # 只在屏幕最下方 10% 内找
HOME_ISLAND_MIN_H = 3     # 小岛最小高度
HOME_ISLAND_MAX_H = 120   # 小岛最大高度
BAD_BAND_MIN = 48         # 连续不匹配多少像素才算"被遮挡区段"
BAD_BAND_ITER = 3         # 迭代排除次数上限
DIVIDER_COLOR = (205, 205, 205)
DIVIDER_HEIGHT = 3


# ---------------------------------------------------------------- 基础工具

def to_gray(rgb):
    """rgb: (H,W,3) uint8 -> (H,W) float32"""
    rgb = rgb.astype(np.float32)
    return rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114


def box_downsample(g, scale):
    """盒式降采样，尺寸必须是 scale 的整数倍（先裁再 reshape）。"""
    h, w = g.shape[0] // scale, g.shape[1] // scale
    if h < 8 or w < 8:
        return g.copy()
    return g[:h * scale, :w * scale].reshape(h, scale, w, scale).mean(axis=(1, 3))


# ---------------------------------------------------------------- 覆盖层探测

def static_rows(grays):
    """返回 (H,) bool：True 表示这一行在所有截图里完全一致。
    固定覆盖层（状态栏/导航栏/底部条）必然满足。"""
    H = grays[0].shape[0]
    diff = np.zeros(H, dtype=np.float32)
    n = len(grays)
    for i in range(n):
        for j in range(i + 1, n):
            diff = np.maximum(diff, np.abs(grays[i] - grays[j]).mean(axis=1))
    return diff < STATIC_EPS


def detect_overlays(grays):
    """量出固定覆盖层高度。返回 (top, bottom)。

    两部分：
      1) 紧贴上下边缘的静止带（状态栏+导航栏、输入框、标签栏）
      2) 底部附近"悬空"的静止小岛 —— iOS 小白条（home indicator）就是这样：
         它固定在屏幕绝对位置，但下面还露出几行内容，所以不紧贴边缘。
         不处理它，小白条会被重复拼进每一段。
    """
    H = grays[0].shape[0]
    st = static_rows(grays)
    cap = int(MAX_OVERLAY_FRAC * H)

    top = 0
    while top < cap and st[top]:
        top += 1
    bottom = 0
    while bottom < cap and st[H - 1 - bottom]:
        bottom += 1

    # 顶部：太薄的静止带多半只是内容里的分隔线，不算覆盖层
    if top < MIN_OVERLAY_H:
        top = 0

    # 底部：紧贴边缘的静止带即使是薄薄 20 多像素（小白条 + 背景）也必须收下，
    # 否则小白条会被重复拼进每一段。
    # 若底边本身不是静止的（内容一直延伸到屏幕最下沿），再单独找"悬空的小白条"。
    if bottom == 0:
        island = find_static_island_from_bottom(st, H)
        if island is not None:
            bottom = H - island

    if top + bottom > int(0.5 * H):
        return 0, 0
    return top, bottom


def find_static_island_from_bottom(st, H):
    """从屏幕底部往上找一段"静止、且其上方不静止"的小岛。
    iOS 小白条就是这种情况：固定在绝对位置，但下面还露出几行内容。
    返回小岛起始行号；找不到返回 None。"""
    zone_start = H - int(HOME_ISLAND_ZONE * H)
    y = H - 1
    while y > zone_start:
        if not st[y]:
            y -= 1
            continue
        end = y
        while y > zone_start and st[y]:
            y -= 1
        start = y + 1
        height = end - start + 1
        above_ok = start - 1 >= 0 and not st[start - 1]
        if HOME_ISLAND_MIN_H <= height <= HOME_ISLAND_MAX_H and above_ok:
            return start
    return None


# ---------------------------------------------------------------- 偏移量搜索

def match_fraction(A, B, d, top, bottom, exclude=None):
    """返回 (frac, ys, errs)。
    frac = 有效行里"整行完全匹配"的比例；ys/errs 供后续找遮挡区段用。"""
    H = A.shape[0]
    n_end = H - bottom - d
    if n_end <= top:
        return 0.0, np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)
    ys = np.arange(top, n_end)
    if exclude is not None:
        ys = ys[~exclude[ys]]
    if ys.size < 8:
        return 0.0, np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)
    errs = np.abs(B[ys] - A[ys + d]).max(axis=1)
    return float((errs < EXACT_EPS).mean()), ys, errs


def _bad_bands(errs, ys, min_len):
    """从逐行误差里找出连续 >= min_len 行、且完全不匹配的区段，返回 [(y0, y1)]。"""
    idx = np.where(errs >= EXACT_EPS)[0]
    if idx.size == 0:
        return []
    groups, s0, p = [], idx[0], idx[0]
    for k in idx[1:]:
        if k - p > 1:
            groups.append((s0, p))
            s0 = k
        p = k
    groups.append((s0, p))
    return [(int(ys[a]), int(ys[b])) for a, b in groups if (b - a + 1) >= min_len]


def _exclusion_search(A, B, top, bottom, lo, hi, bad_min, max_excluded_frac):
    """在 [lo, hi] 里找最优 d，并迭代排除"被遮挡区段"（视频/进度条/广告）。
    返回 (d, frac, exclude_mask)。"""
    H = A.shape[0]
    exclude = np.zeros(H, dtype=bool)
    best_d, best_f = None, -1.0
    for _ in range(BAD_BAND_ITER):
        cand_d, cand_f = None, -1.0
        for d in range(lo, hi + 1):
            f, _, _ = match_fraction(A, B, d, top, bottom, exclude)
            if f > cand_f:
                cand_f, cand_d = f, d
        if cand_d is None:
            break
        if cand_d == best_d:
            best_d, best_f = cand_d, max(best_f, cand_f)
            break
        best_d, best_f = cand_d, cand_f

        _, ys, errs = match_fraction(A, B, best_d, top, bottom, exclude)
        if errs.size == 0:
            break
        bands = _bad_bands(errs, ys, bad_min)
        if not bands:
            break
        new_excl = exclude.copy()
        for y0, y1 in bands:
            new_excl[y0:y1 + 1] = True
        # 排除过多说明这个偏移本身可疑，别继续"作弊"
        if new_excl[top:H - bottom].mean() > max_excluded_frac:
            break
        exclude = new_excl
    return best_d, max(best_f, 0.0), exclude


def find_offset(A, B, top, bottom):
    """A、B 同尺寸灰度图。返回 (d, frac)；d=None 表示没找到可靠重叠。"""
    H = A.shape[0]
    min_overlap = max(24, int(MIN_OVERLAP_FRAC * H))

    def d_limit():
        return H - bottom - min_overlap - top

    if d_limit() <= 2:
        return None, 0.0

    # ---- 第 1 轮：降采样粗搜（同样要带排除循环，否则动态内容会选错候选）
    s = COARSE_SCALE
    As, Bs = box_downsample(A, s), box_downsample(B, s)
    Hs = As.shape[0]
    tops, bots = top // s, bottom // s
    min_ov_s = max(6, min_overlap // s)
    ds_hi = Hs - bots - min_ov_s - tops
    # 粗搜阶段就要排除"滚动太少"的候选，否则悬浮元素会先把自己选出来
    ds_lo = max(1, int(MIN_SCROLL_FRAC * (Hs - tops - bots)) // 2)
    if ds_hi <= ds_lo:
        return None, 0.0
    best_ds, _, _ = _exclusion_search(As, Bs, tops, bots, ds_lo, ds_hi,
                                      max(3, BAD_BAND_MIN // s), 0.6)
    if best_ds is None:
        return None, 0.0

    # ---- 第 2 轮：全分辨率精修
    lo = max(1, best_ds * s - FINE_WINDOW * 2)
    hi = min(d_limit(), best_ds * s + FINE_WINDOW * 2)
    # 排除"滚动太少"的候选：固定位置的悬浮元素会自己和自己匹配
    min_scroll = max(int(MIN_SCROLL_FRAC * (H - top - bottom)), FINE_WINDOW)
    lo = max(lo, min_scroll)
    if lo > hi:
        return None, 0.0
    best_d, best_f, _ = _exclusion_search(A, B, top, bottom, lo, hi,
                                          BAD_BAND_MIN, 0.6)

    if best_d is None:
        return None, 0.0
    # 双闸门：既要"匹配行占比够高"，也要"真的匹配上足够多行"。
    # 只靠占比会在动态内容场景被"排除掉 86% 的行后 100% 匹配"骗过。
    _, _, errs = match_fraction(A, B, best_d, top, bottom)
    match_rows = int((errs < EXACT_EPS).sum()) if errs.size else 0
    if best_f < MATCH_FRAC_THRESHOLD or match_rows < MIN_MATCH_ROWS:
        return None, best_f
    return best_d, best_f


# ---------------------------------------------------------------- 拼接

def assemble(cropped_rgbs, d_list, content_h=None, first_kept_chrome=False, first_top=0):
    """按给定的 d 序列拼装。d=None 表示断开（加分隔线）。

    cropped_rgbs[0] 在 first_kept_chrome=True 时比别人多出 first_top 行（保留的状态栏+导航栏），
    所以"新内容"的高度基准要用 content_h（不含顶部覆盖层的内容区高度），不能用 cropped_rgbs[0] 的行数。
    """
    W = cropped_rgbs[0].shape[1]
    if content_h is None:
        content_h = cropped_rgbs[0].shape[0] - (first_top if first_kept_chrome else 0)

    parts = [cropped_rgbs[0]]
    for i, d in enumerate(d_list):
        if d is None:
            parts.append(np.full((DIVIDER_HEIGHT, W, 3), DIVIDER_COLOR, dtype=np.uint8))
            parts.append(cropped_rgbs[i + 1])
        else:
            parts.append(cropped_rgbs[i + 1][content_h - d:])
    return np.concatenate(parts, axis=0)


def stitch_group(rgbs, verbose=False, keep_first_chrome=True):
    """主入口。返回 (长图, 诊断 dict)。
    诊断里带 top/bottom/d_list；用户手动拖动接缝后，只改 d_list 再调 assemble() 即可重拼。

    keep_first_chrome=True 时，第一张截图的顶部覆盖层（状态栏+导航栏）保留在长图最上方，
    后续截图仍然裁掉（否则每一段都会重复出现状态栏）。这是用户明确要求的。
    """
    grays = [to_gray(r) for r in rgbs]
    n = len(grays)
    H = grays[0].shape[0]

    top, bottom = detect_overlays(grays)

    d_list, pairs = [], []
    for i in range(n - 1):
        d, f = find_offset(grays[i], grays[i + 1], top, bottom)
        d_list.append(d)
        pairs.append({"index": i, "d": d, "frac": round(f, 3), "gap": d is None})
        if verbose:
            print(f"  [pair{i}] d={d} frac={f:.3f} gap={d is None}")

    # 每张都裁掉底部覆盖层；顶部只有第一张保留
    cropped = []
    for i, r in enumerate(rgbs):
        y0 = 0 if (i == 0 and keep_first_chrome) else top
        cropped.append(r[y0:H - bottom])
    out = assemble(cropped, d_list, first_kept_chrome=(keep_first_chrome and top > 0),
                   first_top=top)
    diag = {"top": int(top), "bottom": int(bottom),
            "content_h": int(H - top - bottom),
            "pairs": pairs, "d_list": d_list,
            "keep_first_chrome": bool(keep_first_chrome),
            "height": int(out.shape[0]), "width": int(out.shape[1])}
    return out, diag


MAX_OUTPUT_HEIGHT = 30000
# 两张截图的拍摄间隔超过这个秒数，就认为不属于同一次长截图。
# 用户连续截屏的间隔通常是 2~15 秒，中途去干别的事才会拉长。
GROUP_TIME_GAP = 90.0


def stitch_all(rgbs, timestamps=None, verbose=False, keep_first_chrome=True):
    """把一串截图自动分成若干组，每组拼一张长图。

    分组规则（两个信号任一命中就断开）：
      1. 时间间隔 > GROUP_TIME_GAP 秒 —— 主信号，最可靠
      2. 相邻两张找不到可信的滚动偏移 —— 兜底，防止用户快速截了不相关的画面

    返回 (results, diag_all)：
      results  = [(长图, 该组诊断), ...]
      diag_all = {"groups": [[0,1,2], [3,4]], "breaks": [...], "too_tall": bool, "height": 总高}
    """
    grays = [to_gray(r) for r in rgbs]
    n = len(grays)
    H = grays[0].shape[0]

    breaks, reasons = [], {}
    for i in range(n - 1):
        gap_time = None
        if timestamps is not None and i + 1 < len(timestamps):
            gap_time = float(timestamps[i + 1] - timestamps[i])
        if gap_time is not None and gap_time > GROUP_TIME_GAP:
            breaks.append(i)
            reasons[i] = f"time_gap={gap_time:.0f}s"
            if verbose:
                print(f"  [pair{i}] break by time gap {gap_time:.0f}s")
            continue
        # 时间上算同一组，再用内容匹配兜底确认
        top, bottom = detect_overlays([grays[i], grays[i + 1]])
        d, f = find_offset(grays[i], grays[i + 1], top, bottom)
        if d is None:
            breaks.append(i)
            reasons[i] = f"no_match frac={f:.2f}"
        if verbose:
            print(f"  [pair{i}] time_gap={gap_time} d={d} frac={f:.3f} break={d is None}")

    groups, start = [], 0
    for b in breaks:
        groups.append(list(range(start, b + 1)))
        start = b + 1
    groups.append(list(range(start, n)))

    results = []
    for g in groups:
        sub = [rgbs[i] for i in g]
        img, diag = stitch_group(sub, verbose=False, keep_first_chrome=keep_first_chrome)
        diag["indices"] = g
        results.append((img, diag))

    total_h = sum(r[1]["height"] for r in results)
    diag_all = {"groups": groups, "breaks": breaks, "reasons": reasons,
                "too_tall": total_h > MAX_OUTPUT_HEIGHT, "height": total_h}
    return results, diag_all
