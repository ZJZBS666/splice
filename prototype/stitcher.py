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
FINE_WINDOW = 6           # 精修搜索半径（像素）。实测 6 与 10 准确率相同但快 2 倍
# 精修阶段的抽样步长。粗搜定位后候选已在真值附近，精修只需在 d±2*FINE_WINDOW
# 内找极小值；实测 row=2/col=2 与 row=1/col=1 的准确率完全相同，但快 4 倍。
FINE_ROW_STRIDE = 2       # 精修每 2 行取 1 行
FINE_COL_STRIDE = 2       # 精修每 2 列取 1 列
MIN_OVERLAP_FRAC = 0.06   # 至少 6% 的行重叠，否则判为"断开"
MIN_SCROLL_FRAC = 0.20    # 至少滚动 20% 内容高。小于它的候选一律不采纳：
                          # 固定位置的悬浮视频/按钮在"几乎没滚动"时自己和自己匹配，
                          # 会制造大量假匹配。真实使用中每屏都会滚过 1/4 以上。
MATCH_FRAC_THRESHOLD = 0.55  # 已废弃：旧的"精确匹配行占比"下限，保留常量以免别处引用报错
EXACT_EPS = 0.5           # 已废弃：旧的逐像素完全匹配阈值
TOLERANT_EPS = 3.0        # 已废弃：旧的放宽 eps
MIN_MATCH_ROWS = 30       # 参与打分的"有效纹理行"数量下限（绝对行数）
MAX_EXCLUDED_FRAC = 0.85  # 被排除（视频/进度条）的行占比上限
# ---- 新指标：纹理行归一化误差（抗亚像素 + 抗动态内容）----
TEXTURE_MIN = 3.0         # 行内灰度标准差 >= 它才算"有纹理的行"
SD_FLOOR = 8.0            # 归一化时分母下限，避免纯色行把误差放大成噪声
MATCH_COST_THRESHOLD = 0.65  # 归一化误差上限（辅助闸门）；实测正确偏移 0.00~0.56，无关两图 0.44~1.58
PEAK_RATIO_THRESHOLD = 0.45  # 主闸门：最优代价 / 搜索区间中位代价；实测真匹配 0.00~0.25，无关两图 0.49~0.89
MIN_USED_FRAC = 0.25      # 排除动态区段后，至少还要剩这么多纹理行参与打分（防"排除作弊"）
# 分带投票的"弃权"阈值。某一带在 d±BAND_WIN 内的代价曲线如果几乎是平的，
# 说明这一段内容在两张图里本来就一样（空白背景、重复的输入框），
# 它的 argmin 纯属噪声，不该投票反对。
# 实测（diag_real23.py）：真匹配的有信息带 spread > 0.3，平坦带 < 0.12；
# 而无关两图的**每一个**带 spread 都 < 0.05 —— 所以平坦带弃权后，
# 无关两图会得到 agree=0，真匹配仍能拿到 agree>=2，分离度反而更大。
BAND_SPREAD_MIN = 0.05
# 投"同意"票的带，它自己的最小代价必须低于这个值。
# 实测（calib_bandcost.py）：
#   真匹配 的同意带 min cost 全部 <= 0.90（亚像素/视频最差 0.66，真实微信 0.63）
#   无关两图 的带 min cost 全部 >= 2.04
# 平坦带弃权只能挡掉"没有信息"的带，挡不住"两图都同样花"的无关图 ——
# 后者代价曲线有峰但整体很高，所以必须再补这条绝对上限。
BAND_MAX_COST = 1.0
BAD_ROW_COST = 0.60       # 单行归一化误差 >= 它才算"这行被遮挡了"
BAD_BAND_MIN = 48         # 连续不匹配多少像素才算"被遮挡区段"
BAD_BAND_ITER = 3         # 迭代排除次数上限
# 粗搜：只抽样"参与比较的行/列"，d 保持全分辨率整数。
# 不能对图像做行降采样 —— d=1534 时 1534/4=383.5 不是整数，降采样图里
# 根本不存在真值对应的位移，极小值会被抹平到错误位置（list 场景选错 1888 的根因）。
COARSE_ROW_STRIDE = 8     # 粗搜每 8 行取 1 行（实测 4/8/16 准确率相同，8 比 4 快 2.5 倍）
COARSE_COL_STRIDE = 4     # 粗搜每 4 列取 1 列
# ---- 分带一致性闸门（主判据）----
# 把有效区间横切若干段，每段各自找最优偏移；真匹配时每段都指向同一个 d，
# 无关两图各段乱指。实测：真匹配最少 3/4 段一致，无关两图最多 2/4。
BAND_COUNT = 4            # 切成几段
BAND_WIN = 8              # 每段在自己那一段内搜索 d±8
BAND_AGREE_TOL = 1        # 偏差 <= 1px 就算"指向同一个 d"
# 至少几段一致才认定为真匹配。
# 注意：平坦带弃权后，真匹配常常只剩 2 个"有信息"的带（其余是空白背景、
# 重复的输入框），所以这里必须是 2，再配一条"一致段数 >= 反对段数"的多数
# 判据（见 find_offset）。实测无关两图 agree 恒为 0，仍有充足分离度。
MIN_BAND_AGREE = 2
CAND_TOPK = 8             # 粗搜取前几个候选逐个精修+投票（防"低重叠区噪声"骗过）
STATIC_EPS = 1.5          # 已废弃：旧的"行内平均差"判据，保留常量以免别处引用报错
CHANGE_EPS = 2.0          # 灰度差 >= 它才算"这个像素真的变了"
STATIC_CHANGED_FRAC = 0.10  # 一行里允许变动的像素占比上限
                            # （状态栏时钟只占 ~2%，仍算静止行）
