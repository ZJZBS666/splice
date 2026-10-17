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
    static let coarseScale = 4
    static let fineWindow = 10
    static let minOverlapFrac = 0.06
    static let minScrollFrac = 0.20
    static let matchFracThreshold: Float = 0.55
    static let exactEps: Float = 0.5
    static let minMatchRows = 30
    static let maxExcludedFrac: Float = 0.90
    static let staticEps: Float = 1.5
    static let maxOverlayFrac = 0.22
    static let minOverlayH = 60
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
    /// 匹配置信度 0...1
    var confidence: Float

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

    /// 返回每行是否"在所有截图里完全一致"。
    ///
    /// 语义必须和 Python 原型完全一致：
    ///   diff[y] = max over 所有截图对 ( mean over x |a - b| )
    ///   static[y] = diff[y] < STATIC_EPS
    /// 注意是"行内平均绝对差"，不是"行内最大差"。两者在覆盖层上都是 0，
    /// 但内容里的稀疏文字行差别很大，用最大差会误判成非静止，导致覆盖层变短。
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
        let invW = 1.0 / Float(W)
        var scratch = [Float](repeating: 0, count: W)
        var sum: Float = 0
        let N = vDSP_Length(W)

        for (i, j) in pairs {
            grays[i].data.withUnsafeBufferPointer { a in
                grays[j].data.withUnsafeBufferPointer { b in
                    let ap = a.baseAddress!
                    let bp = b.baseAddress!
                    scratch.withUnsafeMutableBufferPointer { sc in
                        let sp = sc.baseAddress!
                        for y in 0..<H where isStatic[y] {
                            let base = y * W
                            // scratch = a - b
                            vDSP_vsub(ap + base, 1, bp + base, 1, sp, 1, N)
                            // scratch = |scratch|
                            vDSP_vabs(sp, 1, sp, 1, N)
                            // sum = Σ scratch
                            vDSP_sve(sp, 1, &sum, N)
                            if sum * invW >= StitchParams.staticEps {
                                isStatic[y] = false
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

    // MARK: - 偏移量搜索

    struct MatchStats {
        var frac: Float
        var ys: [Int]
        var errs: [Float]
        /// true 表示被剪枝提前中止，frac 不可信
        var aborted: Bool
    }

    /// frac = 有效行里"整行完全匹配"的比例；ys/errs 供后续找遮挡区段用。
    ///
    /// - Parameter pruneBelow: 当"剩下所有行全部匹配"也已经追不上这个 frac 时立刻中止。
    ///   这是纯剪枝，不改变最优解，但让搜索快一到两个数量级。
    static func matchFraction(_ A: GrayImage,
                              _ B: GrayImage,
                              _ d: Int,
                              _ top: Int,
                              _ bottom: Int,
                              _ exclude: [Bool]?,
                              pruneBelow: Float = -1) -> MatchStats {
        let H = A.height
        let W = A.width
        let nEnd = H - bottom - d
        if nEnd <= top {
            return MatchStats(frac: 0, ys: [], errs: [], aborted: false)
        }
        var ys = [Int]()
        ys.reserveCapacity(nEnd - top)
        for y in top..<nEnd {
            if let ex = exclude, ex[y] { continue }
            ys.append(y)
        }
        let n = ys.count
        if n < 8 {
            return MatchStats(frac: 0, ys: [], errs: [], aborted: false)
        }

        var errs = [Float](repeating: 0, count: n)
        var hits = 0
        var aborted = false
        var scratch = [Float](repeating: 0, count: W)
        let N = vDSP_Length(W)
        let invN = 1.0 / Float(n)

        A.data.withUnsafeBufferPointer { a in
            B.data.withUnsafeBufferPointer { b in
                let ap = a.baseAddress!
                let bp = b.baseAddress!
                scratch.withUnsafeMutableBufferPointer { sc in
                    let sp = sc.baseAddress!
                    for k in 0..<n {
                        let y = ys[k]
                        let ra = (y + d) * W
                        let rb = y * W
                        vDSP_vsub(ap + ra, 1, bp + rb, 1, sp, 1, N)
                        vDSP_vabs(sp, 1, sp, 1, N)
                        var mx: Float = 0
                        vDSP_maxv(sp, 1, &mx, N)
                        errs[k] = mx
                        if mx < StitchParams.exactEps { hits += 1 }

                        if pruneBelow >= 0 {
                            let potential = Float(hits + (n - k - 1)) * invN
                            if potential <= pruneBelow {
                                aborted = true
                                return
                            }
                        }
                    }
                }
            }
        }
        if aborted {
            return MatchStats(frac: -1, ys: ys, errs: [], aborted: true)
        }
        return MatchStats(frac: Float(hits) * invN, ys: ys, errs: errs, aborted: false)
    }

    /// 从逐行误差里找出连续 >= minLen 行、且完全不匹配的区段，返回 [(y0, y1)]。
    static func badBands(_ errs: [Float], _ ys: [Int], _ minLen: Int) -> [(Int, Int)] {
        var idx = [Int]()
        for (k, e) in errs.enumerated() where e >= StitchParams.exactEps {
            idx.append(k)
        }
        if idx.isEmpty { return [] }
        var groups: [(Int, Int)] = []
        var s0 = idx[0]
        var p = idx[0]
        for k in idx.dropFirst() {
            if k - p > 1 {
                groups.append((s0, p))
                s0 = k
            }
            p = k
        }
        groups.append((s0, p))
        return groups
            .filter { ($0.1 - $0.0 + 1) >= minLen }
            .map { (ys[$0.0], ys[$0.1]) }
    }

    /// 在 [lo, hi] 里找最优 d，并迭代排除"被遮挡区段"（视频/进度条/广告）。
    static func exclusionSearch(_ A: GrayImage,
                                _ B: GrayImage,
                                _ top: Int,
                                _ bottom: Int,
                                _ lo: Int,
                                _ hi: Int,
                                _ badMin: Int,
                                _ maxExcludedFrac: Float) -> (d: Int?, frac: Float) {
        let H = A.height
        var exclude = [Bool](repeating: false, count: H)
        var bestD: Int?
        var bestF: Float = -1

        for _ in 0..<StitchParams.badBandIter {
            var candD: Int?
            var candF: Float = -1
            for d in lo...hi {
                let f = matchFraction(A, B, d, top, bottom, exclude, pruneBelow: candF).frac
                if f > candF {
                    candF = f
                    candD = d
                }
            }
            guard let cd = candD else { break }
            if cd == bestD {
                bestD = cd
                bestF = max(bestF, candF)
                break
            }
            bestD = cd
            bestF = candF

            let stats = matchFraction(A, B, cd, top, bottom, exclude)
            if stats.errs.isEmpty { break }
            let bands = badBands(stats.errs, stats.ys, badMin)
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
        return (bestD, max(bestF, 0))
    }

    /// A、B 同尺寸灰度图。返回 (d, frac)；d == nil 表示没找到可靠重叠。
    static func findOffset(_ A: GrayImage, _ B: GrayImage, _ top: Int, _ bottom: Int) -> (d: Int?, frac: Float) {
        let H = A.height
        let minOverlap = max(24, Int(StitchParams.minOverlapFrac * Double(H)))

        func dLimit() -> Int { H - bottom - minOverlap - top }
        if dLimit() <= 2 { return (nil, 0) }

        // ---- 第 1 轮：降采样粗搜
        let s = StitchParams.coarseScale
        let As = ImageTools.boxDownsample(A, s)
        let Bs = ImageTools.boxDownsample(B, s)
        let Hs = As.height
        let tops = top / s
        let bots = bottom / s
        let minOvS = max(6, minOverlap / s)
        let dsHi = Hs - bots - minOvS - tops
        let dsLo = max(1, Int(StitchParams.minScrollFrac * Double(Hs - tops - bots)) / 2)
        if dsHi <= dsLo { return (nil, 0) }
        let coarse = exclusionSearch(As, Bs, tops, bots, dsLo, dsHi,
                                     max(3, StitchParams.badBandMin / s), 0.6)
        guard let bestDs = coarse.d else { return (nil, 0) }

        // ---- 第 2 轮：全分辨率精修
        var lo = max(1, bestDs * s - StitchParams.fineWindow * 2)
        let hi = min(dLimit(), bestDs * s + StitchParams.fineWindow * 2)
        // 排除"滚动太少"的候选：固定位置的悬浮元素会自己和自己匹配
        let minScroll = max(Int(StitchParams.minScrollFrac * Double(H - top - bottom)),
                            StitchParams.fineWindow)
        lo = max(lo, minScroll)
        if lo > hi { return (nil, 0) }

        let fine = exclusionSearch(A, B, top, bottom, lo, hi, StitchParams.badBandMin, 0.6)
        guard let bestD = fine.d else { return (nil, 0) }

        // 双闸门：既要"匹配行占比够高"，也要"真的匹配上足够多行"。
        let stats = matchFraction(A, B, bestD, top, bottom, nil)
        let matchRows = stats.errs.filter { $0 < StitchParams.exactEps }.count
        if fine.frac < StitchParams.matchFracThreshold || matchRows < StitchParams.minMatchRows {
            return (nil, fine.frac)
        }
        return (bestD, fine.frac)
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
    /// cropped[0] 在 keepFirstChrome 时前面多出 chromeH 行（保留的状态栏+导航栏）。
    static func render(_ cropped: [RGBABuffer],
                       segments: [Segment],
                       chromeH: Int) -> RGBABuffer {
        let W = cropped[0].width
        var totalH = 0
        for s in segments {
            totalH += ((s.imageIndex == 0) ? chromeH : 0) + s.rowCount
        }
        var out = RGBABuffer(width: W, height: max(totalH, 1), colorSpace: cropped[0].colorSpace)
        let rowBytes = W * 4
        var cursor = 0

        out.pixels.withUnsafeMutableBufferPointer { dst in
            let dp = dst.baseAddress!

            func copyRows(_ src: RGBABuffer, from: Int, rows: Int) {
                guard rows > 0 else { return }
                let s = min(max(from, 0), src.height)
                let take = min(rows, src.height - s)
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
                let src = cropped[s.imageIndex]
                if s.imageIndex == 0 && chromeH > 0 {
                    copyRows(src, from: 0, rows: chromeH)
                    copyRows(src, from: chromeH + s.startRow, rows: s.rowCount)
                } else {
                    copyRows(src, from: s.startRow, rows: s.rowCount)
                }
            }
        }
        return out.cropped(top: 0, bottom: max(0, out.height - cursor))
    }

    /// 遇到"没找到重叠"的接缝时用的简单拼接：两张直接首尾相接，中间加一条分隔线。
    static func renderWithGaps(_ cropped: [RGBABuffer],
                               offsets: [Int?],
                               contentHeight: Int,
                               chromeH: Int) -> RGBABuffer {
        let W = cropped[0].width
        var totalH = cropped[0].height
        for (i, d) in offsets.enumerated() {
            if let d = d {
                totalH += d
            } else {
                totalH += StitchParams.dividerHeight + cropped[i + 1].height
            }
        }

        var out = RGBABuffer(width: W, height: max(totalH, 1), colorSpace: cropped[0].colorSpace)
        let rowBytes = W * 4
        var cursor = 0

        out.pixels.withUnsafeMutableBufferPointer { dst in
            let dp = dst.baseAddress!

            func append(_ src: RGBABuffer, from: Int, rows: Int) {
                guard rows > 0 else { return }
                let s = min(max(from, 0), src.height)
                let take = min(rows, src.height - s)
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

            append(cropped[0], from: 0, rows: cropped[0].height)
            for (i, d) in offsets.enumerated() {
                let src = cropped[i + 1]
                if let d = d {
                    append(src, from: max(0, contentHeight - d), rows: src.height)
                } else {
                    divider()
                    append(src, from: 0, rows: src.height)
                }
            }
        }
        return out.cropped(top: 0, bottom: max(0, out.height - cursor))
    }

    /// 拼一组（调用方保证这一组属于同一次长截图）。
    /// keepFirstChrome: 第一张的状态栏+导航栏保留在长图最上方，后续截图裁掉。
    static func stitchGroup(_ images: [RGBABuffer],
                            keepFirstChrome: Bool = true) -> StitchResult {
        let grays = images.map { $0.grayscale() }
        let H = grays[0].height
        let (top, bottom) = detectOverlays(grays)

        var offsets = [Int?]()
        var seams = [Seam]()
        for i in 0..<(grays.count - 1) {
            let (d, f) = findOffset(grays[i], grays[i + 1], top, bottom)
            offsets.append(d)
            seams.append(Seam(index: i, offset: d, confidence: f))
        }

        return assemble(images, grays: grays, top: top, bottom: bottom,
                        offsets: offsets, seams: seams,
                        keepFirstChrome: keepFirstChrome)
    }

    /// 已知道 offsets 时直接组装（拖动接缝后重拼走这条路，不用再搜一遍）。
    static func assemble(_ images: [RGBABuffer],
                         grays: [GrayImage]?,
                         top: Int,
                         bottom: Int,
                         offsets: [Int?],
                         seams: [Seam],
                         keepFirstChrome: Bool) -> StitchResult {
        // 每张都裁掉底部覆盖层；顶部只有第一张保留
        var cropped = [RGBABuffer]()
        cropped.reserveCapacity(images.count)
        for (i, img) in images.enumerated() {
            let y0 = (i == 0 && keepFirstChrome) ? 0 : top
            cropped.append(img.cropped(top: y0, bottom: bottom))
        }
        let contentH = (grays?.first.height ?? images[0].height) - top - bottom
        let chromeH = keepFirstChrome ? top : 0

        var cuts: [Int] = []
        var out: RGBABuffer
        if offsets.contains(where: { $0 == nil }) {
            out = renderWithGaps(cropped, offsets: offsets, contentHeight: contentH, chromeH: chromeH)
        } else {
            let ints = offsets.map { $0! }
            cuts = defaultCuts(ints, contentHeight: contentH)
            let segs = plan(ints, contentHeight: contentH, cuts: cuts)
            out = render(cropped, segments: segs, chromeH: chromeH)
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
        var cropped = [RGBABuffer]()
        cropped.reserveCapacity(images.count)
        for (i, img) in images.enumerated() {
            let y0 = (i == 0 && keepFirstChrome) ? 0 : top
            cropped.append(img.cropped(top: y0, bottom: bottom))
        }
        let segs = plan(ints, contentHeight: contentH, cuts: cuts)
        return render(cropped, segments: segs, chromeH: chromeH)
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
        let grays = images.map { $0.grayscale() }
        let n = images.count

        // 逐对求偏移（用这一对自身的覆盖层高度，避免不同来源的截图互相污染）
        var pairOffsets = [Int?](repeating: nil, count: n - 1)
        var pairFrac = [Float](repeating: 0, count: n - 1)
        var breaks = [Int]()
        for i in 0..<(n - 1) {
            let (top, bottom) = detectOverlays([grays[i], grays[i + 1]])
            let (d, f) = findOffset(grays[i], grays[i + 1], top, bottom)
            pairOffsets[i] = d
            pairFrac[i] = f
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

        var results = [StitchResult]()
        results.reserveCapacity(groups.count)
        for g in groups {
            let sub = g.map { images[$0] }
            let subGrays = g.map { grays[$0] }
            // 组内重新量一次覆盖层（组内截图风格一致，比逐对更稳）
            let (top, bottom) = detectOverlays(subGrays)

            var offsets = [Int?]()
            var seams = [Seam]()
            for k in 0..<(g.count - 1) {
                let gi = g[k]
                let d = pairOffsets[gi]
                offsets.append(d)
                seams.append(Seam(index: k, offset: d, confidence: pairFrac[gi]))
            }
            var r = assemble(sub, grays: subGrays, top: top, bottom: bottom,
                             offsets: offsets, seams: seams,
                             keepFirstChrome: keepFirstChrome)
            r.indices = g
            results.append(r)
        }
        return results
    }
}
