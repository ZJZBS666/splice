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

@MainActor
final class SpliceModel: ObservableObject {
    @Published var phase: Phase = .idle
    @Published var results: [ResultVM] = []
    @Published var sourceItems: [ScreenshotItem] = []
    @Published var statusText: String = ""
    @Published var progress: Double = 0

    /// 时间窗口（分钟）。用户要求 30 分钟。
    @Published var windowMinutes: Int = 30
    /// 是否保留第一张的状态栏+导航栏
    @Published var keepFirstChrome: Bool = true
    /// 拼接完成后是否删除原图（移到最近删除）
    @Published var deleteOriginals: Bool = true
    /// 超过这个高度就提示
    let maxHeight = StitchParams.maxOutputHeight

    private var loadedImages: [Int: RGBABuffer] = [:]

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
            let preview = makePreview(g.image)
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
    func adjustCut(resultID: UUID, seamIndex: Int, deltaPixels: Int, displayScale: CGFloat) {
        guard let ri = results.firstIndex(where: { $0.id == resultID }) else { return }
        var r = results[ri]
        guard r.canAdjustSeams, seamIndex >= 0, seamIndex < r.cuts.count else { return }

        let offsets = r.seams.compactMap { $0.offset }
        guard offsets.count == r.cuts.count else { return }

        let range = Stitcher.cutRange(seamIndex, offsets: offsets,
                                      contentHeight: r.contentHeight, cuts: r.cuts)
        var cuts = r.cuts
        let delta = Int(Double(deltaPixels) / Double(max(displayScale, 0.01)))
        cuts[seamIndex] = min(max(cuts[seamIndex] + delta, range.lowerBound), range.upperBound)

        let sub = r.indices.compactMap { loadedImages[$0] }
        guard sub.count == r.indices.count,
              let img = Stitcher.restitch(sub,
                                          top: r.topOverlay,
                                          bottom: r.bottomOverlay,
                                          offsets: r.seams.map { $0.offset },
                                          cuts: cuts,
                                          keepFirstChrome: keepFirstChrome) else { return }

        r.cuts = cuts
        r.fullImage = img
        r.preview = makePreview(img)
        results[ri] = r
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

    /// 生成界面用的缩略图。
    ///
    /// 按"总像素预算"缩放，而不是"最长边"。长图高度动辄 8000~30000 像素，
    /// 若按最长边 2048 缩放，宽度会缩到 270 左右，在 390pt 宽的卡片里
    /// 会被放大三倍，糊成一片，接缝手柄也对不准。
    ///
    /// 预算 8M 像素（约 32MB）：
    ///   1206×9000  → 几乎不缩（1098×8192）
    ///   1206×30000 → 缩到 567×14100，虽然窄，但预览窗口只有 320pt 高，
    ///                本来也看不清细节，接缝手柄按比例定位仍然准确。
    private func makePreview(_ buf: RGBABuffer) -> UIImage? {
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
