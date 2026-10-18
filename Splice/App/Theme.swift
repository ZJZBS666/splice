import SwiftUI
import UIKit

// MARK: - 外观模式

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

    var symbol: String {
        switch self {
        case .system: return "circle.lefthalf.filled"
        case .light:  return "sun.max"
        case .dark:   return "moon"
        }
    }
}

// MARK: - 圆角

/// 统一圆角尺度。
///
/// iOS 的圆角不是纯圆弧，而是"连续曲率"（squircle，苹果官方叫
/// continuous corner）。SwiftUI 里对应
/// `RoundedRectangle(..., style: .continuous)`；纯 `cornerRadius:`
/// 默认是 `.circular`，也就是一段 1/4 圆弧直接接到直边上，
/// **曲率在接点处是突变的**，所以看起来比系统"方"、也更机械。
///
/// 这里所有圆角都走 `appCorner(_:)`，样式固定 `.continuous`，只调半径。
/// 半径要给足 —— 连续圆角和普通圆角在 r 很小时（比如 12 以下）几乎看不出
/// 区别，只有半径占到元素短边的 1/3 以上，才能看出苹果那种"饱满又收紧"
/// 的手感。
enum AppRadius {
    /// 小标签、角标
    static let small: CGFloat = 10
    /// 设置页的分组卡片
    static let row: CGFloat = 14
    /// 大按钮（52pt 高，半径 20 ≈ 短边的 0.38）
    static let button: CGFloat = 20
    /// 图片卡片
    static let card: CGFloat = 26
    /// 弹出的页面（sheet）
    static let sheet: CGFloat = 38
}

extension View {
    /// iOS 系统那种连续曲率圆角（squircle）。
    func appCorner(_ radius: CGFloat) -> some View {
        clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
    }

    /// 同上的描边版本，画在形状内侧，不会因为 1pt 线宽把边糊掉。
    func appCornerBorder(_ radius: CGFloat,
                         color: Color = Color.appHairline,
                         lineWidth: CGFloat = 1) -> some View {
        overlay(
            RoundedRectangle(cornerRadius: radius, style: .continuous)
                .strokeBorder(color, lineWidth: lineWidth)
        )
    }
}

// MARK: - 配色

/// 配色。
///
/// 用的是系统语义色（`systemBackground` / `primary` 这些），而不是写死的
/// RGB 值。原因有两个：
///   1. 深色模式下系统会自动给出正确对比度，不用自己维护两套色板；
///   2. 语义色在 trait 变化时由 UIKit 在绘制阶段解析，
///      **不需要 SwiftUI 重新计算任何 body** —— 换外观时不会引起整棵树重建。
extension Color {
    /// 页面底色
    static let appBG = Color(.systemBackground)
    /// 分组页的底色（设置页用，浅色下是浅灰，深色下比卡片更暗）
    static let appGroupedBG = Color(.systemGroupedBackground)
    /// 次级容器底色（占位块等）
    static let appFill = Color(.secondarySystemBackground)
    /// 主按钮背景
    static let appPrimary = Color.primary
    /// 主按钮文字
    static let appOnPrimary = Color(.systemBackground)
    /// 细边框
    static let appHairline = Color.primary.opacity(0.10)
}

// MARK: - 主按钮样式

/// 主按钮样式。全 App 的黑色大按钮都走这里，改一处就够。
struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 16, weight: .medium))
            .frame(maxWidth: .infinity)
            .frame(height: 52)
            .background(Color.appPrimary)
            .foregroundStyle(Color.appOnPrimary)
            .appCorner(AppRadius.button)
            // 按下时轻微缩一下，比单纯改透明度更像系统按钮的手感
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .opacity(configuration.isPressed ? 0.9 : 1)
            .animation(.spring(response: 0.30, dampingFraction: 0.72),
                       value: configuration.isPressed)
    }
}

// MARK: - 主题控制器

