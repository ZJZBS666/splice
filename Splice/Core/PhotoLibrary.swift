import Foundation
import Photos
import UIKit
import ImageIO
import UniformTypeIdentifiers

/// 相册里的一张截图
struct ScreenshotItem: Identifiable {
    let id: String
    let asset: PHAsset
    let creationDate: Date
    let pixelWidth: Int
    let pixelHeight: Int

    var aspectRatio: CGFloat {
        pixelHeight > 0 ? CGFloat(pixelWidth) / CGFloat(pixelHeight) : 0
    }
}

enum PhotoLibraryError: LocalizedError {
    case denied
    case limited
    case loadFailed(String)

    var errorDescription: String? {
        switch self {
        case .denied:
            return "没有相册访问权限。请到「设置 → Splice → 照片」里选择「完全访问」。"
        case .limited:
            return "当前是「受限访问」，Splice 只能看到你手动挑选的截图。请改成「完全访问」。"
        case .loadFailed(let msg):
            return "读取截图失败：\(msg)"
        }
    }
}

/// 相册读写。所有操作都是异步的，用 async/await 包一层。
enum PhotoLibrary {

    // MARK: - 权限

    static func requestAccess() async -> PHAuthorizationStatus {
        let current = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        if current != .notDetermined { return current }
        return await withCheckedContinuation { cont in
            PHPhotoLibrary.requestAuthorization(for: .readWrite) { status in
                cont.resume(returning: status)
            }
        }
    }

    static func ensureAccess() async throws {
        let status = await requestAccess()
        switch status {
        case .authorized:
            return
        case .limited:
            throw PhotoLibraryError.limited
        case .denied, .restricted:
            throw PhotoLibraryError.denied
        case .notDetermined:
            throw PhotoLibraryError.denied
        @unknown default:
            throw PhotoLibraryError.denied
        }
    }

    // MARK: - 读取截图