MAX_OVERLAY_FRAC = 0.22   # 单侧覆盖层高度上限（占屏高）
MIN_OVERLAY_H = 60        # 紧贴边缘的覆盖层最小高度
# 三分类判据里"行均值差 >= 它才算变了"的阈值。
# 实测（calib_top1.py）：真实微信 JPEG 用 6.0 得到 top=318/bottom=270（真值 318/276）；
# 合成 PNG 用 6.0 也精确命中（top=321、bottom 与 content_bottom_bar 一致）。
CLASSIFY_THR = 6.0
# 悬浮覆盖层（不贴底边、下面还露出滚动内容）的"固定带"判据。
# iOS 26 设置页的搜索胶囊就固定在 y≈2394..2538，下面仍有内容在滚。
# 这类带子里内容**不会在任何位置重现**，所以 shift = |A[y]-B[y-d]| 一直很大；
# 而正常滚动内容总有某个 d 让 shift 很小。实测（calib_bottom12.py）：
#   真实 6 图 bottom = 270/270/270/228（真值 276/276/276/228）
#   合成 5 场景 chat 200 / feed 180 / list 34 / article 34 / dynamic 34 全精确
OVERLAY_BAND_END_NEAR = 0.12  # 固定带必须延伸到"距底边 12% 屏高"以内才算底部覆盖层
# iOS 小白条（home indicator）固定在屏幕绝对位置、但不紧贴底边，
# 它下面那几行是屏幕背景色（同样静止），整段一起裁掉即可。
HOME_ISLAND_ZONE = 0.10   # 只在屏幕最下方 10% 内找
HOME_ISLAND_MIN_H = 3     # 小岛最小高度
HOME_ISLAND_MAX_H = 120   # 小岛最大高度
DIVIDER_COLOR = (205, 205, 205)
DIVIDER_HEIGHT = 3
# 右侧滚动条保护带：iOS 滚动指示条固定在屏幕最右侧（1206 宽下实测 x=1188..1196，
# 距右边缘 10~18 像素），半透明、随滚动移动。它既不是"静止行"（每张位置都不同），
# 也不是内容，参与打分会引入噪声，而且会被原样拼进长图 —— 一张长图里出现好几条
# 滚动条就是这个原因。所以在**所有打分与覆盖层判定**里都跳过右侧这一窄条。
# 只损失约 3% 的列，信号几乎不受影响。
SCROLLBAR_GUARD_FRAC = 0.03


