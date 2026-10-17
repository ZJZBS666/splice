import SwiftUI
import UIKit

/// 外观模式。
///
/// `system` 是默认值：跟着 iOS 的浅色/深色设置走。
/// 用户明确选 light / dark 时就用固定的，不再跟随系统。
enum ThemeMode: String, CaseIterable, Identifiable {
    case system
    case light
    case dark

    var id: String { rawValue }

    var label: String {
        switch self {
        case .system: return "跟随系统"
        case .light:  return "浅色"
        case .dark:   return "深色"
        }
    }

    /// 传给 `.preferredColorScheme`。返回 nil 表示"不强制"，即跟随系统。
    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light:  return .light
        case .dark:   return .dark
        }
    }
}

/// 配色。
///
/// 原来界面里到处写死 `Color.white` / `Color.black`，加深色模式时这些
/// 会全部失效（深色底上仍然是白底黑字）。这里统一换成"随外观自动反转"的
/// 语义色，视觉上保持原来的极简风：
///   - 浅色：白底 + 黑主按钮 + 白字
///   - 深色：近黑底 + 白主按钮 + 黑字
extension Color {
    /// 页面底色
    static let appBG = Color(.systemBackground)
    /// 次级容器底色（占位块等）
    static let appFill = Color(.secondarySystemBackground)
    /// 主按钮背景
    static let appPrimary = Color.primary
    /// 主按钮文字
    static let appOnPrimary = Color(.systemBackground)
    /// 细边框
    static let appHairline = Color.primary.opacity(0.10)
}

/// 主按钮样式。全 App 的黑色大按钮都走这里，改一处就够。
struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 16, weight: .medium))
            .frame(maxWidth: .infinity)
            .frame(height: 52)
            .background(Color.appPrimary)
            .foregroundStyle(Color.appOnPrimary)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .opacity(configuration.isPressed ? 0.82 : 1)
    }
}
