import SwiftUI

@main
struct SpliceApp: App {
    @StateObject private var model = SpliceModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .preferredColorScheme(.light)
        }
    }
}