    /// 取最近 windowMinutes 分钟内、指定时间点之前的截图，按拍摄时间升序返回。
    /// - Parameters:
    ///   - windowMinutes: 时间窗口（分钟）。用户设定为 30。
    ///   - before: 只取这个时间点之前的（用于「重新扫描」时排除已处理过的）
    static func fetchRecentScreenshots(windowMinutes: Int = 30,
                                       before: Date = Date()) -> [ScreenshotItem] {
        let since = before.addingTimeInterval(-Double(windowMinutes) * 60)
        // 注意：OptionSet 的 rawValue 是 UInt，直接塞进 %d 在 64 位上不可靠，
        // 必须显式转成 Int 并用 %ld。
        let imageType = Int(PHAssetMediaType.image.rawValue)
        let screenshotBit = Int(PHAssetMediaSubtype.photoScreenshot.rawValue)

        let options = PHFetchOptions()
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: true)]
        options.predicate = NSPredicate(
            format: "mediaType == %ld AND (mediaSubtype & %ld) != 0 AND creationDate >= %@ AND creationDate <= %@",
            imageType,
            screenshotBit,
            since as NSDate,
            before as NSDate
        )
        // 一次最多处理 20 张，超过就没意义了（30000px 上限也拼不下）。
        // 注意：不能直接用 fetchLimit + 升序，那样取到的是窗口里最旧的 20 张。
        // 先全部取出来（升序），再截取最后 20 张，保证拿到的是最新的。
        let result = PHAsset.fetchAssets(with: options)
        var items: [ScreenshotItem] = []
        items.reserveCapacity(result.count)
        result.enumerateObjects { asset, _, _ in
            guard let date = asset.creationDate else { return }
            items.append(ScreenshotItem(id: asset.localIdentifier,
                                        asset: asset,
                                        creationDate: date,
                                        pixelWidth: asset.pixelWidth,
                                        pixelHeight: asset.pixelHeight))
        }
        // 张数上限。每张截图贡献约 (2622 - 321 - 200) ≈ 2100 像素内容高，
        // 30000 的输出上限最多也就 12~14 张；再多的部分拼出来必然被截断，
        // 而且每张要占 ~12MB 原始像素 + ~12MB 灰度图，20 张会吃掉 500MB。
        let limit = 12
        if items.count > limit {
            items = Array(items.suffix(limit))
        }
        return items
    }

    /// 载入原始分辨率的像素。用 requestImageDataAndOrientation 拿原始文件，
    /// 比 requestImage 更省内存、也不会被自动缩放。
    static func loadFullResolution(_ item: ScreenshotItem) async throws -> RGBABuffer {
        let data = try await requestImageData(item.asset)
        guard let cg = decodeCGImage(from: data) else {
            throw PhotoLibraryError.loadFailed("无法解码图片数据")
        }
        guard let buf = ImageTools.rgba(from: cg) else {
            throw PhotoLibraryError.loadFailed("无法转换为像素缓冲")
        }
        return buf
    }

    private static func requestImageData(_ asset: PHAsset) async throws -> Data {
        try await withCheckedThrowingContinuation { cont in
            let options = PHImageRequestOptions()
            options.isNetworkAccessAllowed = true
            options.version = .current
            options.deliveryMode = .highQualityFormat
            options.isSynchronous = false
            PHImageManager.default().requestImageDataAndOrientation(for: asset,
                                                                   options: options) { data, _, _, info in
                if let error = info?[PHImageErrorKey] as? Error {
                    cont.resume(throwing: PhotoLibraryError.loadFailed(error.localizedDescription))
                    return
                }
                if let cancelled = info?[PHImageCancelledKey] as? Bool, cancelled {
                    cont.resume(throwing: PhotoLibraryError.loadFailed("请求被取消"))
                    return
                }
                guard let data = data else {
                    cont.resume(throwing: PhotoLibraryError.loadFailed("相册没有返回数据"))
                    return
                }
                cont.resume(returning: data)
            }
        }
    }

    private static func decodeCGImage(from data: Data) -> CGImage? {
        guard let src = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        // 不要缩略图，要原图
        let opts: [CFString: Any] = [
            kCGImageSourceShouldCache: false,
            kCGImageSourceShouldAllowFloat: false
        ]
        return CGImageSourceCreateImageAtIndex(src, 0, opts as CFDictionary)
    }

    // MARK: - 写回相册

    /// 把长图存进相册，返回新建的 asset 的 localIdentifier。
    ///
    /// 关键：长图可能高到 30000 像素（1206×30000×4 ≈ 145MB 原始像素）。
    /// 如果用 `UIImage.pngData()` 会把整张 PNG 也压进内存，很容易被系统杀掉。
    /// 所以这里先用 ImageIO 把 PNG 直接写到临时文件，再让相册从文件读，
    /// 全程只有一份原始像素在内存里。
    @discardableResult
    static func savePNG(_ buffer: RGBABuffer, filename: String) async throws -> String {
        guard let cg = buffer.makeCGImage() else {
            throw PhotoLibraryError.loadFailed("无法生成长图数据")
        }

        let tmpDir = FileManager.default.temporaryDirectory
        let tmpURL = tmpDir.appendingPathComponent(filename)
        try? FileManager.default.removeItem(at: tmpURL)

        guard let dest = CGImageDestinationCreateWithURL(tmpURL as CFURL,
                                                         "public.png" as CFString,
                                                         1, nil) else {
            throw PhotoLibraryError.loadFailed("无法创建 PNG 写入器")
        }
        CGImageDestinationAddImage(dest, cg, nil)
        guard CGImageDestinationFinalize(dest) else {
            throw PhotoLibraryError.loadFailed("写入 PNG 失败")
        }

        var placeholderID: String?
        do {
            try await PHPhotoLibrary.shared().performChanges {
                let req = PHAssetCreationRequest.forAsset()
                req.creationDate = Date()
                let opts = PHAssetResourceCreationOptions()
                opts.originalFilename = filename
                req.addResource(with: .photo, fileURL: tmpURL, options: opts)
                placeholderID = req.placeholderForCreatedAsset?.localIdentifier
            }
        } catch {
            try? FileManager.default.removeItem(at: tmpURL)
            throw error
        }
        try? FileManager.default.removeItem(at: tmpURL)
        return placeholderID ?? ""
    }

    /// 删除原图。iOS 会把它们移到「最近删除」，30 天内可恢复。
    static func deleteAssets(_ items: [ScreenshotItem]) async throws {
        let ids = items.map { $0.id }
        guard !ids.isEmpty else { return }
        let assets = PHAsset.fetchAssets(withLocalIdentifiers: ids, options: nil)
        try await PHPhotoLibrary.shared().performChanges {
            PHAssetChangeRequest.deleteAssets(assets)
        }
    }
}
