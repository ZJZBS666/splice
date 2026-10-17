import Foundation
import Photos
import SwiftUI

/// App 的全局状态机
enum Phase: Equatable {
    case idle               // 还没开始
    case needPermission     // 需要相册权限
    case scanning           // 正在读相册
    case stitching          // 正在拼接
    case done               // 拼接完成，等待确认
    case saving             // 正在保存
    case saved              // 已保存
    case failed(String)     // 出错

    static func == (a: Phase, b: Phase) -> Bool {
        switch (a, b) {
        case (.idle, .idle), (.needPermission, .needPermission),
             (.scanning, .scanning), (.stitching, .stitching),
             (.done, .done), (.saving, .saving), (.saved, .saved):
            return true
        case let (.failed(x), .failed(y)):
            return x == y
        default:
            return false
        }
    }
}

/// 界面上展示的一组结果
struct ResultVM: Identifiable {
    let id = UUID()
    var indices: [Int]
    var preview: UIImage?          // 用于界面显示的缩略图
    var fullImage: RGBABuffer      // 原始像素，保存时用
    var seams: [Seam]
    var cuts: [Int]
    var topOverlay: Int
    var bottomOverlay: Int
    var contentHeight: Int
    var chromeHeight: Int
    var canAdjustSeams: Bool

    var pixelWidth: Int { fullImage.width }
    var pixelHeight: Int { fullImage.height }
}

/// 跨线程搬运 UIImage 的包装。
///
/// `UIImage` 没有标 `Sendable`，直接从 `Task.detached` 里返回会触发
/// 并发检查警告。但这里只有一处生成、一处读取，不存在真正的并发访问，
/// 所以用 `@unchecked Sendable` 明确声明。
struct PreviewBox: @unchecked Sendable {
    let image: UIImage?
}

@MainActor
final class SpliceModel: ObservableObject {
    @Published var phase: Phase = .idle
    @Published var results: [ResultVM] = []
    @Published var sourceItems: [ScreenshotItem] = []
    @Published var statusText: String = ""
    @Published var progress: Double = 0

    /// 时间窗口（分钟）。用户要求 30 分钟。
    @Published var windowMinutes: Int = 30 {
        didSet { defaults.set(windowMinutes, forKey: Keys.windowMinutes) }
    }
    /// 是否保留第一张的状态栏+导航栏
    @Published var keepFirstChrome: Bool = true {
        didSet { defaults.set(keepFirstChrome, forKey: Keys.keepFirstChrome) }
    }
    /// 拼接完成后是否删除原图（移到最近删除）
    @Published var deleteOriginals: Bool = true {
        didSet { defaults.set(deleteOriginals, forKey: Keys.deleteOriginals) }
    }
    /// 超过这个高度就提示
    let maxHeight = StitchParams.maxOutputHeight

    private var loadedImages: [Int: RGBABuffer] = [:]

    /// 是否正在后台重拼。拖动接缝会连续触发重拼，
    /// 上一次还没结束就丢掉这次，否则两次结果会互相覆盖、画面跳回旧位置。
    private var isRerendering = false

    private let defaults = UserDefaults.standard
    private enum Keys {
        static let windowMinutes = "splice.windowMinutes"
        static let keepFirstChrome = "splice.keepFirstChrome"
        static let deleteOriginals = "splice.deleteOriginals"
    }

    /// 读回上次的设置。
    ///
    /// 不存的话每次冷启动都会退回默认值：用户把识别范围改成 1 小时，
    /// 下次打开又变回 30 分钟，会以为设置没生效。
    init() {
        if defaults.object(forKey: Keys.windowMinutes) != nil {
            let v = defaults.integer(forKey: Keys.windowMinutes)
            if v > 0 { windowMinutes = v }
        }
        if defaults.object(forKey: Keys.keepFirstChrome) != nil {
            keepFirstChrome = defaults.bool(forKey: Keys.keepFirstChrome)
        }
        if defaults.object(forKey: Keys.deleteOriginals) != nil {
            deleteOriginals = defaults.bool(forKey: Keys.deleteOriginals)
        }
    }

    // MARK: - 主流程

    /// 打开 App / 点「重新扫描」时调用
    func scan() async {
        results = []
        loadedImages = [:]
        progress = 0
        phase = .scanning
        statusText = "正在读取最近 \(windowMinutes) 分钟的截图…"

        do {
            try await PhotoLibrary.ensureAccess()
        } catch {
            phase = .needPermission
            statusText = (error as? LocalizedError)?.errorDescription ?? "无法访问相册"
            return
        }

        let items = PhotoLibrary.fetchRecentScreenshots(windowMinutes: windowMinutes)
        sourceItems = items

        if items.isEmpty {
            phase = .idle
            statusText = "最近 \(windowMinutes) 分钟里没有找到截图。\n先去截几张图，再回来。"
            return
        }
        if items.count == 1 {
            phase = .idle
            statusText = "只找到 1 张截图，没法拼接。\n至少需要 2 张连续的截图。"
            return
        }

        await stitch(items: items)
    }