# ---------------------------------------------------------------- 基础工具

def to_gray(rgb):
    """rgb: (H,W,3) uint8 -> (H,W) float32"""
    rgb = rgb.astype(np.float32)
    return rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114


def usable_w(W):
    """参与打分的列数：去掉最右侧的滚动条保护带（见 SCROLLBAR_GUARD_FRAC）。"""
    cut = max(1, int(SCROLLBAR_GUARD_FRAC * W))
    return max(1, W - cut)


def box_downsample(g, scale):
    """盒式降采样，尺寸必须是 scale 的整数倍（先裁再 reshape）。"""
    h, w = g.shape[0] // scale, g.shape[1] // scale
    if h < 8 or w < 8:
        return g.copy()
    return g[:h * scale, :w * scale].reshape(h, scale, w, scale).mean(axis=(1, 3))


# ---------------------------------------------------------------- 覆盖层探测

def static_rows(grays):
    """返回 (H,) bool：True 表示这一行在所有截图里基本一致。

    判定：该行里"被改动的像素"占比 <= STATIC_CHANGED_FRAC 就算静止。

    为什么不用"行内平均绝对差 < STATIC_EPS"：
    真机状态栏左上角的**时钟**在两次截图之间会变（9:41 -> 9:42）。
    时钟只占 1206 像素宽里的几十个像素，但平均差会被拉到 3 以上，
    于是状态栏那几行被判成"非静止"，top 从 318 缩到 77 左右，
    结果就是每段内容上面都重复贴一条状态栏。
    （见 test_clock.py：旧逻辑 top=77，新逻辑 top=366，真值 318）

    截图是 PNG（无损），没变的像素**一定**完全相等，所以按"改动像素占比"
    判断既准确又不会被时钟、电池图标、信号格这类小区域变化骗到。
    """
    H = grays[0].shape[0]
    W = grays[0].shape[1]
    UW = usable_w(W)
    max_changed = max(1, int(STATIC_CHANGED_FRAC * W))
    st = np.ones(H, dtype=bool)
    n = len(grays)
    for i in range(n):
        for j in range(i + 1, n):
            changed = (np.abs(grays[i][:, :UW] - grays[j][:, :UW]) >= CHANGE_EPS).sum(axis=1)
            st &= changed <= max_changed
    return st


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


def classify_bottom(A, B, d, thr=CLASSIFY_THR):
    """用已知的滚动量 d 判定底部覆盖层高度（真机唯一可靠的判据）。

    为什么不能用"跨截图静止行"：深色模式下微信输入框是**半透明**的，
    聊天内容从它下面透出来，所以输入框的像素在两张截图之间会变，永远不满足
    "静止行"。而只要有一行不静止，连续静止后缀就断掉 —— 实测 pair0 只报
    bottom=24，真实输入框顶在 y=2346（bottom=276）。少裁的 252 行输入框残影
    被拼进长图中间，同时 252 行真实内容被挤掉，这正是"截图不全"的机制。

    判据（三分类，每行只看两个数）：
      same  = |A[y] - B[y]|        同一屏幕位置
      shift = |A[y] - B[y-d]|      A[y] 若随内容滚动，应出现在 B 的这个位置
      CONT  same>=thr 且 shift<thr   → 滚动内容（B 的同位置变了，但它确实在 B 里）
      FIX   same<thr  且 shift>=thr  → 固定覆盖层
      AMB   两者都<thr               → 空白（空白和空白到处都一样，无法区分）
      NOIS  两者都>=thr              → 瞬时 UI（光标/高亮）或 JPEG 振铃

    取"最后一个 CONT 行"作为内容底边：它下面是覆盖层或空白，
    裁掉空白没有视觉损失，所以两个方向都安全。

    补充：还要处理**悬浮覆盖层**（iOS 26 设置页的搜索胶囊）。
    它固定在 y≈2394..2538，下面仍有内容在滚，所以"最后一个 CONT 行"落在
    屏幕最底部，classify 会给出 bottom=0，胶囊就被拼进长图两次。
    这类带子的特征是 shift 一直很大（内容在 B 里任何位置都找不到），
    所以再找一段"连续 shift>=thr 且延伸到接近底边"的带，从它的上边缘裁。
    """
    H = A.shape[0]
    UW = usable_w(A.shape[1])
    y0 = max(int(H * (1.0 - MAX_OVERLAY_FRAC)), d, 0)
    if y0 >= H:
        return 0
    ys = np.arange(y0, H)
    same = np.abs(A[ys][:, :UW] - B[ys][:, :UW]).mean(axis=1)
    shift = np.abs(A[ys][:, :UW] - B[ys - d][:, :UW]).mean(axis=1)
    cont = (same >= thr) & (shift < thr)
    idx = np.nonzero(cont)[0]
    b_class = H - 1 - int(ys[idx[-1]]) if len(idx) else 0

    # 悬浮固定带：连续 shift>=thr 且下端接近屏幕底部
    near = H - int(OVERLAY_BAND_END_NEAR * H)
    b_isl = 0
    run_start = None
    for k in range(len(shift) + 1):
        big = k < len(shift) and shift[k] >= thr
        if big and run_start is None:
            run_start = k
        elif not big and run_start is not None:
            if k - run_start >= MIN_OVERLAY_H and int(ys[k - 1]) >= near:
                b_isl = max(b_isl, H - int(ys[run_start]))
            run_start = None
    return max(b_class, b_isl)


