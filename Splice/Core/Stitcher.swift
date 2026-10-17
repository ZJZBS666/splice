import Foundation
import CoreGraphics
import Accelerate

/// Splice 拼接算法。这是 Python 原型 `splice/prototype/stitcher.py` 的 1:1 翻译，
/// 所有常量、搜索顺序、判定条件都必须完全一致，否则行为会跑偏。
///
/// ================================ 几何关系 ================================
/// 截图 B 是 A 向下滚动 delta 像素后的样子：   B[y] == A[y + delta]
/// 所以求出的 d 就等于 delta，B 里真正的新内容是 B[HC-d : HC]，高度正好 d。
enum StitchParams {
    // ---- 粗搜抽样（不对图像降采样！）----
    // 为什么不能降采样：d=1534 时 1534/4=383.5 不是整数，降采样图里根本不存在
    // 真值对应的位移，极小值会被抹平到错误位置（实测 list 场景因此选成 1888）。
    // 正确做法是**抽样参与比较的行/列**，d 始终是全分辨率整数。
    static let coarseRowStride = 8
    static let coarseColStride = 4
    /// 精修阶段的抽样步长。抽样会让相邻几个候选的代价并列（实测 stride=2 时
    /// d-1/d/d+1 三个都是 0.000），所以 findOffset 末尾必须用全分辨率复核一次。
    static let fineRowStride = 2
    static let fineColStride = 2
    /// 精修窗口：在粗搜候选 ±fineWindow*2 内全分辨率细扫。
    /// 实测 6 与 10 准确率相同但快一倍。
    static let fineWindow = 6
    static let minOverlapFrac = 0.06
    /// 至少滚动 20% 内容高。小于它的候选一律不采纳：固定位置的悬浮元素
    /// 在"几乎没滚动"时自己和自己匹配，会制造大量假匹配。
    static let minScrollFrac = 0.20

    // ---- 打分指标：纹理行归一化 L1 ----
    /// cost(d) = Σ|B[y]-A[y+d]| / Σ std(A[y+d])，只统计"有纹理"的行。
    /// 只统计有纹理的行：纯色行在任何偏移下都匹配，会稀释信号。
    /// 用"比值的和"而不是"逐行比值的均值"：后者会被低对比度行放大（分母接近 0）。
    /// 用 sum 而不是 median/trimmed：纯色行多时中位数退化为 0，没有判别力。
    static let textureMin: Float = 3.0
    static let sdFloor: Float = 8.0
    /// 排除动态区段后，至少还要剩这么多比例的纹理行参与打分（防"排除作弊"）
    static let minUsedFrac: Float = 0.25
    static let badRowCost: Float = 0.60

    // ---- 分带一致性（主判据）----
    /// 把有效区间横切若干段，每段各自在 d±bandWin 内找自己的最优偏移。
    /// 真匹配时每段都指向同一个 d；无关两图各段乱指。
    /// 实测：真匹配最少 3/4 段一致，无关两图最多 2/4（4/5/6 段均稳定分离）。
    /// 为什么不用绝对 cost 或峰值比当闸门：实测区间重叠
    /// （真匹配 cost 0.00~0.99 / 无关 0.44~1.58；峰值比真 0.00~0.42 / 无关 0.35~0.54）。
    static let bandCount = 4
    static let bandWin = 8
    static let bandAgreeTol = 1
    static let minBandAgree = 2
    /// 某一带在 d±bandWin 内的代价曲线如果几乎是平的，说明这一段内容在两张图里
    /// 本来就一样（空白背景、重复的输入框），它的 argmin 纯属噪声，不该投票反对。
    /// 实测：真匹配的有信息带 spread > 0.3，平坦带 < 0.12；
    /// 而无关两图的**每一个**带 spread 都 < 0.05 —— 平坦带弃权后无关两图得到
    /// agree=0，真匹配仍能拿到 agree>=2，分离度反而更大。
    static let bandSpreadMin: Float = 0.05
    /// 投"同意"票的带，它自己的最小代价必须低于这个值。
    /// 实测：真匹配的同意带 min cost 全部 <= 0.90（亚像素/视频最差 0.66，真实微信 0.63），
    /// 无关两图的带 min cost 全部 >= 2.04。
    /// 平坦带弃权只能挡掉"没有信息"的带，挡不住"两图都同样花"的无关图 ——
    /// 后者代价曲线有峰但整体很高，所以必须再补这条绝对上限。
    static let bandMaxCost: Float = 1.0
    /// 粗搜取前几个候选逐个精修+投票：接近搜索上界的候选只有很少的行可比，
    /// 随机噪声也能压出低代价（实测 seed888/tail=0.5 时粗搜 argmin 落在 2463，
    /// 真值 1438，那个位置分带一致性只有 1/4，而真值是 4/4）。
    static let candTopK = 8

    static let minMatchRows = 30
    static let maxExcludedFrac: Float = 0.85

    // ---- 右侧滚动条保护带 ----
    /// iOS 的滚动指示条固定在屏幕最右侧（1206 宽下实测在 x=1188..1196，
    /// 距右边缘 10~18 像素），半透明、随滚动移动。
    /// 它既不是"静止行"（每张截图位置都不同），也不是内容，参与打分会引入噪声，
    /// 而且会被原样拼进长图，导致一张长图里出现好几条滚动条。
    /// 所以在**所有打分与覆盖层判定**里都跳过右侧这一窄条。
    /// 只损失约 3% 的列，信号几乎不受影响。
    static let scrollbarGuardFrac = 0.03

    static let staticEps: Float = 1.5
    /// 判定"像素真的变了"的阈值
    static let changeEps: Float = 2.0
    /// 一行里允许变动的像素占比上限（状态栏时钟只占 ~4%，仍算静止）
    static let staticChangedFrac: Double = 0.10
    static let maxOverlayFrac = 0.22
    static let minOverlayH = 60
    /// 三分类判据里"行均值差 >= 它才算变了"的阈值。
    /// 实测：真实微信 JPEG 用 6.0 得到 top=318/bottom=270（真值 318/276）；
    /// 合成 PNG 用 6.0 也精确命中（top=321、bottom 与 content_bottom_bar 一致）。
    static let classifyThr: Float = 6.0
    /// 悬浮覆盖层（不贴底边、下面还露出滚动内容）的"固定带"判据。
    /// iOS 26 设置页的搜索胶囊就固定在 y≈2394..2538，下面仍有内容在滚。
    /// 这类带子里内容**不会在任何位置重现**，所以 shift = |A[y]-B[y-d]| 一直很大；
    /// 而正常滚动内容总有某个 d 让 shift 很小。
    /// 固定带必须延伸到"距底边 12% 屏高"以内才算底部覆盖层。
    static let overlayBandEndNear: Double = 0.12
    static let homeIslandZone = 0.10
    static let homeIslandMinH = 3
    static let homeIslandMaxH = 120
    static let badBandMin = 48
    static let badBandIter = 3
    static let dividerGray: UInt8 = 205
    static let dividerHeight = 3
    static let maxOutputHeight = 30000
    /// 两张截图的拍摄间隔超过这个秒数，就认为不属于同一次长截图。
    static let groupTimeGap: TimeInterval = 90
}

