import SwiftUI
import UIKit

struct RootView: View {
    @EnvironmentObject private var model: SpliceModel
    @State private var showSettings = false
    /// 点卡片进入的全屏预览（nil 表示不展示）
    @State private var fullscreenResult: ResultVM?

    var body: some View {
        ZStack {
            Color.appBG.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar
                content
                    // 阶段之间淡入淡出。原来是从「正在拼」直接换成结果页，
                    // 几张几千像素高的卡片瞬间出现，观感很硬。
                    .transition(.opacity)
            }
            .animation(.smooth(duration: 0.30), value: model.phase)
        }
        .sheet(isPresented: $showSettings) {
            SettingsView()
                .environmentObject(model)
                // 让 sheet 的圆角也走连续曲率，和系统设置页一致
                .presentationCornerRadius(AppRadius.sheet)
        }
        .fullScreenCover(item: $fullscreenResult) { r in
            FullscreenPreview(result: r)
                .environmentObject(model)
        }
        .task {
            // 打开 App 就自动扫描，符合"截完图打开 App 就自动拼"的预期
            if model.phase == .idle || model.phase == .saved {
                await model.scan()
            }
        }
    }

    // MARK: - 顶栏

    private var topBar: some View {
        HStack {
            Text("SPLICE")
                .font(.system(size: 13, weight: .semibold))
                .tracking(3.4)
                .foregroundStyle(.secondary)
            Spacer()
            Button {
                showSettings = true
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 19))
                    .foregroundStyle(.secondary)
            }
            .accessibilityLabel("设置")
        }
        .padding(.horizontal, 30)
        .padding(.top, 8)
        .padding(.bottom, 12)
    }

    // MARK: - 主体

    @ViewBuilder
    private var content: some View {
        switch model.phase {
        case .idle:
            idleView
        case .needPermission:
            permissionView
        case .scanning, .stitching, .saving:
            busyView
        case .done:
            doneView
        case .saved:
            savedView
        case .failed(let msg):
            failedView(msg)
        }
    }

    // MARK: - 各种状态

    private var idleView: some View {
        VStack(spacing: 0) {
            Spacer()
            Image(systemName: "rectangle.stack")
                .font(.system(size: 44, weight: .light))
                .foregroundStyle(.tertiary)
                .padding(.bottom, 20)
            Text(model.statusText.isEmpty
                 ? "最近 \(model.windowMinutes) 分钟里没有找到截图。\n先去截几张图，再回来。"
                 : model.statusText)
                .font(.system(size: 15))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .lineSpacing(5)
                .padding(.horizontal, 44)
            Spacer()
            Button {
                Task { await model.scan() }
            } label: {
                Text("重新扫描")
            }
            .buttonStyle(PrimaryButtonStyle())
            .padding(.horizontal, 30)
            .padding(.bottom, 24)
        }
    }

    private var permissionView: some View {
        VStack(spacing: 0) {
            Spacer()
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 44, weight: .light))
                .foregroundStyle(.tertiary)
                .padding(.bottom, 20)
            Text("需要相册权限")
                .font(.system(size: 19, weight: .semibold))
                .padding(.bottom, 10)
            Text(model.statusText)
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .lineSpacing(5)
                .padding(.horizontal, 40)
            Spacer()
            Button {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            } label: {
                Text("去设置里打开")
            }
            .buttonStyle(PrimaryButtonStyle())
            .padding(.horizontal, 30)
            .padding(.bottom, 24)
        }
    }

    private var busyView: some View {
        VStack(spacing: 0) {
            Spacer()
            ProgressView()
                .controlSize(.large)
                .padding(.bottom, 22)
            Text(model.statusText)
                .font(.system(size: 15))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Spacer()
        }
    }

    private var savedView: some View {
        VStack(spacing: 0) {
            Spacer()
            Image(systemName: "checkmark.circle")
                .font(.system(size: 48, weight: .light))
                .foregroundStyle(.green)
                .padding(.bottom, 20)
            Text(model.statusText)
                .font(.system(size: 15))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .lineSpacing(5)
                .padding(.horizontal, 40)
            Spacer()
            Button {
                model.reset()
                Task { await model.scan() }
            } label: {
                Text("再来一次")
            }
            .buttonStyle(PrimaryButtonStyle())
            .padding(.horizontal, 30)
            .padding(.bottom, 24)
        }
    }

    private func failedView(_ msg: String) -> some View {
        VStack(spacing: 0) {
            Spacer()
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 44, weight: .light))
                .foregroundStyle(.orange)
                .padding(.bottom, 20)
            Text(msg)
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .lineSpacing(5)
                .padding(.horizontal, 36)
            Spacer()
            Button {
                model.reset()
                Task { await model.scan() }
            } label: {
                Text("重试")
            }
            .buttonStyle(PrimaryButtonStyle())
            .padding(.horizontal, 30)
            .padding(.bottom, 24)
        }
    }

    // MARK: - 结果页

    private var doneView: some View {
        // 预览区尽量吃满屏幕：底部操作区只留固定高度，剩下全给长图。
        //
        // 之前按「屏高 × 0.60」算，iPhone 16 Pro 上只有 431pt，而一张
        // 1206×5709 的长图按宽度铺满后高度是 1632pt —— 431pt 的窗口只能看到
        // 四分之一，接缝根本没法微调。现在把卡片高度提到"内容区减去底部操作区"，
        // 同时把尺寸文字挪到图片上的浮动标签里，不再单独占一行。
        GeometryReader { proxy in
            // 底部操作区（状态行 + 开关 + 保存按钮 + 内边距）总共约 105pt，
            // 这里按 108 预留，剩下全部给预览。尺寸文字与接缝提示已经改成
            // 图片上的浮动标签，不再额外占一行高度。
            let controlH: CGFloat = 108
            let cardH = max(360, proxy.size.height - controlH)

            VStack(spacing: 0) {
                ScrollView {
                    VStack(spacing: 18) {
                        ForEach(model.results) { r in
                            ResultCard(result: r,
                                       onTap: { fullscreenResult = r },
                                       previewHeight: cardH)
                                .environmentObject(model)
                        }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 4)
                }

                controlBar
            }
        }
    }

    /// 底部操作区：状态说明 + 开关同排，保存按钮独占一行。
    ///
    /// 之所以把开关和状态文字压到同一行：这一块每多占 40pt，
    /// 上面的长图预览就少 40pt，而预览恰恰是最需要空间的地方。
    private var controlBar: some View {
        VStack(spacing: 8) {
            HStack(spacing: 10) {
                Text(model.statusText)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Spacer(minLength: 0)
                Text("删原图")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .fixedSize()
                Toggle("", isOn: $model.deleteOriginals)
                    .labelsHidden()
                    .toggleStyle(.switch)
                    .tint(Color.appPrimary)
                    .fixedSize()
            }
            .padding(.horizontal, 22)

            Button {
                Task { await model.confirmSave() }
            } label: {
                Text(model.results.count > 1
                     ? "确认保存 \(model.results.count) 张长图"
                     : "确认保存")
            }
            .buttonStyle(PrimaryButtonStyle())
            .padding(.horizontal, 24)
        }
        .padding(.top, 6)
        .padding(.bottom, 8)
        .frame(maxWidth: .infinity)
        .background(Color.appBG)
    }
}