def classify_top(A, B, d, thr=CLASSIFY_THR):
    """顶部覆盖层高度的对称判据：B[y] 若随内容滚动，应出现在 A[y+d]。"""
    H = B.shape[0]
    UW = usable_w(B.shape[1])
    y1 = min(int(H * MAX_OVERLAY_FRAC), H - d)
    if y1 <= 0:
        return 0
    ys = np.arange(0, y1)
    same = np.abs(B[ys][:, :UW] - A[ys][:, :UW]).mean(axis=1)
    shift = np.abs(B[ys][:, :UW] - A[ys + d][:, :UW]).mean(axis=1)
    cont = (same >= thr) & (shift < thr)
    idx = np.nonzero(cont)[0]
    if len(idx) == 0:
        return 0
    return int(ys[idx[0]])


def refine_overlays(grays, d_list, top0, bottom0):
    """用已经求出的 d 重新量覆盖层；没有 d 的对不参与。

    多对时取中位数（同一批截图、同一个 App，覆盖层高度是常量）。
    一对都不可用时退回 detect_overlays 的结果。
    """
    tops, bots = [], []
    for i, d in enumerate(d_list):
        if d is None:
            continue
        t = classify_top(grays[i], grays[i + 1], d)
        b = classify_bottom(grays[i], grays[i + 1], d)
        if t > 0:
            tops.append(t)
        if b > 0:
            bots.append(b)
    top = int(np.median(tops)) if tops else top0
    bottom = int(np.median(bots)) if bots else bottom0
    if top < MIN_OVERLAY_H:
        top = top0
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
#
# 指标演进史（重要，别再走回头路）：
#   第 2 版：误差中位数 —— 正确和错误偏移处中位数都是 0，零判别力。
#   第 4 版：整行完全匹配占比 frac —— 合成样本（整数滚动）下完美，
#            但真机 UIScrollView 停下时滚动量是**小数**像素，iOS 截图会按小数
#            偏移做双线性重采样，同一内容行的像素值差 1~120，frac 恒为 0，
#            整组会被误判成"无重叠"。这是必须换指标的根本原因。
#   第 5 版（当前）：纹理行归一化 L1 误差
#            cost(d) = Σ|B[y]-A[y+d]| / Σ std(A[y+d])   只统计"有纹理"的行
#            - 只统计有纹理的行：纯色行在任何偏移下都匹配，会稀释信号
#            - 用"比值的和"而不是"逐行比值的均值"：后者会被低对比度行放大
#              （分母接近 0），亚像素时会把真值淹没
#            - 用 sum 而不是 median/trimmed：纯色行多时中位数退化为 0
#   粗搜不再对图像做行降采样：d=1534 时 1534/4=383.5 不是整数，降采样图里
#   根本不存在真值对应的位移，极小值被抹平到错误位置（这是 list 场景选错
#   1888 的根因）。改为**抽样比较行**（y 取 top, top+4, ...），d 仍是精确整数。

