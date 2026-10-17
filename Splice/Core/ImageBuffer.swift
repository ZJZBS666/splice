import UIKit
import CoreGraphics

/// 一张图的原始像素（RGBA，每像素 4 字节，第 0 行是图像顶部）。
///
/// 标记为 @unchecked Sendable：内容是不可变的字节数组 + 线程安全的 CGColorSpace，
/// 可以安全地传进 Task.detached 里做拼接（否则 Task 的 Success: Sendable 约束会报错）。
struct RGBABuffer: @unchecked Sendable {
    let width: Int
    let height: Int
    var pixels: [UInt8]
    let colorSpace: CGColorSpace

    init(width: Int, height: Int, pixels: [UInt8], colorSpace: CGColorSpace) {
        self.width = width
        self.height = height
        self.pixels = pixels
        self.colorSpace = colorSpace
    }

    init(width: Int, height: Int, colorSpace: CGColorSpace) {
        self.width = width
        self.height = height
        self.pixels = [UInt8](repeating: 0, count: width * height * 4)
        self.colorSpace = colorSpace
    }

    var bytesPerRow: Int { width * 4 }

    /// 裁掉顶部 top 行、底部 bottom 行。
    /// 不需要裁时直接返回自己，避免白拷一份（长图动辄 100MB 以上）。
    func cropped(top: Int, bottom: Int) -> RGBABuffer {
        let y0 = max(0, min(top, height))
        let y1 = max(y0, min(height - bottom, height))
        if y0 == 0 && y1 == height { return self }
        let rows = y1 - y0
        var out = RGBABuffer(width: width, height: rows, colorSpace: colorSpace)
        if rows > 0 {
            let n = rows * bytesPerRow
            pixels.withUnsafeBufferPointer { s in
                out.pixels.withUnsafeMutableBufferPointer { d in
                    memcpy(d.baseAddress!, s.baseAddress! + y0 * bytesPerRow, n)
                }
            }
        }
        return out
    }

    /// 只保留前 maxWidth 列（多张截图宽度不一致时对齐用）
    func croppedToWidth(_ maxWidth: Int) -> RGBABuffer {
        if width <= maxWidth { return self }
        var out = RGBABuffer(width: maxWidth, height: height, colorSpace: colorSpace)
        pixels.withUnsafeBufferPointer { s in
            out.pixels.withUnsafeMutableBufferPointer { d in
                for y in 0..<height {
                    memcpy(d.baseAddress! + y * maxWidth * 4,
                           s.baseAddress! + y * bytesPerRow,
                           maxWidth * 4)
                }
            }
        }
        return out
    }

    func makeCGImage() -> CGImage? {
        let data = Data(pixels)
        guard let provider = CGDataProvider(data: data as CFData) else { return nil }
        let info = CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue)
        return CGImage(width: width,
                       height: height,
                       bitsPerComponent: 8,
                       bitsPerPixel: 32,
                       bytesPerRow: bytesPerRow,
                       space: colorSpace,
                       bitmapInfo: info,
                       provider: provider,
                       decode: nil,
                       shouldInterpolate: false,
                       intent: .defaultIntent)
    }

    func makeUIImage() -> UIImage? {
        guard let cg = makeCGImage() else { return nil }
        return UIImage(cgImage: cg)
    }

    /// 转灰度（和 Python 原型完全一致：0.299R + 0.587G + 0.114B）
    func grayscale() -> GrayImage {
        let count = width * height
        var g = [Float](repeating: 0, count: count)
        pixels.withUnsafeBufferPointer { p in
            g.withUnsafeMutableBufferPointer { dst in
                for i in 0..<count {
                    let o = i * 4
                    dst[i] = Float(p[o]) * 0.299
                        + Float(p[o + 1]) * 0.587
                        + Float(p[o + 2]) * 0.114
                }
            }
        }
        return GrayImage(width: width, height: height, data: g)
    }
}

/// 灰度图（Float，值域 0...255）
struct GrayImage: @unchecked Sendable {
    let width: Int
    let height: Int
    var data: [Float]
}

enum ImageTools {

    /// 把 CGImage 解成 RGBA 缓冲。用图像自己的色彩空间，避免 P3 截图掉色。
    /// 但如果原图不是 RGB 模型（灰度、CMYK 等），必须换成 sRGB，
    /// 否则 CGContext 创建会失败。
    static func rgba(from cgImage: CGImage) -> RGBABuffer? {
        let w = cgImage.width
        let h = cgImage.height
        if w <= 0 || h <= 0 { return nil }

        var cs = cgImage.colorSpace ?? CGColorSpaceCreateDeviceRGB()
        if cs.model != .rgb {
            cs = CGColorSpaceCreateDeviceRGB()
        }

        var buf = [UInt8](repeating: 0, count: w * h * 4)
        let ok: Bool = buf.withUnsafeMutableBytes { raw -> Bool in
            guard let base = raw.baseAddress else { return false }
            guard let ctx = CGContext(data: base,
                                      width: w,
                                      height: h,
                                      bitsPerComponent: 8,
                                      bytesPerRow: w * 4,
                                      space: cs,
                                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else {
                return false
            }
            ctx.interpolationQuality = .none
            ctx.draw(cgImage, in: CGRect(x: 0, y: 0, width: w, height: h))
            return true
        }
        return ok ? RGBABuffer(width: w, height: h, pixels: buf, colorSpace: cs) : nil
    }

    /// 盒式降采样（先裁到整数倍再取平均），和 Python 的 box_downsample 一致
    static func boxDownsample(_ img: GrayImage, _ scale: Int) -> GrayImage {
        let nh = img.height / scale
        let nw = img.width / scale
        if nh < 8 || nw < 8 { return img }
        var out = [Float](repeating: 0, count: nh * nw)
        let inv = 1.0 / Float(scale * scale)
        let srcW = img.width
        img.data.withUnsafeBufferPointer { s in
            out.withUnsafeMutableBufferPointer { d in
                for y in 0..<nh {
                    for x in 0..<nw {
                        var sum: Float = 0
                        for dy in 0..<scale {
                            let rowBase = (y * scale + dy) * srcW
                            for dx in 0..<scale {
                                sum += s[rowBase + x * scale + dx]
                            }
                        }
                        d[y * nw + x] = sum * inv
                    }
                }
            }
        }
        return GrayImage(width: nw, height: nh, data: out)
    }
}
