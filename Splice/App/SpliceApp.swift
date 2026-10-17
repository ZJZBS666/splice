import SwiftUI

@main
struct SpliceApp: App {
    @StateObject private var model = SpliceModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                // 外观由 model.themeMode 决定：
                //   .system -> nil，跟着 iOS 设置走
                //   .light / .dark -> 强制
                .preferredColorScheme(model.themeMode.colorScheme)
        }
    }
}