def _row_sd(A, col_stride=1):
    """每行的灰度标准差。与 d 无关，可以预先算一次。

    std 只依赖 A 的行本身，而 a = A[ys+d] 只是"取 A 的哪些行"，
    所以整张 A 的行标准差表可以复用，省掉每个候选都重算的代价。
    """
    sub = A[:, :usable_w(A.shape[1])][:, ::col_stride]
    return sub.std(axis=1).astype(np.float32)


def _cost_at(A, B, d, top, bottom, sdA, row_stride, col_stride, exclude=None):
    """返回 (cost, used_rows, ys, rne, tex_mask) 或 None。

    cost = Σ rowMAD / Σ rowSD，只累加"有纹理且未被排除"的行。
    rowMAD 是这一行所有（抽样）列的绝对差均值。
    """
    H = A.shape[0]
    UW = usable_w(A.shape[1])
    n_end = H - bottom - d
    if n_end <= top:
        return None
    ys = np.arange(top, n_end, row_stride)
    if ys.size < 8:
        return None
    a_rows = ys + d
    a = A[a_rows][:, :UW][:, ::col_stride]
    b = B[ys][:, :UW][:, ::col_stride]
    sd = sdA[a_rows]
    row_mad = np.abs(a - b).mean(axis=1)
    rne = row_mad / np.maximum(sd, SD_FLOOR)

    tex = sd >= TEXTURE_MIN
    used = tex
    if exclude is not None:
        used = tex & (~exclude[ys])
    n_used = int(used.sum())
    if n_used < 8:
        return None
    sd_sum = float(sd[used].sum())
    if sd_sum < 1e-6:
        return None
    cost = float(row_mad[used].sum() / sd_sum)
    return cost, n_used, ys, rne, tex


def _scan_curve(A, B, top, bottom, lo, hi, sdA, row_stride, col_stride,
                exclude=None):
    """扫描 [lo, hi]，返回 {d: (cost, used_rows)}。"""
    curve = {}
    for d in range(lo, hi + 1):
        got = _cost_at(A, B, d, top, bottom, sdA, row_stride, col_stride, exclude)
        if got is not None:
            curve[d] = (got[0], got[1])
    return curve


def _bad_bands(rne, ys, tex, min_len):
    """找出"连续 >= min_len 行、是纹理行、但误差很大"的区段。

    这些就是视频 / 进度条 / 广告 / 动画 —— 两张截图里内容真的不一样，
    不该参与打分。返回 [(y0, y1)]（屏幕坐标，含端点）。
    """
    bad = (rne >= BAD_ROW_COST) & tex
    if not bad.any():
        return []
    idx = np.where(bad)[0]
    groups, s0, p = [], idx[0], idx[0]
    for k in idx[1:]:
        if k - p > 1:
            groups.append((s0, p))
            s0 = k
        p = k
    groups.append((s0, p))
    return [(int(ys[a]), int(ys[b])) for a, b in groups if (b - a + 1) >= min_len]


def _exclusion_search(A, B, top, bottom, lo, hi, sdA, row_stride, col_stride,
                      bad_min, max_excluded_frac):
    """在 [lo, hi] 里找 cost 最小的 d，并迭代排除动态区段。

    返回 (d, cost, exclude, curve)。curve 是最后一轮的 {d: cost}，用于算峰值比。
    """
    H = A.shape[0]
    exclude = np.zeros(H, dtype=bool)
    best_d, best_c = None, None
    curve = {}
    for _ in range(BAD_BAND_ITER):
        raw = _scan_curve(A, B, top, bottom, lo, hi, sdA, row_stride, col_stride,
                          exclude)
        curve = {d: v[0] for d, v in raw.items()}
        if not curve:
            return None, None, exclude, curve
        cand_d = min(curve, key=lambda k: curve[k])
        cand_c = curve[cand_d]
        if cand_d == best_d:
            best_c = min(best_c, cand_c) if best_c is not None else cand_c
            break
        best_d, best_c = cand_d, cand_c

        got = _cost_at(A, B, best_d, top, bottom, sdA, row_stride, col_stride,
                       exclude)
        if got is None:
            break
        _, _, ys, rne, tex = got
        bands = _bad_bands(rne, ys, tex, bad_min)
        if not bands:
            break
        new_excl = exclude.copy()
        for y0, y1 in bands:
            new_excl[y0:y1 + 1] = True
        # 排除过多说明这个偏移本身可疑，别继续"作弊"
        if new_excl[top:H - bottom].mean() > max_excluded_frac:
            break
        exclude = new_excl
    return best_d, best_c, exclude, curve