    /// 载入像素 → 分组 → 拼接
    func stitch(items: [ScreenshotItem]) async {
        phase = .stitching
        statusText = "正在拼接 \(items.count) 张截图…"
        progress = 0

        var buffers: [RGBABuffer] = []
        buffers.reserveCapacity(items.count)
        for (i, item) in items.enumerated() {
            do {
                let buf = try await PhotoLibrary.loadFullResolution(item)
                buffers.append(buf)
                loadedImages[i] = buf
            } catch {
                statusText = "第 \(i + 1) 张读取失败：\(error.localizedDescription)"
                phase = .failed(statusText)
                return
            }
            progress = Double(i + 1) / Double(items.count) * 0.6
            statusText = "正在读取第 \(i + 1)/\(items.count) 张…"
        }

        // 所有截图宽度必须一致，否则按最窄的对齐（正常情况下不会发生）
        let minW = buffers.map { $0.width }.min() ?? 0
        if buffers.contains(where: { $0.width != minW }) {
            buffers = buffers.map { $0.croppedToWidth(minW) }
        }

        statusText = "正在识别重叠部分…"
        progress = 0.7

        let ts = items.map { $0.creationDate.timeIntervalSince1970 }
        let keep = keepFirstChrome
        let bufs = buffers
        let groups = await Task.detached(priority: .userInitiated) {
            Stitcher.stitchAll(bufs, timestamps: ts, keepFirstChrome: keep)
        }.value

        progress = 0.95
        var vms: [ResultVM] = []
        for g in groups {
            let preview = SpliceModel.makePreview(g.image)
            vms.append(ResultVM(indices: g.indices,
                                preview: preview,
                                fullImage: g.image,
                                seams: g.seams,
                                cuts: g.cuts,
                                topOverlay: g.topOverlay,
                                bottomOverlay: g.bottomOverlay,
                                contentHeight: g.contentHeight,
                                chromeHeight: g.chromeHeight,
                                canAdjustSeams: g.canAdjustSeams))
        }

        // 太高的组给个提示（但仍允许保存，用户自己决定）
        let tooTall = vms.filter { $0.pixelHeight > maxHeight }
        results = vms
        progress = 1
        phase = .done
        if vms.count == 1 {
            statusText = tooTall.isEmpty
                ? "拼好了，1 张长图。确认后保存到相册。"
                : "拼好了，但高度 \(tooTall[0].pixelHeight) 像素超过 \(maxHeight)，相册可能显示异常。"
        } else {
            statusText = "识别到 \(vms.count) 组截图，拼成 \(vms.count) 张长图。"
                + (tooTall.isEmpty ? "" : "其中 \(tooTall.count) 张超过 \(maxHeight) 像素。")
        }
    }

    // MARK: - 拖动接缝

    /// 用户拖动某条接缝后调用。delta 为屏幕坐标下的位移（正数向下）。
    ///
    /// 重拼要在后台线程做：长图最高 30000 像素（约 145MB），
    /// 在主线程里 memcpy + 缩放预览会卡住界面几百毫秒，看起来像 App 卡死了。
    func adjustCut(resultID: UUID, seamIndex: Int, deltaPixels: Int, displayScale: CGFloat) async {
        // 上一次重拼还没结束就忽略这次，否则两次结果会互相覆盖
        guard !isRerendering else { return }
        guard let ri = results.firstIndex(where: { $0.id == resultID }) else { return }
        let r = results[ri]
        guard r.canAdjustSeams, seamIndex >= 0, seamIndex < r.cuts.count else { return }

        let offsets = r.seams.compactMap { $0.offset }
        guard offsets.count == r.cuts.count else { return }

        let range = Stitcher.cutRange(seamIndex, offsets: offsets,
                                      contentHeight: r.contentHeight, cuts: r.cuts)
        var cuts = r.cuts
        let delta = Int(Double(deltaPixels) / Double(max(displayScale, 0.01)))
        cuts[seamIndex] = min(max(cuts[seamIndex] + delta, range.lowerBound), range.upperBound)
        guard cuts != r.cuts else { return }

        let sub = r.indices.compactMap { loadedImages[$0] }
        guard sub.count == r.indices.count else { return }

        let top = r.topOverlay
        let bottom = r.bottomOverlay
        let offs = r.seams.map { $0.offset }
        let keep = keepFirstChrome

        isRerendering = true
        defer { isRerendering = false }

        // 重拼 + 生成预览都在后台线程完成。预览那一步的缩放
        // （145MB → 32MB）同样要几百毫秒，留在主线程照样会卡。
        let made = await Task.detached(priority: .userInitiated) { () -> (RGBABuffer, PreviewBox)? in
            guard let img = Stitcher.restitch(sub, top: top, bottom: bottom,
                                              offsets: offs, cuts: cuts,
                                              keepFirstChrome: keep) else { return nil }
            return (img, PreviewBox(image: SpliceModel.makePreview(img)))
        }.value
        guard let made = made else { return }

        // 重拼期间用户可能点了「再来一次」把 results 清空了，重新定位一次
        guard let ri2 = results.firstIndex(where: { $0.id == resultID }) else { return }
        var r2 = results[ri2]
        r2.cuts = cuts
        r2.fullImage = made.0
        r2.preview = made.1.image
        results[ri2] = r2
    }

