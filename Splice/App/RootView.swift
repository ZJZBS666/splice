import SwiftUI
import UIKit

struct RootView: View {
    @EnvironmentObject private var model: SpliceModel
    @State private var showSettings = false

    var body: some View {
        ZStack {
            Color.white.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar
                content
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView()
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
                    .font(.system(size: 16, weight: .medium))
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(Color.black)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
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
                    .font(.system(size: 16, weight: .medium))
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(Color.black)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
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
                    .font(.system(size: 16, weight: .medium))
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(Color.black)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
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
                    .font(.system(size: 16, weight: .medium))
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(Color.black)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .padding(.horizontal, 30)
            .padding(.bottom, 24)
        }
    }

    // MARK: - 结果页

    private var doneView: some View {
        VStack(spacing: 0) {
            Text(model.statusText)
                .font(.system(size: 13))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .lineSpacing(4)
                .padding(.horizontal, 30)
                .padding(.bottom, 14)

            ScrollView {
                VStack(spacing: 26) {
                    ForEach(model.results) { r in
                        ResultCard(result: r)
                            .environmentObject(model)
                    }
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 20)
            }

            VStack(spacing: 12) {
                Toggle(isOn: $model.deleteOriginals) {
                    Text("保存后删除原图（移到「最近删除」）")
                        .font(.system(size: 13))
                        .foregroundStyle(.secondary)
                }
                .toggleStyle(.switch)
                .tint(.black)
                .padding(.horizontal, 30)

                Button {
                    Task { await model.confirmSave() }
                } label: {
                    Text(model.results.count > 1
                         ? "确认保存 \(model.results.count) 张长图"
                         : "确认保存")
                        .font(.system(size: 16, weight: .medium))
                        .frame(maxWidth: .infinity)
                        .frame(height: 52)
                        .background(Color.black)
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                }
                .padding(.horizontal, 30)
            }
            .padding(.top, 12)
            .padding(.bottom, 20)
            .background(Color.white)
        }
    }
}

// MARK: - 单张结果卡片

private struct ResultCard: View {
    @EnvironmentObject private var model: SpliceModel
    let result: ResultVM

    /// 拖动时累计的位移，松手才重拼
    @State private var dragOffsets: [Int: CGFloat] = [:]
    @State private var activeSeam: Int?

    private var displayHeight: CGFloat { 320 }

    var body: some View {
        VStack(spacing: 10) {
            ZStack(alignment: .top) {
                if let img = result.preview {
                    GeometryReader { geo in
                        let scale = geo.size.width / CGFloat(img.size.width)
                        let h = CGFloat(img.size.height) * scale
                        ScrollView(.vertical, showsIndicators: false) {
                            Image(uiImage: img)
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(width: geo.size.width)
                                .overlay(alignment: .topLeading) {
                                    seamHandles(viewWidth: geo.size.width,
                                                imageHeight: h,
                                                previewHeight: img.size.height)
                                }
                        }
                        .frame(height: displayHeight)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(Color.black.opacity(0.08), lineWidth: 1)
                        )
                    }
                    .frame(height: displayHeight)
                } else {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(Color(.systemGray6))
                        .frame(height: displayHeight)
                }
            }

            HStack {
                Text("\(result.pixelWidth) × \(result.pixelHeight)")
                    .font(.system(size: 12).monospacedDigit())
                    .foregroundStyle(.secondary)
                Spacer()
                if result.canAdjustSeams {
                    Text("拖动接缝可微调")
                        .font(.system(size: 12))
                        .foregroundStyle(.tertiary)
                } else {
                    Text("有接缝未识别，已直接拼接")
                        .font(.system(size: 12))
                        .foregroundStyle(.tertiary)
                }
            }
        }
    }

    /// 接缝手柄：把每条 cuts 换算成缩略图里的 y 坐标
    @ViewBuilder
    private func seamHandles(viewWidth: CGFloat, imageHeight: CGFloat, previewHeight: CGFloat) -> some View {
        if result.canAdjustSeams && !result.cuts.isEmpty {
            let k = imageHeight / CGFloat(max(result.pixelHeight, 1))
            ForEach(Array(result.cuts.enumerated()), id: \.offset) { item in
                let idx = item.offset
                let cut = item.element
                let baseY = CGFloat(cut) * k
                let dy = dragOffsets[idx] ?? 0
                SeamHandle(color: activeSeam == idx ? Color.blue : Color.white.opacity(0.9))
                    .position(x: viewWidth / 2, y: max(0, baseY + dy))
                    .gesture(
                        DragGesture(minimumDistance: 0)
                            .onChanged { v in
                                activeSeam = idx
                                dragOffsets[idx] = v.translation.height
                            }
                            .onEnded { v in
                                activeSeam = nil
                                let scale = CGFloat(result.pixelHeight) / max(imageHeight, 1)
                                let deltaPixels = Int((v.translation.height * scale).rounded())
                                dragOffsets[idx] = nil
                                if deltaPixels != 0 {
                                    model.adjustCut(resultID: result.id,
                                                    seamIndex: idx,
                                                    deltaPixels: deltaPixels,
                                                    displayScale: 1)
                                }
                            }
                    )
            }
        }
    }
}

private struct SeamHandle: View {
    let color: Color

    var body: some View {
        ZStack {
            Rectangle()
                .fill(color)
                .frame(height: 2)
            Capsule()
                .fill(color)
                .frame(width: 46, height: 18)
                .overlay(
                    Image(systemName: "arrow.up.and.down")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Color.black.opacity(0.55))
                )
        }
        .frame(width: 200, height: 34)
        .contentShape(Rectangle())
    }
}

// MARK: - 设置

struct SettingsView: View {
    @EnvironmentObject private var model: SpliceModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color.white.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        sectionTitle("识别范围")
                        Picker("识别范围", selection: $model.windowMinutes) {
                            Text("最近 10 分钟").tag(10)
                            Text("最近 30 分钟").tag(30)
                            Text("最近 1 小时").tag(60)
                            Text("最近 3 小时").tag(180)
                        }
                        .pickerStyle(.segmented)
                        .padding(.bottom, 8)
                        Text("Splice 只在这个时间范围里找截图。")
                            .font(.system(size: 12))
                            .foregroundStyle(.tertiary)
                            .padding(.bottom, 26)

                        sectionTitle("顶部保留")
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
                        .tint(.black)
                        .padding(.bottom, 26)

                        sectionTitle("关于")
                        Text("Splice 会把最近的截图按时间顺序自动识别重叠部分，去掉重复后拼成一张长图。识别不出来时会在接缝处加一条细分隔线，你可以拖动接缝微调。")
                            .font(.system(size: 13))
                            .foregroundStyle(.secondary)
                            .lineSpacing(5)
                    }
                    .padding(.horizontal, 24)
                    .padding(.top, 8)
                }
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完成") { dismiss() }
                        .foregroundStyle(.black)
                }
            }
        }
    }

    private func sectionTitle(_ t: String) -> some View {
        Text(t)
            .font(.system(size: 11, weight: .semibold))
            .tracking(1.4)
            .foregroundStyle(.tertiary)
            .padding(.bottom, 10)
    }
}

#Preview {
    RootView().environmentObject(SpliceModel())
}