def _band_cost(A, B, d, y0, y1, sdA, col_stride):
    """[y0,y1) 区间内、偏移 d 的归一化 L1 代价（只统计纹理行）。

    与全局 _cost_at 用同一套度量，保证"分段最优"和"全局最优"可比。
    """
    H = A.shape[0]
    UW = usable_w(A.shape[1])
    y1 = min(y1, H - d)
    if y1 <= y0 + 4:
        return None
    ys = np.arange(y0, y1)
    a = A[ys + d][:, :UW][:, ::col_stride]
    b = B[ys][:, :UW][:, ::col_stride]
    sd = sdA[ys + d]
    tex = sd >= TEXTURE_MIN
    if int(tex.sum()) < 8:
        return None
    mad = np.abs(a - b).mean(axis=1)
    den = float(sd[tex].sum())
    if den < 1e-6:
        return None
    return float(mad[tex].sum() / den)


def band_votes(A, B, d, top, bottom, col_stride=None):
    """分带一致性：把有效区间横切 BAND_COUNT 段，每段各自在 d±BAND_WIN 内
    找自己的最优偏移，统计"指向同一个 d（偏差 <= BAND_AGREE_TOL）"的段数。

    这是真正的判别闸门。为什么不用绝对 cost 或峰值比（实测数据）：
      - 绝对 cost：亚像素+视频场景下真匹配 0.67~0.99，无关两图 0.73~1.36，重叠
      - 峰值比：真匹配最高 0.42，无关两图最低 0.35，重叠
      - 分带投票：真匹配最少 3/4 段一致，无关两图最多 2/4，4/5/6 段均稳定分离
    道理很直观：真匹配时上下每一段都指向同一个滚动量；无关两图即使全局
    argmin 恰好落在某个 d，各段也会各指一处。

    返回 (agree, devs)。**代价曲线太平坦的带算"弃权"，不记入 devs**，
    理由见 BAND_SPREAD_MIN 的注释：那种带的 argmin 是噪声，投反对票会让
    本来正确的偏移掉到 MIN_BAND_AGREE 以下，整组被误判成断开
    （真机 6 张被拆成 3 组、每张长图只有 2 张内容的根因就是这个）。
    """
    H = A.shape[0]
    if col_stride is None:
        col_stride = COARSE_COL_STRIDE
    n_end = H - bottom - d
    if n_end <= top + 16:
        return 0, []
    sdA = _row_sd(A, col_stride)
    ys_all = np.arange(top, n_end)
    ys_tex = ys_all[sdA[ys_all + d] >= TEXTURE_MIN]
    if ys_tex.size < BAND_COUNT * 8:
        return 0, []
    y_lo, y_hi = int(ys_tex[0]), int(ys_tex[-1])
    span = y_hi - y_lo + 1
    devs = []
    for k in range(BAND_COUNT):
        b0 = y_lo + span * k // BAND_COUNT
        b1 = y_lo + span * (k + 1) // BAND_COUNT
        best_dd, best_c = None, None
        cs = []
        for dd in range(max(1, d - BAND_WIN), d + BAND_WIN + 1):
            c = _band_cost(A, B, dd, b0, b1, sdA, col_stride)
            if c is None:
                continue
            cs.append(c)
            if best_c is None or c < best_c:
                best_c, best_dd = c, dd
        if best_dd is None or not cs:
            continue
        cmax = max(cs)
        spread = (cmax - min(cs)) / cmax if cmax > 1e-9 else 0.0
        if spread < BAND_SPREAD_MIN:      # 平坦带弃权
            continue
        # 代价整体很高的带，即使曲线有峰也不能算"同意"：无关两图就是这种
        # 情况（曲线有起伏但 min 都在 2.0 以上）。
        if best_c > BAND_MAX_COST:
            continue
        devs.append(best_dd - d)
    agree = sum(1 for x in devs if abs(x) <= BAND_AGREE_TOL)
    return agree, devs


