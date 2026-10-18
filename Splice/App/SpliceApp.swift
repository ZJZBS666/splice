import SwiftUI

@main
struct SpliceApp: App {
    var body: some Scene {
        WindowGroup {
            AppRootView()
        }
    }
}

/// 依赖装配层。
///
/// 这里刻意**不读任何会变化的状态**：`@StateObject` 和 `@ObservedObject`
/// 都会让"持有它的视图"跟着重算，把这个放在 App body 里的话，
/// 拼图过程中每一次 progress / statusText 更新都会重建整个 WindowGroup 的内容。
/// 现在 App body 只做一次装配，状态观察下放到真正用它的地方。
private struct AppRootView: View {
    @StateObject private var model = SpliceModel()

    var body: some View {
        RootView()
            .environmentObject(model)
            .environmentObject(ThemeController.shared)
            .modifier(PreferredAppearance())
    }
}

/// 只观察外观模式。
///
/// 单独抽成一个 modifier，是为了让"改外观"这件事的失效范围只到这里：
/// 外壳（AppRootView）和页面（RootView）都不观察 ThemeController，
/// 换浅色/深色时它们不会重算 body，也就不会连带把结果页那几张几千像素高的
/// 长图卡片重新布局一遍。
private struct PreferredAppearance: ViewModifier {
    @ObservedObject private var theme = ThemeController.shared

    func body(content: Content) -> some View {
        content.preferredColorScheme(theme.mode.colorScheme)
    }
}