/// 一对相邻截图的拼接信息。用户手动拖动接缝后，改 offset 再重拼即可。
struct Seam: Identifiable, @unchecked Sendable {
    let id = UUID()
    /// 该接缝是"第 index 张"和"第 index+1 张"之间
    var index: Int
    /// 向下滚动的像素数；nil 表示没找到可靠重叠，硬拼并加分隔线
    var offset: Int?
    /// 该对匹配的代价：Σ|B-A| / Σstd，0 表示完全相同，越大越不像。
    /// 注意这不是"置信度"，没有 1.0 上限；界面上不要直接当百分比显示。
    var cost: Float

    var isGap: Bool { offset == nil }
}

/// 一组截图拼出来的结果
struct StitchResult: Identifiable, @unchecked Sendable {
    let id = UUID()
    /// 这组包含哪些原图（在输入数组里的下标）
    var indices: [Int]
    /// 长图
    var image: RGBABuffer
    /// 每条接缝
    var seams: [Seam]
    /// 每对相邻截图的滚动量（nil = 断开）
    var offsets: [Int?]
    /// 顶部覆盖层高度（状态栏+导航栏）
    var topOverlay: Int
    /// 底部覆盖层高度
    var bottomOverlay: Int
    /// 内容区高度（不含任何覆盖层）
    var contentHeight: Int
    /// 第一张保留的覆盖层行数（= topOverlay，或 0）
    var chromeHeight: Int
    /// 每条接缝在长图里的全局切点（长度 = 接缝数）。空表示这组有"断开"，不可拖动。
    var cuts: [Int]

    var pixelHeight: Int { image.height }
    var canAdjustSeams: Bool { !cuts.isEmpty && !seams.contains { $0.isGap } }
}

enum Stitcher {

    // MARK: - 覆盖层探测