    // MARK: - 保存

    func confirmSave() async {
        guard !results.isEmpty else { return }
        phase = .saving
        progress = 0
        var savedCount = 0
        var failedMsg: String?

        for (i, r) in results.enumerated() {
            statusText = "正在保存第 \(i + 1)/\(results.count) 张长图…"
            do {
                let stamp = ISO8601DateFormatter().string(from: Date())
                    .replacingOccurrences(of: ":", with: "-")
                let name = "Splice-\(stamp)-\(i + 1).png"
                try await PhotoLibrary.savePNG(r.fullImage, filename: name)
                savedCount += 1
            } catch {
                failedMsg = error.localizedDescription
            }
            progress = Double(i + 1) / Double(results.count) * 0.7
        }

        // 只有在全部长图都成功存进相册后才删原图。
        // 少存一张就删原图，等于把用户的内容弄丢了两份 —— 宁可留着。
        if deleteOriginals && savedCount == results.count {
            statusText = "正在把原图移到「最近删除」…"
            // 只删真正参与拼接的那些原图（results 里的 indices 指向 sourceItems）
            var used = Set<Int>()
            for r in results { for i in r.indices { used.insert(i) } }
            let items = used.sorted().compactMap { idx -> ScreenshotItem? in
                guard idx >= 0 && idx < sourceItems.count else { return nil }
                return sourceItems[idx]
            }
            do {
                try await PhotoLibrary.deleteAssets(items)
            } catch {
                failedMsg = (failedMsg.map { $0 + "\n" } ?? "")
                    + "长图已保存，但删除原图失败：\(error.localizedDescription)"
            }
        }

        progress = 1
        if let msg = failedMsg {
            let keep = (deleteOriginals && savedCount != results.count)
                ? "\n有长图没保存成功，所以原图都保留着，没有删除。"
                : ""
            phase = .failed(msg + keep)
            statusText = msg + keep
        } else {
            phase = .saved
            statusText = deleteOriginals
                ? "已保存 \(savedCount) 张长图到相册，原图已移到「最近删除」。"
                : "已保存 \(savedCount) 张长图到相册。"
            // 长图已经写进相册了，内存里这份 100MB+ 的像素没必要再留着。
            // 不释放的话，用户接着再拼一组（App 还没被系统杀掉）就会翻倍。
            results = []
            loadedImages = [:]
            sourceItems = []
        }
    }

    func reset() {
        results = []
        loadedImages = [:]
        sourceItems = []
        phase = .idle
        statusText = ""
        progress = 0
    }

    // MARK: - 预览图

    /// 把整张长图缩成界面用的预览图。
    ///
    /// 为什么不用"最长边缩到 2048"：长图高 8000~30000、宽只有 1206，
    /// 按最长边缩放会让宽度只剩 270，卡片里被放大三倍糊成一片，
    /// 接缝手柄也对不准。改成按"总像素预算"缩放，宽度能保住。
    ///
    /// 预算 8M 像素（约 32MB）：
    ///   1206×9000  → 几乎不缩（1098×8192）
    ///   1206×30000 → 缩到 567×14100，虽然窄，但预览窗口只有 320pt 高，
    ///                本来也看不清细节，接缝手柄按比例定位仍然准确。
    ///
    /// 写成 `nonisolated static` 是为了能在后台线程调用 —— 缩放本身
    /// 也要几百毫秒，留在主线程会卡界面。它不读任何实例状态，安全。
    nonisolated static func makePreview(_ buf: RGBABuffer) -> UIImage? {
        guard let cg = buf.makeCGImage() else { return nil }
        let maxPixels = 8_000_000.0
        let w = Double(cg.width), h = Double(cg.height)
        let pixels = max(w * h, 1)
        let scale = min(1.0, (maxPixels / pixels).squareRoot())
        if scale >= 0.999 { return UIImage(cgImage: cg) }
        let tw = max(1, Int((w * scale).rounded()))
        let th = max(1, Int((h * scale).rounded()))
        guard let ctx = CGContext(data: nil,
                                  width: tw, height: th,
                                  bitsPerComponent: 8, bytesPerRow: 0,
                                  space: cg.colorSpace ?? CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else {
            return UIImage(cgImage: cg)
        }
        ctx.interpolationQuality = .high
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: tw, height: th))
        guard let out = ctx.makeImage() else { return UIImage(cgImage: cg) }
        return UIImage(cgImage: out)
    }
}