/// 只负责"外观模式"这一件事。
///
/// 之所以从 `SpliceModel` 里搬出来单独一个对象：`@Published` 是整对象广播的，
/// 放在 `SpliceModel` 上意味着改一次外观会让所有 `@EnvironmentObject var model`
/// 的视图全部重算 body —— 包括结果页那几张上千像素高的长图卡片，点一下会明显卡一下。
/// 拆出来以后，外观变化只有 `PreferredAppearance` 和设置页两个地方会重算。
///
/// 这里刻意**不把整个类标成 `@MainActor`**：`set(_:)` 会被 SwiftUI
/// `Binding` 的 `set` 闭包直接调用，而那个闭包不是主 actor 隔离的，
/// 标了反而要多绕一层。真正的界面操作放在 `MainActor.assumeIsolated` 里，
/// 保证 UIKit 那段一定在主线程上跑。
final class ThemeController: ObservableObject {
    static let shared = ThemeController()

    @Published private(set) var mode: ThemeMode

    private let key = "splice.themeMode"
    private let defaults = UserDefaults.standard

    private init() {
        if let raw = defaults.string(forKey: key),
           let saved = ThemeMode(rawValue: raw) {
            mode = saved
        } else {
            mode = .system
        }
    }

    /// 切换外观。
    ///
    /// 顺序很重要：先抓一张当前画面盖在最上层，再改模式，最后让那张图淡出。
    /// 直接改模式的话是"啪"一下硬跳（系统的 trait 变化不做过渡动画），
    /// 现在是旧画面淡出、新画面淡入，看起来才顺。
    func set(_ newMode: ThemeMode) {
        guard newMode != mode else { return }

        MainActor.assumeIsolated {
            AppearanceCrossfade.fadeOutCurrentScreen()

            withAnimation(.easeInOut(duration: 0.30)) {
                mode = newMode
            }
            defaults.set(newMode.rawValue, forKey: key)
        }
    }
}

// MARK: - 换外观时的淡入淡出

/// 换外观时把"当前画面"盖在最上层再淡出。
///
/// 为什么不能只靠 `withAnimation`：`preferredColorScheme` 改的是窗口级
/// `overrideUserInterfaceStyle`，UIKit 改这个只做一次静默重绘，不产生可动画的属性，
/// 所以不管外面包不包 `withAnimation`，界面都是硬切。
/// 唯一能真正做出过渡的办法就是拿一张旧画面的位图叠在上面淡掉。
///
/// 放在独立 `UIWindow` 里（而不是某个 SwiftUI 视图里）是因为它必须盖住
/// sheet、全屏 cover 这些被 UIKit 提到窗口更高层的内容。
@MainActor
private enum AppearanceCrossfade {
    /// 用 static 变量持有，避免窗口还没淡完就被回收
    private static var overlay: UIWindow?

    static func fadeOutCurrentScreen(duration: TimeInterval = 0.32) {
        // 系统开了"减弱动态效果"就别硬上淡入淡出，直接切
        guard !UIAccessibility.isReduceMotionEnabled else { return }

        guard let scene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.activationState == .foregroundActive }),
              let source = scene.windows.first(where: { $0.isKeyWindow }) ?? scene.windows.first
        else { return }

        // 上一次还没淡完就先收掉，否则连点会叠好几层
        if let old = overlay {
            old.isHidden = true
            overlay = nil
        }

        // false 表示取"当前已经渲染好的"画面，也就是换外观之前的那一帧
        guard let snapshot = source.snapshotView(afterScreenUpdates: false) else { return }

        let window = UIWindow(windowScene: scene)
        window.windowLevel = UIWindow.Level(rawValue: UIWindow.Level.alert.rawValue + 1)
        window.backgroundColor = .clear
        window.isUserInteractionEnabled = false

        let host = UIViewController()
        host.view.backgroundColor = .clear
        window.rootViewController = host
        window.frame = source.frame

        snapshot.frame = host.view.bounds
        snapshot.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        host.view.addSubview(snapshot)

        window.isHidden = false
        overlay = window

        UIView.animate(withDuration: duration,
                       delay: 0,
                       options: [.curveEaseInOut, .beginFromCurrentState]) {
            snapshot.alpha = 0
        } completion: { _ in
            if overlay === window { overlay = nil }
            window.isHidden = true
        }
    }
}