// MARK: - 单张结果卡片

private struct ResultCard: View {
    let result: ResultVM
    /// 点一下进全屏
    let onTap: () -> Void
    /// 卡片里预览区的高度（由外层按屏幕高度算好传进来）
    let previewHeight: CGFloat

    var body: some View {
        ZStack {
            if let img = result.preview {
                GeometryReader { geo in
                    let w = geo.size.width
                    let h = CGFloat(img.size.height) / CGFloat(max(img.size.width, 1)) * w
                    ScrollView(.vertical, showsIndicators: false) {
                        Image(uiImage: img)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: w)
                            .overlay(alignment: .topLeading) {
                                SeamOverlay(result: result,
                                            imageHeight: h,
                                            viewWidth: w)
                            }
                    }
                    .frame(height: previewHeight)
                    .appCorner(AppRadius.card)
                    .appCornerBorder(AppRadius.card)
                }
                .frame(height: previewHeight)
            } else {
                RoundedRectangle(cornerRadius: AppRadius.card, style: .continuous)
                    .fill(Color.appFill)
                    .frame(height: previewHeight)
            }

            // 尺寸 + 接缝提示 + "放大"角标：都浮在图片上，不再额外占一行高度。
            if result.preview != nil {
                VStack {
                    Spacer()
                    HStack(alignment: .bottom, spacing: 8) {
                        infoChip
                        Spacer(minLength: 0)
                        Image(systemName: "arrow.up.left.and.arrow.down.right")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(.white)
                            .padding(7)
                            .background(Color.black.opacity(0.45))
                            .clipShape(Circle())
                    }
                    .padding(10)
                }
                .allowsHitTesting(false)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture { onTap() }
    }

    /// 压在图片左下角的信息标签
    private var infoChip: some View {
        HStack(spacing: 6) {
            Text("\(result.pixelWidth) × \(result.pixelHeight)")
                .monospacedDigit()
            Text("·")
            Text(result.canAdjustSeams ? "拖动接缝微调" : "有接缝未识别")
        }
        .font(.system(size: 10, weight: .medium))
        .foregroundStyle(.white)
        .lineLimit(1)
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Color.black.opacity(0.45))
        .appCorner(AppRadius.small)
    }
}