def find_offset(A, B, top, bottom):
    """A、B 同尺寸灰度图。返回 (d, cost)；d=None 表示没找到可靠重叠。

    两段式：粗搜（抽样行+抽样列，全分辨率 d）定位，再全分辨率精修。
    四道闸门，任一不过就判"断开"（宁可硬拼让用户拖，也不瞎猜）：
      1) 分带一致性 >= MIN_BAND_AGREE —— 主判据，见 band_votes 注释
      2) 参与打分的纹理行 >= MIN_MATCH_ROWS —— 不是靠排除作弊
      3) 保留的纹理行占比 >= MIN_USED_FRAC
    绝对 cost 与峰值比都不再作闸门（正负例区间重叠），只作诊断值返回。
    """
    H = A.shape[0]
    min_overlap = max(24, int(MIN_OVERLAP_FRAC * H))
    d_hi = H - bottom - min_overlap - top
    min_scroll = max(int(MIN_SCROLL_FRAC * (H - top - bottom)), FINE_WINDOW)
    lo = min_scroll
    hi = d_hi
    if hi - lo < 8:
        return None, 0.0

    # ---- 第 1 轮：粗搜（抽样行列，d 全分辨率）
    sdA = _row_sd(A, COARSE_COL_STRIDE)
    c_d, c_c, _, curve = _exclusion_search(
        A, B, top, bottom, lo, hi, sdA,
        COARSE_ROW_STRIDE, COARSE_COL_STRIDE,
        max(8, BAD_BAND_MIN // COARSE_ROW_STRIDE), MAX_EXCLUDED_FRAC)
    if c_d is None or not curve:
        return None, 0.0

    # ---- 粗搜取前 TOPK 个候选，逐个精修 + 分带投票，取第一个通过闸门的
    # 为什么要取多个：接近搜索上界 d_hi 的候选只有很少的行可比，随机噪声
    # 也容易压出低代价。实测 seed888/tail=0.5 时粗搜 argmin 落在 d=2463
    # （真值 1438），那个位置的分带一致性只有 1/4，而真值是 4/4。
    # 所以"代价最低"不能直接当结论，必须让分带投票来裁决。
    cands = sorted(curve, key=lambda k: curve[k])[:CAND_TOPK]
    sdA1 = _row_sd(A, FINE_COL_STRIDE)
    best = None
    for cd in cands:
        f_lo = max(lo, cd - FINE_WINDOW * 2)
        f_hi = min(hi, cd + FINE_WINDOW * 2)
        f_d, f_c, f_ex, _ = _exclusion_search(
            A, B, top, bottom, f_lo, f_hi, sdA1, FINE_ROW_STRIDE, FINE_COL_STRIDE,
            BAD_BAND_MIN, MAX_EXCLUDED_FRAC)
        if f_d is None:
            continue
        agree, devs = band_votes(A, B, f_d, top, bottom)
        # 多数判据：一致段数必须 >= 反对段数。
        # 平坦带已弃权，devs 里剩下的都是"真的看了"的带；
        # 只要求 agree >= 2 而不要求多数的话，2 对 3 反对也会通过。
        if agree < MIN_BAND_AGREE or agree < len(devs) - agree:
            continue
        # 分带投票通过：再核纹理行数量与保留比例
        got = _cost_at(A, B, f_d, top, bottom, sdA1,
                       FINE_ROW_STRIDE, FINE_COL_STRIDE, exclude=f_ex)
        if got is None:
            continue
        cost, used_rows, ys, rne, tex = got
        n_tex = int(tex.sum())
        if n_tex < MIN_MATCH_ROWS:
            continue
        if n_tex > 0 and used_rows / float(n_tex) < MIN_USED_FRAC:
            continue
        if best is None or agree > best[0] or (agree == best[0] and cost < best[1]):
            best = (agree, cost, f_d)
            if agree >= BAND_COUNT:      # 全票通过，不用再看别的候选
                break

    if best is None:
        return None, c_c

    # ---- 收尾：在 best_d 的 ±1 上用全行全列复核一次
    # 精修阶段用 row_stride=2 抽样，行相位可能偏 1 像素（实测 dynamic pair3
    # 因此差 1px，且 1882/1883/1884 三个候选在抽样下代价并列 0）。
    # 这里必须用全行的代价重新比较，不能拿抽样代价当基准 —— 否则并列时永远
    # 停在先找到的那个。只比 3 个候选，代价很小。
    bd = best[2]
    bc = None
    sdA_full = _row_sd(A, 1)
    for dd in (bd - 1, bd, bd + 1):
        if dd < lo or dd > hi:
            continue
        got = _cost_at(A, B, dd, top, bottom, sdA_full, 1, 1)
        if got is None:
            continue
        if bc is None or got[0] < bc:
            bd, bc = dd, got[0]
    if bc is None:
        return best[2], best[1]
    return bd, bc


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

    # 第一轮：先用"跨截图静止行"给出的覆盖层估个 d。
    # 这个估计在深色半透明覆盖层下往往偏小（bottom 24 而非 276），
    # 但 d 本身对它不敏感 —— 实测真实 5 对在任何 (top,bottom) 组合下
    # d 都恒定 1048/1341/1109/778。
    d_list = [find_offset(grays[i], grays[i + 1], top, bottom)[0]
              for i in range(n - 1)]

    # 第二轮：用 d 反过来量覆盖层（classify_top/bottom），再重算一遍 d。
    # 这一步才是修"截图不全"的关键：底部少裁 252 行会让 252 行真实内容被挤掉。
    top2, bottom2 = refine_overlays(grays, d_list, top, bottom)
    if (top2, bottom2) != (top, bottom):
        top, bottom = top2, bottom2
        d_list = [find_offset(grays[i], grays[i + 1], top, bottom)[0]
                  for i in range(n - 1)]

    pairs = []
    for i, d in enumerate(d_list):
        c = 0.0
        if d is not None:
            got = _cost_at(grays[i], grays[i + 1], d, top, bottom,
                           _row_sd(grays[i], 1), 1, 1)
            if got is not None:
                c = got[0]
        pairs.append({"index": i, "d": d, "cost": round(c, 4), "gap": d is None})
        if verbose:
            print(f"  [pair{i}] d={d} cost={c:.4f} gap={d is None}")

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
        d, c = find_offset(grays[i], grays[i + 1], top, bottom)
        if d is None:
            breaks.append(i)
            reasons[i] = f"no_match cost={c:.2f}"
        if verbose:
            print(f"  [pair{i}] time_gap={gap_time} d={d} cost={c:.4f} break={d is None}")

    groups, start = [], 0
    for b in breaks:
        groups.append(list(range(start, b + 1)))
        start = b + 1
    groups.append(list(range(start, n)))

    results = []
    for g in groups:
        # 单张的组是"这一对没找到重叠"的副产物：它的长图就是原截图本身，
        # 没有任何拼接价值。Swift 侧同样过滤（analyzeAll 的 plans.filter）。
        if len(g) < 2:
            continue
        sub = [rgbs[i] for i in g]
        img, diag = stitch_group(sub, verbose=False, keep_first_chrome=keep_first_chrome)
        diag["indices"] = g
        results.append((img, diag))

    total_h = sum(r[1]["height"] for r in results)
    diag_all = {"groups": groups, "breaks": breaks, "reasons": reasons,
                "too_tall": total_h > MAX_OUTPUT_HEIGHT, "height": total_h}
    return results, diag_all