    /// 返回每行是否"在所有截图里基本一致"。
    ///
    /// 判定：该行里"被改动的像素"占比 <= STATIC_CHANGED_FRAC 就算静止。
    ///
    /// 为什么不用"行内平均绝对差 < STATIC_EPS"：
    /// 真机状态栏左上角的**时钟**在两次截图之间会变（9:41 → 9:42）。
    /// 时钟只占 1206 像素宽里的几十个像素，但平均差会被拉到 40 以上，
    /// 于是状态栏那几行被判成"非静止"，top 从 318 缩到 60 左右，
    /// 结果就是每段内容上面都重复贴一条状态栏。
    ///
    /// 截图是 PNG（无损），没变的像素**一定**完全相等，所以按"改动像素占比"
    /// 判断既准确又不会被时钟、电池图标、信号格这类小区域变化骗到。
    static func staticRows(_ grays: [GrayImage]) -> [Bool] {
        if grays.isEmpty { return [] }
        let H = grays[0].height
        let W = grays[0].width
        let n = grays.count
        if n < 2 { return [Bool](repeating: false, count: H) }

        let pairs: [(Int, Int)] = {
            var p: [(Int, Int)] = []
            for i in 0..<n {
                for j in (i + 1)..<n { p.append((i, j)) }
            }
            return p
        }()

        var isStatic = [Bool](repeating: true, count: H)
        // 一行里最多允许多少个像素不同
        let maxChanged = max(1, Int(StitchParams.staticChangedFrac * Double(W)))
        // 滚动条那几列每张截图位置都不同，必须排除，否则整条底边都被判成"变了"
        let uw = usableWidth(W)
        var scratch = [Float](repeating: 0, count: W)
        let N = vDSP_Length(uw)
        let eps = StitchParams.changeEps

        for (i, j) in pairs {
            grays[i].data.withUnsafeBufferPointer { a in
                grays[j].data.withUnsafeBufferPointer { b in
                    let ap = a.baseAddress!
                    let bp = b.baseAddress!
                    scratch.withUnsafeMutableBufferPointer { sc in
                        let sp = sc.baseAddress!
                        for y in 0..<H where isStatic[y] {
                            let base = y * W
                            vDSP_vsub(ap + base, 1, bp + base, 1, sp, 1, N)
                            vDSP_vabs(sp, 1, sp, 1, N)
                            // 数一数有多少个像素真的变了；超过上限就提前判否
                            var changed = 0
                            for x in 0..<uw {
                                if sp[x] >= eps {
                                    changed += 1
                                    if changed > maxChanged {
                                        isStatic[y] = false
                                        break
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        return isStatic
    }

    /// 从底部往上找一段"静止、且其上方不静止"的小岛（iOS 小白条）。
    /// 返回小岛起始行号；找不到返回 nil。
    static func findStaticIslandFromBottom(_ st: [Bool], _ H: Int) -> Int? {
        let zoneStart = H - Int(StitchParams.homeIslandZone * Double(H))
        var y = H - 1
        while y > zoneStart {
            if !st[y] {
                y -= 1
                continue
            }
            let end = y
            while y > zoneStart && st[y] {
                y -= 1
            }
            let start = y + 1
            let height = end - start + 1
            let aboveOK = start - 1 >= 0 && !st[start - 1]
            if height >= StitchParams.homeIslandMinH
                && height <= StitchParams.homeIslandMaxH
                && aboveOK {
                return start
            }
        }
        return nil
    }

    /// 量出固定覆盖层高度。返回 (top, bottom)。
    static func detectOverlays(_ grays: [GrayImage]) -> (top: Int, bottom: Int) {
        let H = grays[0].height
        let st = staticRows(grays)
        let cap = Int(StitchParams.maxOverlayFrac * Double(H))

        var top = 0
        while top < cap && top < H && st[top] { top += 1 }
        var bottom = 0
        while bottom < cap && bottom < H && st[H - 1 - bottom] { bottom += 1 }

        if top < StitchParams.minOverlayH { top = 0 }

        // 底部：紧贴边缘的静止带即使很薄也必须收下（否则小白条会重复拼进每一段）。
        // 只有底边本身不静止时，才单独找"悬空的小白条"。
        if bottom == 0 {
            if let island = findStaticIslandFromBottom(st, H) {
                bottom = H - island
            }
        }

        if top + bottom > Int(0.5 * Double(H)) {
            return (0, 0)
        }
        return (top, bottom)
    }

    /// 用已知的滚动量 d 判定**底部**覆盖层高度（真机唯一可靠的判据）。
    ///
    /// 为什么不能用"跨截图静止行"：深色模式下微信输入框是**半透明**的，
    /// 聊天内容从它下面透出来，所以输入框的像素在两张截图之间会变，永远不满足
    /// "静止行"。而只要有一行不静止，连续静止后缀就断掉 —— 实测 pair0 只报
    /// bottom=24，真实输入框顶在 y=2346（bottom=276）。少裁的 252 行输入框残影
    /// 被拼进长图中间，同时 252 行真实内容被挤掉，这正是"截图不全"的机制。
    ///
    /// 判据（三分类，每行只看两个数）：
    ///   same  = |A[y] - B[y]|        同一屏幕位置
    ///   shift = |A[y] - B[y-d]|      A[y] 若随内容滚动，应出现在 B 的这个位置
    ///   CONT  same>=thr 且 shift<thr   → 滚动内容（B 的同位置变了，但它确实在 B 里）
    ///   FIX   same<thr  且 shift>=thr  → 固定覆盖层
    ///   AMB   两者都<thr               → 空白（空白和空白到处都一样，无法区分）
    ///   NOIS  两者都>=thr              → 瞬时 UI（光标/高亮）或 JPEG 振铃
    ///
    /// 取"最后一个 CONT 行"作为内容底边：它下面是覆盖层或空白，
    /// 裁掉空白没有视觉损失，所以两个方向都安全。
    ///
    /// 补充：还要处理**悬浮覆盖层**（iOS 26 设置页的搜索胶囊）。
    /// 它固定在 y≈2394..2538，下面仍有内容在滚，所以"最后一个 CONT 行"落在
    /// 屏幕最底部，上面那段会给出 bottom=0，胶囊就被拼进长图两次。
    /// 这类带子的特征是 shift 一直很大（内容在 B 里任何位置都找不到），
    /// 所以再找一段"连续 shift>=thr 且延伸到接近底边"的带，从它的上边缘裁。
    static func classifyBottom(_ A: GrayImage, _ B: GrayImage, _ d: Int,
                               _ thr: Float = StitchParams.classifyThr) -> Int {
        let H = A.height
        let W = A.width
        let y0 = max(Int(Double(H) * (1.0 - StitchParams.maxOverlayFrac)), d, 0)
        if y0 >= H { return 0 }
        let rows = H - y0
        let n = usableWidth(W)

        var same = [Float](repeating: 0, count: rows)
        var shift = [Float](repeating: 0, count: rows)
        let ad = A.data
        let bd = B.data
        for k in 0..<rows {
            let y = y0 + k
            let ra = y * W
            let rc = (y - d) * W
            var s: Float = 0
            var t: Float = 0
            for x in 0..<n {
                let av = ad[ra + x]
                s += abs(av - bd[ra + x])
                t += abs(av - bd[rc + x])
            }
            same[k] = s / Float(n)
            shift[k] = t / Float(n)
        }

        // 最后一个 CONT 行
        var bClass = 0
        var k = rows - 1
        while k >= 0 {
            if same[k] >= thr && shift[k] < thr {
                bClass = H - 1 - (y0 + k)
                break
            }
            k -= 1
        }

        // 悬浮固定带：连续 shift>=thr 且下端接近屏幕底部
        let near = H - Int(StitchParams.overlayBandEndNear * Double(H))
        var bIsland = 0
        var runStart = -1
        for i in 0...rows {
            let big = i < rows && shift[i] >= thr
            if big && runStart < 0 {
                runStart = i
            } else if !big && runStart >= 0 {
                let len = i - runStart
                let yEnd = y0 + i - 1
                if len >= StitchParams.minOverlayH && yEnd >= near {
                    bIsland = max(bIsland, H - (y0 + runStart))
                }
                runStart = -1
            }
        }
        return max(bClass, bIsland)
    }

    /// 顶部覆盖层高度的对称判据：B[y] 若随内容滚动，应出现在 A[y+d]。
    static func classifyTop(_ A: GrayImage, _ B: GrayImage, _ d: Int,
                            _ thr: Float = StitchParams.classifyThr) -> Int {
        let H = B.height
        let W = B.width
        let y1 = min(Int(Double(H) * StitchParams.maxOverlayFrac), H - d)
        if y1 <= 0 { return 0 }
        let n = usableWidth(W)

        var first = -1
        let ad = A.data
        let bd = B.data
        for y in 0..<y1 {
            let r = y * W
            let rd = (y + d) * W
            var s: Float = 0
            var t: Float = 0
            for x in 0..<n {
                let bv = bd[r + x]
                s += abs(bv - ad[r + x])
                t += abs(bv - ad[rd + x])
            }
            let same = s / Float(n)
            let shift = t / Float(n)
            if same >= thr && shift < thr {
                first = y
                break
            }
        }
        return first > 0 ? first : 0
    }

    /// 用已经求出的 d 重新量覆盖层；没有 d 的对不参与。
    ///
    /// 多对时取中位数（同一批截图、同一个 App，覆盖层高度是常量）。
    /// 一对都不可用时退回 detectOverlays 的结果。
    static func refineOverlays(_ grays: [GrayImage], _ dList: [Int?],
                               _ top0: Int, _ bottom0: Int) -> (top: Int, bottom: Int) {
        var tops = [Int]()
        var bots = [Int]()
        for i in 0..<dList.count {
            guard let d = dList[i] else { continue }
            let t = classifyTop(grays[i], grays[i + 1], d)
            let b = classifyBottom(grays[i], grays[i + 1], d)
            if t > 0 { tops.append(t) }
            if b > 0 { bots.append(b) }
        }
        var top = tops.isEmpty ? top0 : medianInt(tops)
        let bottom = bots.isEmpty ? bottom0 : medianInt(bots)
        if top < StitchParams.minOverlayH { top = top0 }
        return (top, bottom)
    }

    static func medianInt(_ v: [Int]) -> Int {
        let s = v.sorted()
        if s.isEmpty { return 0 }
        return s[s.count / 2]
    }

    // MARK: - 偏移量搜索
    //
    // 指标演进史（重要，别再走回头路）：
    //   第 2 版：误差中位数 —— 正确和错误偏移处中位数都是 0，零判别力。
    //   第 4 版：整行完全匹配占比 frac —— 合成样本（整数滚动）下完美，
    //            但真机 UIScrollView 停下时滚动量是**小数**像素，iOS 截图会按小数
    //            偏移做双线性重采样，同一内容行的像素值差 1~120，frac 恒为 0，
    //            整组会被误判成"无重叠"。这是必须换指标的根本原因。
    //   第 5 版（当前）：纹理行归一化 L1 误差
    //            cost(d) = Σ|B[y]-A[y+d]| / Σ std(A[y+d])   只统计"有纹理"的行
    //            - 只统计有纹理的行：纯色行在任何偏移下都匹配，会稀释信号
    //            - 用"比值的和"而不是"逐行比值的均值"：后者会被低对比度行放大
    //              （分母接近 0），亚像素时会把真值淹没
    //            - 用 sum 而不是 median/trimmed：纯色行多时中位数退化为 0

    /// 抽样列数。必须和 Python 的 `A[:, ::cs]` 完全一致：
    /// numpy 切片对宽 1206、步长 4 取到 0,4,...,1204 共 302 列，
    /// 而 1206/4 = 301。差这一列会让 Swift 与已验证的 Python 行为不一致。
    @inline(__always)
    static func sampleCount(_ W: Int, _ cs: Int) -> Int {
        let s = max(1, cs)
        return (W - 1) / s + 1
    }

    /// 参与打分的列数：去掉最右侧的滚动条保护带。
    /// 见 `StitchParams.scrollbarGuardFrac` 的说明。
    @inline(__always)
    static func usableWidth(_ W: Int) -> Int {
        let cut = max(1, Int(StitchParams.scrollbarGuardFrac * Double(W)))
        return max(1, W - cut)
    }

    /// 每行的灰度标准差。与 d 无关，可以预先算一次。
    ///
    /// std 只依赖 A 的行本身，而 a = A[ys+d] 只是"取 A 的哪些行"，
    /// 所以整张 A 的行标准差表可以复用，省掉每个候选都重算的代价。
    ///
    /// 注意：这里刻意手写循环而不用 vDSP —— 用 vDSP 需要把"均值"以指针
    /// 形式传进去，多一层间接反而更慢，而且每行只有 1206/colStride 个元素，
    /// 循环本身不是瓶颈（实测整组搜索 0.4~0.7 秒）。
    static func rowSD(_ A: GrayImage, _ colStride: Int) -> [Float] {
        let W = A.width
        let H = A.height
        var out = [Float](repeating: 0, count: H)
        let cs = max(1, colStride)
        let n = sampleCount(usableWidth(A.width), cs)
        if n < 1 { return out }
        let invN = 1.0 / Float(n)
        A.data.withUnsafeBufferPointer { a in
            let ap = a.baseAddress!
            for y in 0..<H {
                let base = y * W
                var sum: Float = 0
                var i = 0
                while i < n {
                    sum += ap[base + i * cs]
                    i += 1
                }
                let mean = sum * invN
                var acc: Float = 0
                i = 0
                while i < n {
                    let dv = ap[base + i * cs] - mean
                    acc += dv * dv
                    i += 1
                }
                out[y] = acc > 0 ? (acc * invN).squareRoot() : 0
            }
        }
        return out
    }

    /// 偏移 d 处的打分结果
    struct CostResult {
        var cost: Float
        var usedRows: Int
        var ys: [Int]
        /// 每行归一化误差（rowMAD / max(rowSD, sdFloor)）
        var rne: [Float]
        /// 该行是否是"有纹理的行"
        var tex: [Bool]
    }

    /// cost = Σ rowMAD / Σ rowSD，只累加"有纹理且未被排除"的行。
    ///
    /// - Parameter wantDetail: 只有需要 rne/tex 去找动态区段时才设 true。
    ///   粗搜要扫 1000+ 个候选，每个都分配三个数组会造成大量无谓的分配，
    ///   实测在真机上这一项能让整组搜索慢一倍以上。
    static func costAt(_ A: GrayImage,
                       _ B: GrayImage,
                       _ d: Int,
                       _ top: Int,
                       _ bottom: Int,
                       _ sdA: [Float],
                       _ rowStride: Int,
                       _ colStride: Int,
                       _ exclude: [Bool]? = nil,
                       wantDetail: Bool = false) -> CostResult? {
        let H = A.height
        let W = A.width
        let nEnd = H - bottom - d
        if nEnd <= top { return nil }
        var ys = [Int]()
        ys.reserveCapacity((nEnd - top) / rowStride + 1)
        var y = top
        while y < nEnd { ys.append(y); y += rowStride }
        if ys.count < 8 { return nil }

        let n = ys.count
        let nc = sampleCount(usableWidth(W), colStride)
        if nc < 1 { return nil }

        var rne: [Float] = wantDetail ? [Float](repeating: 0, count: n) : []
        var tex: [Bool] = wantDetail ? [Bool](repeating: false, count: n) : []
        var sdSum: Float = 0
        var madSum: Float = 0
        var used = 0
        var scratch = [Float](repeating: 0, count: nc)
        let N = vDSP_Length(nc)
        let stride = vDSP_Stride(colStride)
        let tmin = StitchParams.textureMin
        let sfloor = StitchParams.sdFloor

        A.data.withUnsafeBufferPointer { a in
            B.data.withUnsafeBufferPointer { b in
                let ap = a.baseAddress!
                let bp = b.baseAddress!
                scratch.withUnsafeMutableBufferPointer { sc in
                    let sp = sc.baseAddress!
                    for k in 0..<n {
                        let yy = ys[k]
                        let ra = (yy + d) * W
                        let rb = yy * W
                        // 抽样比较：每 colStride 列取 1 列
                        vDSP_vsub(ap + ra, stride, bp + rb, stride, sp, 1, N)
                        vDSP_vabs(sp, 1, sp, 1, N)
                        var mad: Float = 0
                        vDSP_meanv(sp, 1, &mad, N)
                        let sd = sdA[yy + d]
                        let isTex = sd >= tmin
                        if wantDetail {
                            let den = sd > sfloor ? sd : sfloor
                            rne[k] = mad / den
                            tex[k] = isTex
                        }
                        if isTex && (exclude == nil || !exclude![yy]) {
                            used += 1
                            sdSum += sd
                            madSum += mad
                        }
                    }
                }
            }
        }
        if used < 8 || sdSum < 1e-6 { return nil }
        return CostResult(cost: madSum / sdSum, usedRows: used,
                          ys: wantDetail ? ys : [], rne: rne, tex: tex)
    }

    /// 扫描 [lo, hi]，返回 {d: cost}（按 d 升序保存，方便取 topK）
    static func scanCurve(_ A: GrayImage,
                          _ B: GrayImage,
                          _ top: Int,
                          _ bottom: Int,
                          _ lo: Int,
                          _ hi: Int,
                          _ sdA: [Float],
                          _ rowStride: Int,
                          _ colStride: Int,
                          _ exclude: [Bool]?) -> [(d: Int, cost: Float)] {
        var out = [(d: Int, cost: Float)]()
        out.reserveCapacity(hi - lo + 1)
        for d in lo...hi {
            if let got = costAt(A, B, d, top, bottom, sdA, rowStride, colStride, exclude) {
                out.append((d, got.cost))
            }
        }
        return out
    }

    /// 找出"连续 >= minLen 行、是纹理行、但误差很大"的区段。
    ///
    /// 这些就是视频 / 进度条 / 广告 / 动画 —— 两张截图里内容真的不一样，
    /// 不该参与打分。返回 [(y0, y1)]（屏幕坐标，含端点）。
    static func badBands(_ rne: [Float], _ ys: [Int], _ tex: [Bool],
                         _ minLen: Int) -> [(Int, Int)] {
        var groups: [(Int, Int)] = []
        var s0 = -1
        var prev = -1
        for k in 0..<rne.count where rne[k] >= StitchParams.badRowCost && tex[k] {
            if s0 < 0 {
                s0 = k
            } else if k - prev > 1 {
                groups.append((s0, prev))
                s0 = k
            }
            prev = k
        }
        if s0 >= 0 { groups.append((s0, prev)) }
        return groups
            .filter { ($0.1 - $0.0 + 1) >= minLen }
            .map { (ys[$0.0], ys[$0.1]) }
    }

    /// 在 [lo, hi] 里找 cost 最小的 d，并迭代排除动态区段。
    /// 返回 (d, cost, exclude, curve)，curve 是最后一轮的 [(d, cost)]。
    static func exclusionSearch(_ A: GrayImage,
                                _ B: GrayImage,
                                _ top: Int,
                                _ bottom: Int,
                                _ lo: Int,
                                _ hi: Int,
                                _ sdA: [Float],
                                _ rowStride: Int,
                                _ colStride: Int,
                                _ badMin: Int,
                                _ maxExcludedFrac: Float)
        -> (d: Int?, cost: Float, exclude: [Bool], curve: [(d: Int, cost: Float)]) {
        let H = A.height
        var exclude = [Bool](repeating: false, count: H)
        var bestD: Int?
        var bestC: Float = 0
        var curve: [(d: Int, cost: Float)] = []

        for _ in 0..<StitchParams.badBandIter {
            curve = scanCurve(A, B, top, bottom, lo, hi, sdA, rowStride, colStride, exclude)
            if curve.isEmpty {
                return (nil, 0, exclude, curve)
            }
            var cand = curve[0]
            for e in curve where e.cost < cand.cost { cand = e }
            if cand.d == bestD {
                bestC = min(bestC, cand.cost)
                break
            }
            bestD = cand.d
            bestC = cand.cost

            guard let got = costAt(A, B, cand.d, top, bottom, sdA, rowStride,
                                   colStride, exclude, wantDetail: true) else { break }
            let bands = badBands(got.rne, got.ys, got.tex, badMin)
            if bands.isEmpty { break }
            var newExcl = exclude
            for (y0, y1) in bands {
                let a = max(0, y0), b = min(H - 1, y1)
                if a <= b { for y in a...b { newExcl[y] = true } }
            }
            // 排除过多说明这个偏移本身可疑，别继续"作弊"
            var exclCount = 0
            var total = 0
            for y in top..<(H - bottom) {
                total += 1
                if newExcl[y] { exclCount += 1 }
            }
            if total > 0 && Float(exclCount) / Float(total) > maxExcludedFrac { break }
            exclude = newExcl
        }
        return (bestD, bestC, exclude, curve)
    }

    /// [y0,y1) 区间内、偏移 d 的归一化 L1 代价（只统计纹理行）。
    /// 与全局 costAt 用同一套度量，保证"分段最优"和"全局最优"可比。
    static func bandCost(_ A: GrayImage,
                         _ B: GrayImage,
                         _ d: Int,
                         _ y0: Int,
                         _ y1In: Int,
                         _ sdA: [Float],
                         _ colStride: Int) -> Float? {
        let H = A.height
        let W = A.width
        let y1 = min(y1In, H - d)
        if y1 <= y0 + 4 { return nil }
        let nc = sampleCount(usableWidth(W), colStride)
        if nc < 1 { return nil }
        var texCount = 0
        var sdSum: Float = 0
        var madSum: Float = 0
        var scratch = [Float](repeating: 0, count: nc)
        let N = vDSP_Length(nc)
        let stride = vDSP_Stride(colStride)
        let tmin = StitchParams.textureMin

        A.data.withUnsafeBufferPointer { a in
            B.data.withUnsafeBufferPointer { b in
                let ap = a.baseAddress!
                let bp = b.baseAddress!
                scratch.withUnsafeMutableBufferPointer { sc in
                    let sp = sc.baseAddress!
                    for yy in y0..<y1 {
                        let sd = sdA[yy + d]
                        if sd < tmin { continue }
                        texCount += 1
                        let ra = (yy + d) * W
                        let rb = yy * W
                        vDSP_vsub(ap + ra, stride, bp + rb, stride, sp, 1, N)
                        vDSP_vabs(sp, 1, sp, 1, N)
                        var mad: Float = 0
                        vDSP_meanv(sp, 1, &mad, N)
                        sdSum += sd
                        madSum += mad
                    }
                }
            }
        }
        if texCount < 8 || sdSum < 1e-6 { return nil }
        return madSum / sdSum
    }

    /// 分带一致性：把有效区间横切 bandCount 段，每段各自在 d±bandWin 内
    /// 找自己的最优偏移，统计"指向同一个 d（偏差 <= bandAgreeTol）"的段数。
    ///
    /// 这是真正的判别闸门。为什么不用绝对 cost 或峰值比（实测数据）：
    ///   - 绝对 cost：亚像素+视频场景下真匹配 0.67~0.99，无关两图 0.73~1.36，重叠
    ///   - 峰值比：真匹配最高 0.42，无关两图最低 0.35，重叠
    ///   - 分带投票：真匹配最少 3/4 段一致，无关两图最多 2/4，4/5/6 段均稳定分离
    /// 道理很直观：真匹配时上下每一段都指向同一个滚动量；无关两图即使全局
    /// argmin 恰好落在某个 d，各段也会各指一处。
    static func bandVotes(_ A: GrayImage,
                          _ B: GrayImage,
                          _ d: Int,
                          _ top: Int,
                          _ bottom: Int,
                          _ colStride: Int,
                          _ sdA: [Float]? = nil) -> (agree: Int, devs: [Int]) {
        let H = A.height
        let nEnd = H - bottom - d
        if nEnd <= top + 16 { return (0, []) }
        let sd = sdA ?? rowSD(A, colStride)
        var ysTex = [Int]()
        for y in top..<nEnd where sd[y + d] >= StitchParams.textureMin {
            ysTex.append(y)
        }
        if ysTex.count < StitchParams.bandCount * 8 { return (0, []) }
        let yLo = ysTex[0]
        let yHi = ysTex[ysTex.count - 1]
        let span = yHi - yLo + 1

        var devs = [Int]()
        for k in 0..<StitchParams.bandCount {
            let b0 = yLo + span * k / StitchParams.bandCount
            let b1 = yLo + span * (k + 1) / StitchParams.bandCount
            var bestDD: Int?
            var bestC: Float?
            var cMin: Float?
            var cMax: Float?
            for dd in max(1, d - StitchParams.bandWin)...(d + StitchParams.bandWin) {
                guard let c = bandCost(A, B, dd, b0, b1, sd, colStride) else { continue }
                if cMin == nil || c < cMin! { cMin = c }
                if cMax == nil || c > cMax! { cMax = c }
                if bestC == nil || c < bestC! {
                    bestC = c
                    bestDD = dd
                }
            }
            guard let bd = bestDD, let bc = bestC, let cmx = cMax else { continue }
            // 平坦带弃权：曲线几乎是平的，说明这一段内容在两张图里本来就一样
            let spread = cmx > 1e-9 ? (cmx - (cMin ?? 0)) / cmx : 0
            if spread < StitchParams.bandSpreadMin { continue }
            // 代价整体很高的带，即使曲线有峰也不能算"同意"：无关两图就是这种
            if bc > StitchParams.bandMaxCost { continue }
            devs.append(bd - d)
        }
        var agree = 0
        for x in devs where abs(x) <= StitchParams.bandAgreeTol { agree += 1 }
        return (agree, devs)
    }

    /// A、B 同尺寸灰度图。返回 (d, cost)；d == nil 表示没找到可靠重叠。
    ///
    /// 两段式：粗搜（抽样行+抽样列，d 全分辨率）定位，再全分辨率精修。
    /// 闸门任一不过就判"断开"（宁可硬拼让用户拖，也不瞎猜）：
    ///   1) 分带一致性 >= minBandAgree —— 主判据，见 bandVotes 注释
    ///   2) 参与打分的纹理行 >= minMatchRows —— 不是靠排除作弊
    ///   3) 保留的纹理行占比 >= minUsedFrac
    /// 绝对 cost 与峰值比都不再作闸门（正负例区间重叠），只作诊断值返回。
    static func findOffset(_ A: GrayImage, _ B: GrayImage, _ top: Int, _ bottom: Int) -> (d: Int?, cost: Float) {
        let H = A.height
        let minOverlap = max(24, Int(StitchParams.minOverlapFrac * Double(H)))
        let dHi = H - bottom - minOverlap - top
        let minScroll = max(Int(StitchParams.minScrollFrac * Double(H - top - bottom)),
                            StitchParams.fineWindow)
        let lo = minScroll
        let hi = dHi
        if hi - lo < 8 { return (nil, 0) }

        // ---- 第 1 轮：粗搜（抽样行列，d 全分辨率）
        let sdC = rowSD(A, StitchParams.coarseColStride)
        let coarse = exclusionSearch(A, B, top, bottom, lo, hi, sdC,
                                     StitchParams.coarseRowStride,
                                     StitchParams.coarseColStride,
                                     max(8, StitchParams.badBandMin / StitchParams.coarseRowStride),
                                     StitchParams.maxExcludedFrac)
        if coarse.d == nil || coarse.curve.isEmpty { return (nil, 0) }

        // ---- 粗搜取前 TOPK 个候选，逐个精修 + 分带投票，取第一个通过闸门的
        // 为什么要取多个：接近搜索上界 dHi 的候选只有很少的行可比，随机噪声
        // 也容易压出低代价。实测 seed888/tail=0.5 时粗搜 argmin 落在 d=2463
        // （真值 1438），那个位置的分带一致性只有 1/4，而真值是 4/4。
        // 所以"代价最低"不能直接当结论，必须让分带投票来裁决。
        // 注意排序必须带 d 作为次要键：Swift 的 sort 不保证稳定，而 Python 的
        // sorted 是稳定的（代价并列时按 d 升序）。不带次要键的话，并列候选的
        // 顺序会随实现变化，进而影响"第一个通过闸门的候选"是哪一个。
        let cands = coarse.curve.sorted {
            $0.cost != $1.cost ? $0.cost < $1.cost : $0.d < $1.d
        }.prefix(StitchParams.candTopK)
        let sdA1 = rowSD(A, StitchParams.fineColStride)
        var best: (agree: Int, cost: Float, d: Int)?

        for cand in cands {
            let fLo = max(lo, cand.d - StitchParams.fineWindow * 2)
            let fHi = min(hi, cand.d + StitchParams.fineWindow * 2)
            let fine = exclusionSearch(A, B, top, bottom, fLo, fHi, sdA1,
                                       StitchParams.fineRowStride,
                                       StitchParams.fineColStride,
                                       StitchParams.badBandMin,
                                       StitchParams.maxExcludedFrac)
            guard let fd = fine.d else { continue }
            let votes = bandVotes(A, B, fd, top, bottom,
                                  StitchParams.coarseColStride, sdC)
            // 多数判据：一致段数必须 >= 反对段数。
            // 平坦带已弃权，devs 里剩下的都是"真的看了"的带；
            // 只要求 agree >= 2 而不要求多数的话，2 对 3 反对也会通过。
            if votes.agree < StitchParams.minBandAgree
                || votes.agree < votes.devs.count - votes.agree { continue }
            // 分带投票通过：再核纹理行数量与保留比例
            guard let got = costAt(A, B, fd, top, bottom, sdA1,
                                   StitchParams.fineRowStride,
                                   StitchParams.fineColStride, fine.exclude,
                                   wantDetail: true) else { continue }
            let nTex = got.tex.filter { $0 }.count
            if nTex < StitchParams.minMatchRows { continue }
            if nTex > 0 && Float(got.usedRows) / Float(nTex) < StitchParams.minUsedFrac { continue }

            if best == nil || votes.agree > best!.agree
                || (votes.agree == best!.agree && got.cost < best!.cost) {
                best = (votes.agree, got.cost, fd)
                if votes.agree >= StitchParams.bandCount { break }   // 全票通过
            }
        }

        guard let b = best else { return (nil, coarse.cost) }

        // ---- 收尾：在 best.d 的 ±1 上用全行全列复核一次
        // 精修阶段用 rowStride=2 抽样，行相位可能偏 1 像素（实测 dynamic pair3
        // 因此差 1px，且 1882/1883/1884 三个候选在抽样下代价并列 0）。
        // 这里必须用全行的代价重新比较，不能拿抽样代价当基准 —— 否则并列时永远
        // 停在先找到的那个。只比 3 个候选，代价很小。
        let sdFull = rowSD(A, 1)
        var finalD = b.d
        var finalC: Float?
        for dd in [b.d - 1, b.d, b.d + 1] where dd >= lo && dd <= hi {
            guard let got = costAt(A, B, dd, top, bottom, sdFull, 1, 1) else { continue }
            if finalC == nil || got.cost < finalC! {
                finalD = dd
                finalC = got.cost
            }
        }
        return (finalD, finalC ?? b.cost)
    }

    // MARK: - 拼接方案

    /// 输出里的一段：从第 imageIndex 张裁剪图的第 startRow 行开始，取 rowCount 行。
    struct Segment {
        var imageIndex: Int
        var startRow: Int
        var rowCount: Int
    }

    /// 全局坐标：第 i 张截图覆盖内容区 [S[i], S[i]+contentH)，S[0]=0、S[i]=S[i-1]+d[i-1]。
    /// 切点 cuts[i] 表示"第 i 张与第 i+1 张在哪里换手"，取值范围 [S[i+1], S[i]+contentH]。
    /// 只要在这个范围内，换手处两边像素完全一样，所以拖动切点不会破坏画面。
    /// 总高度恒为 S[m-1] + contentH，与切点无关。
    static func starts(_ offsets: [Int]) -> [Int] {
        // 必须显式处理空数组：`for i in 1...0` 会触发
        // "Fatal error: Range requires lowerBound <= upperBound" 直接闪退。
        // 单张截图自成一组时 offsets 就是空的（0 对相邻截图）。
        if offsets.isEmpty { return [0] }
        var S = [Int](repeating: 0, count: offsets.count + 1)
        for i in 1...offsets.count { S[i] = S[i - 1] + offsets[i - 1] }
        return S
    }

    static func plan(_ offsets: [Int], contentHeight: Int, cuts: [Int]) -> [Segment] {
        let m = offsets.count + 1
        if m == 1 {
            return [Segment(imageIndex: 0, startRow: 0, rowCount: contentHeight)]
        }
        let S = starts(offsets)
        let G = S[m - 1] + contentHeight

        var segs = [Segment]()
        segs.reserveCapacity(m)
        segs.append(Segment(imageIndex: 0, startRow: 0, rowCount: cuts[0]))
        if m > 2 {
            for i in 1..<(m - 1) {
                segs.append(Segment(imageIndex: i,
                                    startRow: cuts[i - 1] - S[i],
                                    rowCount: cuts[i] - cuts[i - 1]))
            }
        }
        segs.append(Segment(imageIndex: m - 1,
                            startRow: cuts[m - 2] - S[m - 1],
                            rowCount: G - cuts[m - 2]))
        return segs
    }

    /// 某个切点允许的取值范围。拖动时用它做夹紧。
    static func cutRange(_ i: Int, offsets: [Int], contentHeight: Int, cuts: [Int]) -> ClosedRange<Int> {
        let m = offsets.count + 1
        let S = starts(offsets)
        var lo = (i + 1 < m) ? S[i + 1] : 0
        if i > 0 { lo = max(lo, cuts[i - 1]) }
        var hi = S[i] + contentHeight
        if i + 1 < cuts.count { hi = min(hi, cuts[i + 1]) }
        if hi < lo { hi = lo }
        return lo...hi
    }

    /// 默认切点：每张都取到自己的最下沿（等价于"上一张全保留，下一张只取新内容"）。
    static func defaultCuts(_ offsets: [Int], contentHeight: Int) -> [Int] {
        let S = starts(offsets)
        return (0..<offsets.count).map { S[$0] + contentHeight }
    }

    /// 把 plan 出来的片段拼成一张图。
    ///
    /// 直接从未裁剪的原图里取行（而不是先给每张做一份 `cropped` 副本）。
    /// 这是纯内存优化，输出像素与旧实现完全一致：
    /// 旧写法要额外持有 12 份裁剪副本（约 130MB），在手机上很容易被系统杀掉。
    ///
    /// 坐标换算：`Segment.startRow` 是"内容区坐标"。
    ///   - 第 0 张且保留 chrome 时，内容区从原图第 `chromeH` 行开始
    ///   - 其余情况内容区从原图第 `top` 行开始
    static func render(_ images: [RGBABuffer],
                       segments: [Segment],
                       top: Int,
                       bottom: Int,
                       chromeH: Int) -> RGBABuffer {
        let W = images[0].width
        var totalH = 0
        for s in segments {
            totalH += ((s.imageIndex == 0) ? chromeH : 0) + s.rowCount
        }
        var out = RGBABuffer(width: W, height: max(totalH, 1), colorSpace: images[0].colorSpace)
        let rowBytes = W * 4
        var cursor = 0
        // 单张图允许拷贝到的最大行号（不含），保证不会把底部覆盖层抄进长图
        let maxRow = max(0, images[0].height - bottom)

        out.pixels.withUnsafeMutableBufferPointer { dst in
            let dp = dst.baseAddress!

            func copyRows(_ src: RGBABuffer, from: Int, rows: Int) {
                guard rows > 0 else { return }
                let s = min(max(from, 0), min(src.height, maxRow))
                let take = min(rows, min(src.height, maxRow) - s)
                guard take > 0 else { return }
                src.pixels.withUnsafeBufferPointer { sp in
                    memcpy(dp + cursor * rowBytes,
                           sp.baseAddress! + s * rowBytes,
                           take * rowBytes)
                }
                cursor += take
                if take < rows {
                    // 数据不足时补白，绝不让数组越界
                    let pad = rows - take
                    memset(dp + cursor * rowBytes, 255, pad * rowBytes)
                    cursor += pad
                }
            }

            for s in segments {
                let src = images[s.imageIndex]
                let hasChrome = (s.imageIndex == 0 && chromeH > 0)
                if hasChrome {
                    copyRows(src, from: 0, rows: chromeH)
                }
                let base = hasChrome ? chromeH : top
                copyRows(src, from: base + s.startRow, rows: s.rowCount)
            }
        }
        return out.cropped(top: 0, bottom: max(0, out.height - cursor))
    }

    /// 遇到"没找到重叠"的接缝时用的简单拼接：两张直接首尾相接，中间加一条分隔线。
    /// 同样直接从未裁剪原图取行，不额外做 `cropped` 副本。
    static func renderWithGaps(_ images: [RGBABuffer],
                               offsets: [Int?],
                               top: Int,
                               bottom: Int,
                               contentHeight: Int,
                               chromeH: Int) -> RGBABuffer {
        let W = images[0].width
        // 第 0 张：保留 chrome 时从第 0 行起，否则从内容区顶端 top 起；都止于 H-bottom
        let firstStart = chromeH > 0 ? 0 : top
        let firstRows = max(0, images[0].height - bottom - firstStart)
        var totalH = firstRows
        for (i, d) in offsets.enumerated() {
            if let d = d {
                totalH += d
            } else {
                totalH += StitchParams.dividerHeight + (images[i + 1].height - top - bottom)
            }
        }

        var out = RGBABuffer(width: W, height: max(totalH, 1), colorSpace: images[0].colorSpace)
        let rowBytes = W * 4
        var cursor = 0
        let maxRow = max(0, images[0].height - bottom)

        out.pixels.withUnsafeMutableBufferPointer { dst in
            let dp = dst.baseAddress!

            func append(_ src: RGBABuffer, from: Int, rows: Int) {
                guard rows > 0 else { return }
                let s = min(max(from, 0), min(src.height, maxRow))
                let take = min(rows, min(src.height, maxRow) - s)
                guard take > 0 else { return }
                src.pixels.withUnsafeBufferPointer { sp in
                    memcpy(dp + cursor * rowBytes,
                           sp.baseAddress! + s * rowBytes,
                           take * rowBytes)
                }
                cursor += take
            }

            func divider() {
                for y in 0..<StitchParams.dividerHeight {
                    let row = (cursor + y) * rowBytes
                    for x in 0..<W {
                        let o = row + x * 4
                        dp[o] = StitchParams.dividerGray
                        dp[o + 1] = StitchParams.dividerGray
                        dp[o + 2] = StitchParams.dividerGray
                        dp[o + 3] = 255
                    }
                }
                cursor += StitchParams.dividerHeight
            }

            append(images[0], from: firstStart, rows: firstRows)
            for (i, d) in offsets.enumerated() {
                let src = images[i + 1]
                if let d = d {
                    // 只取"新露出来的 d 行"：内容区第 contentHeight-d 行开始
                    append(src, from: top + (contentHeight - d), rows: d)
                } else {
                    divider()
                    append(src, from: top, rows: contentHeight)
                }
            }
        }
        return out.cropped(top: 0, bottom: max(0, out.height - cursor))
    }

    /// 分析一组截图：量覆盖层 + 求每对相邻截图的滚动量。
    ///
    /// 单独抽出来是为了**及时释放灰度图**：灰度图占用的内存和原图一样大
    /// （12 张 1206×2622 的 Float 灰度图约 150MB），一旦进入渲染阶段就不再需要，
    /// 而渲染要新分配一张最多 145MB 的长图。放在同一个函数里两者会同时存活。
    static func analyze(_ images: [RGBABuffer]) -> (top: Int, bottom: Int,
                                                    offsets: [Int?], seams: [Seam]) {
        let grays = images.map { $0.grayscale() }
        var (top, bottom) = detectOverlays(grays)

        var offsets = [Int?]()
        for i in 0..<(grays.count - 1) {
            let (d, _) = findOffset(grays[i], grays[i + 1], top, bottom)
            offsets.append(d)
        }

        // 第二轮：用已经求出的 d 反过来量覆盖层（classifyTop/Bottom），再重算 d。
        // 详见 classifyBottom 的注释：底部少裁会让真实内容被挤掉。
        let refined = refineOverlays(grays, offsets, top, bottom)
        if refined.top != top || refined.bottom != bottom {
            top = refined.top
            bottom = refined.bottom
            for i in 0..<(grays.count - 1) {
                offsets[i] = findOffset(grays[i], grays[i + 1], top, bottom).d
            }
        }

        var seams = [Seam]()
        for i in 0..<offsets.count {
            let c: Float
            if let d = offsets[i] {
                c = costAt(grays[i], grays[i + 1], d, top, bottom,
                           rowSD(grays[i], 1), 1, 1)?.cost ?? 0
            } else {
                c = 0
            }
            seams.append(Seam(index: i, offset: offsets[i], cost: c))
        }
        return (top, bottom, offsets, seams)
    }

    /// 拼一组（调用方保证这一组属于同一次长截图）。
    /// keepFirstChrome: 第一张的状态栏+导航栏保留在长图最上方，后续截图裁掉。
    static func stitchGroup(_ images: [RGBABuffer],
                            keepFirstChrome: Bool = true) -> StitchResult {
        let a = analyze(images)
        return assemble(images, top: a.top, bottom: a.bottom,
                        offsets: a.offsets, seams: a.seams,
                        keepFirstChrome: keepFirstChrome)
    }

    /// 已知道 offsets 时直接组装（拖动接缝后重拼走这条路，不用再搜一遍）。
    static func assemble(_ images: [RGBABuffer],
                         top: Int,
                         bottom: Int,
                         offsets: [Int?],
                         seams: [Seam],
                         keepFirstChrome: Bool) -> StitchResult {
        let contentH = images[0].height - top - bottom
        let chromeH = keepFirstChrome ? top : 0

        var cuts: [Int] = []
        var out: RGBABuffer
        if offsets.contains(where: { $0 == nil }) {
            out = renderWithGaps(images, offsets: offsets, top: top, bottom: bottom,
                                 contentHeight: contentH, chromeH: chromeH)
        } else {
            let ints = offsets.map { $0! }
            cuts = defaultCuts(ints, contentHeight: contentH)
            let segs = plan(ints, contentHeight: contentH, cuts: cuts)
            out = render(images, segments: segs, top: top, bottom: bottom, chromeH: chromeH)
        }

        return StitchResult(indices: Array(0..<images.count),
                            image: out,
                            seams: seams,
                            offsets: offsets,
                            topOverlay: top,
                            bottomOverlay: bottom,
                            contentHeight: contentH,
                            chromeHeight: chromeH,
                            cuts: cuts)
    }

    /// 用户拖动接缝后重拼。只对"全部接缝都找到重叠"的组有效。
    static func restitch(_ images: [RGBABuffer],
                         top: Int,
                         bottom: Int,
                         offsets: [Int?],
                         cuts: [Int],
                         keepFirstChrome: Bool) -> RGBABuffer? {
        guard !offsets.contains(where: { $0 == nil }) else { return nil }
        let ints = offsets.map { $0! }
        let contentH = images[0].height - top - bottom
        let chromeH = keepFirstChrome ? top : 0
        let segs = plan(ints, contentHeight: contentH, cuts: cuts)
        return render(images, segments: segs, top: top, bottom: bottom, chromeH: chromeH)
    }

    /// 分组分析结果。渲染阶段只靠这个结构就够了，不再需要灰度图。
    struct GroupPlan {
        var indices: [Int]
        var top: Int
        var bottom: Int
        var offsets: [Int?]
        /// 每对匹配的代价（越小越像；NaN 表示该对判定为断开）
        var costs: [Float]
    }

    /// 阶段 1：只用灰度图做全部分析，返回分组方案。
    ///
    /// 单独抽成函数是为了让灰度图在返回时**立刻释放**。灰度图总内存和原图相当
    /// （12 张 1206×2622 的 Float 灰度图约 150MB），而渲染阶段还要新分配
    /// 一张最多 145MB 的长图；两者若同时存活，真机上很容易被系统杀掉。
    static func analyzeAll(_ images: [RGBABuffer],
                           timestamps: [TimeInterval]?) -> [GroupPlan] {
        let n = images.count
        let grays = images.map { $0.grayscale() }

        // 逐对求偏移（用这一对自身的覆盖层高度，避免不同来源的截图互相污染）
        var pairOffsets = [Int?](repeating: nil, count: n - 1)
        var pairCost = [Float](repeating: 0, count: n - 1)
        var breaks = [Int]()
        for i in 0..<(n - 1) {
            let (top, bottom) = detectOverlays([grays[i], grays[i + 1]])
            let (d, c) = findOffset(grays[i], grays[i + 1], top, bottom)
            pairOffsets[i] = d
            pairCost[i] = c
            var brk = (d == nil)
            if let ts = timestamps, i + 1 < ts.count,
               ts[i + 1] - ts[i] > StitchParams.groupTimeGap {
                brk = true
            }
            if brk { breaks.append(i) }
        }

        var groups = [[Int]]()
        var start = 0
        for b in breaks {
            groups.append(Array(start...b))
            start = b + 1
        }
        groups.append(Array(start..<n))

        var plans = [GroupPlan]()
        plans.reserveCapacity(groups.count)
        for g in groups {
            let sub = g.map { grays[$0] }
            var (top, bottom) = detectOverlays(sub)
            var offsets = [Int?]()
            var costs = [Float]()
            for k in 0..<(g.count - 1) {
                offsets.append(pairOffsets[g[k]])
                costs.append(pairCost[g[k]])
            }

            // 第二轮：用已经求出的 d 反过来量覆盖层（classifyTop/Bottom），再重算 d。
            // 这一步才是修"截图不全"的关键：底部少裁 252 行会让 252 行真实内容被挤掉。
            // 第一轮那个估计在深色半透明覆盖层下往往偏小（bottom 24 而非 276），
            // 但 d 本身对它不敏感 —— 实测真实 5 对在任何 (top,bottom) 组合下
            // d 都恒定 1048/1341/1109/778。
            let refined = refineOverlays(sub, offsets, top, bottom)
            if refined.top != top || refined.bottom != bottom {
                top = refined.top
                bottom = refined.bottom
                for k in 0..<(g.count - 1) {
                    let (d, c) = findOffset(grays[g[k]], grays[g[k + 1]], top, bottom)
                    offsets[k] = d
                    costs[k] = c
                }
            }
            plans.append(GroupPlan(indices: g, top: top, bottom: bottom,
                                   offsets: offsets, costs: costs))
        }
        // 只保留真正能拼的组（至少 2 张）。
        // 单张的组是"这一对没找到重叠"的副产物：它的长图就是原截图本身，
        // 没有任何拼接价值，显示出来只会让用户以为拼错了。
        // 顺便这也避开了 `starts([])` 这条曾经直接闪退的路径。
        return plans.filter { $0.indices.count >= 2 }
    }

    /// 把一串截图自动分成若干组，每组拼一张长图。
    ///
    /// 分组规则（任一命中就断开）：
    ///   1. 时间间隔 > groupTimeGap 秒 —— 主信号，最可靠
    ///   2. 相邻两张找不到可信的滚动偏移 —— 兜底
    ///
    /// 性能要点：每对相邻截图只搜一次偏移，结果缓存下来给后面的组装复用。
    /// 否则 10 张图要搜 9 + 9 次，手机上会明显卡顿。
    static func stitchAll(_ images: [RGBABuffer],
                          timestamps: [TimeInterval]? = nil,
                          keepFirstChrome: Bool = true) -> [StitchResult] {
        guard !images.isEmpty else { return [] }
        if images.count == 1 {
            return [stitchGroup(images, keepFirstChrome: keepFirstChrome)]
        }

        // 阶段 1：分析（此函数返回后灰度图即被释放）
        let plans = analyzeAll(images, timestamps: timestamps)

        // 阶段 2：渲染（内存里只剩原图和正在生成的长图）
        var results = [StitchResult]()
        results.reserveCapacity(plans.count)
        for p in plans {
            let sub = p.indices.map { images[$0] }
            var seams = [Seam]()
            for k in 0..<p.offsets.count {
                seams.append(Seam(index: k, offset: p.offsets[k], cost: p.costs[k]))
            }
            var r = assemble(sub, top: p.top, bottom: p.bottom,
                             offsets: p.offsets, seams: seams,
                             keepFirstChrome: keepFirstChrome)
            r.indices = p.indices
            results.append(r)
        }
        return results
    }
}