// MARK: - 接缝拖动手柄（卡片与全屏共用）

private struct SeamOverlay: View {
    @EnvironmentObject private var model: SpliceModel
    let result: ResultVM
    /// 图片在屏幕上的实际显示高度
    let imageHeight: CGFloat
    let viewWidth: CGFloat

    /// 拖动时累计的位移，松手才重拼
    @State private var dragOffsets: [Int: CGFloat] = [:]
    @State private var activeSeam: Int?

    var body: some View {
        Group {
            if result.canAdjustSeams && !result.cuts.isEmpty && imageHeight > 1 {
                let k = imageHeight / CGFloat(max(result.pixelHeight, 1))
                // cuts 是"内容区坐标"（内容区第 0 行 = 长图第 chromeHeight 行），
                // 所以换算成显示坐标要先加上保留的状态栏+导航栏高度，
                // 否则手柄会整体偏上 top 像素。
                let chrome = CGFloat(result.chromeHeight)
                ForEach(Array(result.cuts.enumerated()), id: \.offset) { item in
                    let idx = item.offset
                    let baseY = (chrome + CGFloat(item.element)) * k
                    let dy = dragOffsets[idx] ?? 0
                    SeamHandle(active: activeSeam == idx)
                        .position(x: viewWidth / 2, y: max(0, baseY + dy))
                        // 用 highPriorityGesture 抢在 ScrollView 之前拿到竖直拖动，
                        // 否则手指一往下拉，滚的是整张长图而不是这条接缝。
                        .highPriorityGesture(
                            DragGesture(minimumDistance: 0)
                                .onChanged { v in
                                    activeSeam = idx
                                    dragOffsets[idx] = v.translation.height
                                }
                                .onEnded { v in
                                    activeSeam = nil
                                    let pxPerPoint = CGFloat(result.pixelHeight) / max(imageHeight, 1)
                                    let deltaPixels = Int((v.translation.height * pxPerPoint).rounded())
                                    dragOffsets[idx] = nil
                                    if deltaPixels != 0 {
                                        // 重拼在后台线程做（最高 30000px 的长图要几百毫秒），
                                        // 所以这里必须包成 Task，不能直接同步调用。
                                        Task {
                                            await model.adjustCut(resultID: result.id,
                                                                  seamIndex: idx,
                                                                  deltaPixels: deltaPixels,
                                                                  displayScale: 1)
                                        }
                                    }
                                }
                        )
                }
            }
        }
    }
}

// MARK: - 全屏预览

private struct FullscreenPreview: View {
    @EnvironmentObject private var model: SpliceModel
    @Environment(\.dismiss) private var dismiss

    /// 传进来的是快照；拖动接缝后模型里的图会更新，所以这里按 id 重新取一次
    let result: ResultVM

    private var live: ResultVM {
        model.results.first(where: { $0.id == result.id }) ?? result
    }

    var body: some View {
        ZStack(alignment: .top) {
            Color.black.ignoresSafeArea()

            if let img = live.preview {
                GeometryReader { geo in
                    let w = geo.size.width
                    let h = CGFloat(img.size.height) / CGFloat(max(img.size.width, 1)) * w
                    ScrollView(.vertical, showsIndicators: false) {
                        Image(uiImage: img)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: w)
                            .overlay(alignment: .topLeading) {
                                SeamOverlay(result: live, imageHeight: h, viewWidth: w)
                            }
                    }
                }
                .ignoresSafeArea(edges: .bottom)
            }

            HStack {
                Spacer()
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 34, height: 34)
                        .background(Color.black.opacity(0.55))
                        .clipShape(Circle())
                }
                .accessibilityLabel("关闭")
            }
            .padding(.horizontal, 18)
            .padding(.top, 6)
        }
        .statusBarHidden(true)
    }
}

private struct SeamHandle: View {
    let active: Bool

    var body: some View {
        ZStack {
            // 白底上白线看不见，所以画"黑线 + 白描边"的双层线：
            // 无论长图内容是什么颜色都能看清。
            Rectangle()
                .fill(Color.white)
                .frame(height: 4)
            Rectangle()
                .fill(active ? Color.blue : Color.black.opacity(0.55))
                .frame(height: 1.5)
            Capsule()
                .fill(active ? Color.blue : Color.black.opacity(0.72))
                .frame(width: 46, height: 20)
                .overlay(
                    Image(systemName: "arrow.up.and.down")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Color.white)
                )
                .shadow(color: Color.black.opacity(0.25), radius: 2, y: 1)
        }
        .frame(width: 200, height: 34)
        .contentShape(Rectangle())
    }
}

// MARK: - 设置

struct SettingsView: View {
    @EnvironmentObject private var model: SpliceModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    /// 外观单独观察 `ThemeController`，不走 `SpliceModel`。
    @ObservedObject private var theme = ThemeController.shared

    private let repoURL = URL(string: "https://github.com/ZJZBS666/splice")!
    private let authorURL = URL(string: "https://github.com/ZJZBS666")!

    var body: some View {
        NavigationStack {
            ZStack {
                // iOS 设置页的底色是 grouped 底（浅色下浅灰、深色下更黑），
                // 内容放在白色的分组卡片里，靠明度差分组。
                Color.appGroupedBG.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        section("外观") {
                            // 用自定义 Binding 而不是 $theme.mode：切换要走
                            // ThemeController.set()，那里才会先截屏再改模式，
                            // 做出「旧画面淡出、新画面淡入」的过渡。
                            Picker("外观", selection: Binding(
                                get: { theme.mode },
                                set: { theme.set($0) }
                            )) {
                                ForEach(ThemeMode.allCases) { m in
                                    Text(m.label).tag(m)
                                }
                            }
                            .pickerStyle(.segmented)
                            hint("选「跟随系统」时，Splice 会跟着 iPhone 的浅色/深色设置自动切换。")
                        }

                        section("识别范围") {
                            Picker("识别范围", selection: $model.windowMinutes) {
                                Text("最近 10 分钟").tag(10)
                                Text("最近 30 分钟").tag(30)
                                Text("最近 1 小时").tag(60)
                                Text("最近 3 小时").tag(180)
                            }
                            .pickerStyle(.segmented)
                            hint("Splice 只在这个时间范围里找截图。")
                        }

                        section("顶部保留") {
                            Toggle(isOn: $model.keepFirstChrome) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("保留第一张的状态栏和导航栏")
                                        .font(.system(size: 15))
                                    Text("关掉后长图顶部直接是内容")
                                        .font(.system(size: 12))
                                        .foregroundStyle(.tertiary)
                                }
                            }
                            .toggleStyle(.switch)
                            .tint(Color.appPrimary)
                            hint("顶部这一条只会保留一次。")
                        }

                        section("关于") {
                            Text("Splice 会把最近的截图按时间顺序自动识别重叠部分，去掉重复后拼成一张长图。识别不出来时会在接缝处加一条细分隔线，你可以拖动接缝微调。")
                                .font(.system(size: 13))
                                .foregroundStyle(.secondary)
                                .lineSpacing(5)
                        }

                        groupCard {
                            linkRow(icon: "person.crop.circle",
                                    title: "作者",
                                    detail: "ZJZBS666") {
                                openURL(authorURL)
                            }
                            Divider().padding(.leading, 44)
                            linkRow(icon: "chevron.left.forwardslash.chevron.right",
                                    title: "项目源码",
                                    detail: "ZJZBS666/splice") {
                                openURL(repoURL)
                            }
                        }
                        .padding(.top, 2)
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 6)
                    .padding(.bottom, 28)
                }
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完成") { dismiss() }
                        .foregroundStyle(.primary)
                }
            }
        }
    }

    /// 一行"可点开的链接"，右侧带一个小箭头
    private func linkRow(icon: String, title: String, detail: String,
                         action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .font(.system(size: 16))
                    .foregroundStyle(.secondary)
                    .frame(width: 24)
                Text(title)
                    .font(.system(size: 15))
                    .foregroundStyle(.primary)
                Spacer()
                Text(detail)
                    .font(.system(size: 14))
                    .foregroundStyle(.secondary)
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 8)
            .frame(height: 50)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// iOS 设置页那种"inset grouped"分组卡片：
    /// 卡片本身是页面底色的对比色（浅色下白、深色下深灰），圆角走连续曲率。
    @ViewBuilder
    private func groupCard<C: View>(@ViewBuilder _ content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color.appBG)
        .appCorner(AppRadius.row)
    }

    /// 分组卡片里、控件下面那行小字说明。
    private func hint(_ s: String) -> some View {
        Text(s)
            .font(.system(size: 12))
            .foregroundStyle(.tertiary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// 一个小标题 + 一张分组卡片。
    @ViewBuilder
    private func section<C: View>(_ title: String,
                                  @ViewBuilder _ content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            sectionTitle(title)
            groupCard {
                VStack(alignment: .leading, spacing: 10) {
                    content()
                }
            }
        }
    }

    private func sectionTitle(_ t: String) -> some View {
        Text(t)
            .font(.system(size: 11, weight: .semibold))
            .tracking(1.4)
            .foregroundStyle(.tertiary)
            .padding(.leading, 4)
            .padding(.bottom, 8)
    }
}

#Preview {
    RootView().environmentObject(SpliceModel())
}
