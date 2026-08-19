#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_UI_POLISH_v0_3"
HISTORY_SCROLL_MARK = "AYU_HISTORY_SCROLL_v0_3"
CUSTOM_SECTION_MARK = "AYU_CUSTOM_ACTION_SECTION_v0_3"
GHOST_EXPANDABLE_MARK = "AYU_GHOST_EXPANDABLE_SWITCH_v0_3"
ASYNC_PERSIST_MARK = "AYU_DELETED_ASYNC_PERSIST_v0_3"
BAKED_ALPHA_MARK = "AYU_DELETED_BAKED_ALPHA_v0_3"
LOW_LATENCY_MARK = "AYU_DELETED_LOW_LATENCY_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def function_bounds(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"function anchor missing: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise RuntimeError(f"function opening brace missing: {signature}")
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return start, index + 1
    raise RuntimeError(f"function closing brace missing: {signature}")


def patch_async_deleted_persistence(root: Path) -> None:
    path = root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift"
    text = path.read_text(encoding="utf-8")

    if ASYNC_PERSIST_MARK not in text:
        state_anchor = "    private static let deletedState = Atomic<AyuDeletedState>(value: loadDeletedState())\n"
        state_new = state_anchor + '''\n    // AYU_DELETED_ASYNC_PERSIST_v0_3\n    // The Atomic is the source of truth for live UI. Persisting a potentially large\n    // deleted-id set must never block the AccountStateManager queue or chat layout.\n    private static let deletedPersistenceQueue = Queue(name: "ayu.deleted.persistence")\n'''
        text = one(text, state_anchor, state_new, "deleted persistence queue")

        persist_start, persist_end = function_bounds(text, "    private static func persistDeletedState(_ value: AyuDeletedState) {")
        persist_func = text[persist_start:persist_end]
        async_helper = '''\n\n    private static func persistDeletedStateAsync(_ value: AyuDeletedState) {\n        deletedPersistenceQueue.async {\n            persistDeletedState(value)\n        }\n    }'''
        text = text[:persist_end] + async_helper + text[persist_end:]

        sync_call = "            persistDeletedState(updated)\n"
        count = text.count(sync_call)
        if count < 3:
            raise RuntimeError(f"deleted persistence call anchors expected >= 3, found {count}")
        text = text.replace(sync_call, "            persistDeletedStateAsync(updated)\n")

    path.write_text(text, encoding="utf-8")


def patch_deleted_background_alpha(root: Path) -> None:
    path = root / "submodules/ChatMessageBackground/Sources/ChatMessageBackground.swift"
    text = path.read_text(encoding="utf-8")

    if BAKED_ALPHA_MARK not in text:
        cache_anchor = "    private static let ayuFillImageCache = NSCache<NSString, UIImage>()\n"
        cache_new = cache_anchor + '''\n    // AYU_DELETED_BAKED_ALPHA_v0_3\n    // Preserve Telegram's exact stock bubble artwork (including dark-theme and\n    // gradient fills) and bake only the requested alpha into a cached image.\n    public var ayuCustomImageAlpha: CGFloat?\n    private var ayuAppliedCustomImageAlpha: CGFloat?\n    private static let ayuAlphaImageCache = NSCache<NSString, UIImage>()\n'''
        text = one(text, cache_anchor, cache_new, "deleted alpha cache properties")

        fill_start, fill_end = function_bounds(text, "    private static func ayuFillImage(_ image: UIImage, color: UIColor) -> UIImage {")
        alpha_helper = r'''

    private static func ayuAlphaImage(_ image: UIImage, alpha: CGFloat) -> UIImage {
        let alphaKey = Int((alpha * 1000.0).rounded())
        let key = "\(ObjectIdentifier(image).hashValue):alpha:\(alphaKey)" as NSString
        if let cached = self.ayuAlphaImageCache.object(forKey: key) {
            return cached
        }
        let format = UIGraphicsImageRendererFormat()
        format.scale = image.scale
        format.opaque = false
        let renderer = UIGraphicsImageRenderer(size: image.size, format: format)
        let rendered = renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: image.size), blendMode: .normal, alpha: alpha)
        }
        let result: UIImage
        if image.capInsets == .zero {
            result = rendered
        } else {
            result = rendered.resizableImage(withCapInsets: image.capInsets, resizingMode: image.resizingMode)
        }
        self.ayuAlphaImageCache.setObject(result, forKey: key)
        return result
    }'''
        text = text[:fill_end] + alpha_helper + text[fill_end:]

        text = one(
            text,
            ", sameAyuFill {\n            return\n        }\n        self.ayuAppliedCustomFillColor = self.ayuCustomFillColor\n",
            ", sameAyuFill, self.ayuAppliedCustomImageAlpha == self.ayuCustomImageAlpha {\n            return\n        }\n        self.ayuAppliedCustomFillColor = self.ayuCustomFillColor\n        self.ayuAppliedCustomImageAlpha = self.ayuCustomImageAlpha\n",
            "deleted background fast-path alpha state",
        )

        outline_anchor = "        let outlineImage: UIImage?\n"
        alpha_apply = '''        if !highlighted, let ayuCustomImageAlpha = self.ayuCustomImageAlpha, let currentImage = image {\n            image = Self.ayuAlphaImage(currentImage, alpha: ayuCustomImageAlpha)\n        }\n\n'''
        text = one(text, outline_anchor, alpha_apply + outline_anchor, "deleted baked alpha application")

    path.write_text(text, encoding="utf-8")


def patch_deleted_bubble(root: Path) -> None:
    path = root / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
    text = path.read_text(encoding="utf-8")

    text = text.replace(
        "        let ayuDeletedVisible = AyuRuntimeSettings.isDeleted(item.message.id) && !AyuRuntimeSettings.isInDeletedViewer(item.message.id)\n",
        "        let ayuDeletedVisible = AyuRuntimeSettings.isDeleted(item.message.id)\n",
        1,
    )

    old = '''        strongSelf.backgroundNode.ayuCustomFillColor = ayuDeletedBackgroundColor\n        let ayuBackgroundMaskMode = ayuDeletedBackgroundColor == nil ? strongSelf.backgroundMaskMode : false\n        // Telegram-theme deleted messages keep the exact stock bubble image/color.\n        // Only the two bubble-background nodes are composited at 0.5; text, media,\n        // status and controls remain stock opacity. No image tint/cache work is used.\n        let ayuTelegramThemeDeleted = ayuDeletedVisible && ayuDeletedBackgroundColor == nil\n        strongSelf.backgroundNode.alpha = ayuTelegramThemeDeleted ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n        strongSelf.backgroundWallpaperNode.alpha = ayuTelegramThemeDeleted ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n'''
    new = '''        // AYU_DELETED_BAKED_ALPHA_v0_3: use one cached stock bubble image with\n        // alpha baked into its pixels. This avoids the dark-theme color shift caused\n        // by compositing both the normal and wallpaper bubble nodes at half alpha.\n        strongSelf.backgroundNode.ayuCustomFillColor = ayuDeletedBackgroundColor\n        strongSelf.backgroundNode.ayuCustomImageAlpha = ayuDeletedVisible ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : nil\n        let ayuBackgroundMaskMode = ayuDeletedBackgroundColor == nil ? strongSelf.backgroundMaskMode : false\n        strongSelf.backgroundNode.alpha = 1.0\n        strongSelf.backgroundWallpaperNode.alpha = ayuDeletedVisible ? 0.0 : 1.0\n'''
    if old in text:
        text = text.replace(old, new, 1)
    elif BAKED_ALPHA_MARK not in text:
        raise RuntimeError("deleted Telegram-theme alpha block missing")

    path.write_text(text, encoding="utf-8")


def patch_deleted_viewer(root: Path) -> None:
    path = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuDeletedMessagesController.swift"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "/// view filters the history to Ayu-marked ids and renders them at full opacity.\n",
        "/// view filters the history to Ayu-marked ids while keeping the same deleted styling as the ordinary chat.\n",
    )
    text = text.replace("        AyuRuntimeSettings.beginDeletedViewer(peerId: peerId)\n", "")
    deinit_block = '''\n    deinit {\n        AyuRuntimeSettings.endDeletedViewer(peerId: self.peerId)\n    }\n'''
    text = text.replace(deinit_block, "\n")
    path.write_text(text, encoding="utf-8")


def patch_low_latency_marker(root: Path) -> None:
    path = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    text = path.read_text(encoding="utf-8")
    if LOW_LATENCY_MARK not in text:
        anchor = '''            // Mark first, before touching Postbox, so the normal chat relayout sees\n            // the deleted state on its very first refresh.\n'''
        replacement = '''            // AYU_DELETED_LOW_LATENCY_v0_3\n            // Mark first, before touching Postbox. Persistence is asynchronous, so\n            // the only work before the one-shot history invalidation is O(number of\n            // ids in this delete event), with no timer, polling or frame-loop work.\n'''
        text = one(text, anchor, replacement, "low-latency deleted marker")
    path.write_text(text, encoding="utf-8")


def patch_ghost_settings(root: Path) -> None:
    path = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift"
    text = path.read_text(encoding="utf-8")

    if GHOST_EXPANDABLE_MARK not in text:
        old_header = '''        case let .header(title, _):\n            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: title, label: "", sectionId: self.section, style: .blocks, action: { arguments.toggleExpanded?() })\n'''
        new_header = r'''        case let .header(title, expanded):
            // AYU_GHOST_EXPANDABLE_SWITCH_v0_3
            let snapshot = AyuRuntimeSettings.snapshot
            let subItems: [ItemListExpandableSwitchItem.SubItem] = [
                ItemListExpandableSwitchItem.SubItem(id: AnyHashable("read"), title: "Не читать сообщения", isSelected: snapshot.hideReadMessages, isEnabled: true),
                ItemListExpandableSwitchItem.SubItem(id: AnyHashable("stories"), title: "Не отмечать просмотр историй", isSelected: snapshot.hideReadStories, isEnabled: true),
                ItemListExpandableSwitchItem.SubItem(id: AnyHashable("online"), title: "Скрывать онлайн", isSelected: snapshot.hideOnline, isEnabled: true),
                ItemListExpandableSwitchItem.SubItem(id: AnyHashable("typing"), title: "Скрывать «печатает…»", isSelected: snapshot.hideTyping, isEnabled: true),
                ItemListExpandableSwitchItem.SubItem(id: AnyHashable("offline"), title: "Автоматически офлайн", isSelected: snapshot.automaticOffline, isEnabled: true)
            ]
            return ItemListExpandableSwitchItem(
                presentationData: presentationData,
                systemStyle: .glass,
                title: title,
                value: snapshot.master,
                isExpanded: expanded,
                subItems: subItems,
                sectionId: self.section,
                style: .blocks,
                updated: { arguments.updateBool(.master, $0) },
                selectAction: { arguments.toggleExpanded?() },
                subAction: { item in
                    if item.id == AnyHashable("read") {
                        arguments.updateBool(.hideReadMessages, !item.isSelected)
                    } else if item.id == AnyHashable("stories") {
                        arguments.updateBool(.hideReadStories, !item.isSelected)
                    } else if item.id == AnyHashable("online") {
                        arguments.updateBool(.hideOnline, !item.isSelected)
                    } else if item.id == AnyHashable("typing") {
                        arguments.updateBool(.hideTyping, !item.isSelected)
                    } else if item.id == AnyHashable("offline") {
                        arguments.updateBool(.automaticOffline, !item.isSelected)
                    }
                }
            )
'''
        text = one(text, old_header, new_header, "Ghost expandable switch header")

        old_entries = r'''private func ayuGhostEntries(_ snapshot: AyuRuntimeSnapshot, expanded: Bool) -> [AyuGhostEntry] {
    let enabledCount = [snapshot.hideReadMessages, snapshot.hideReadStories, snapshot.hideOnline, snapshot.hideTyping, snapshot.automaticOffline].filter { $0 }.count
    var entries: [AyuGhostEntry] = [
        .header("Режим призрака \(enabledCount)/5", expanded)
    ]
    if expanded {
        entries.append(contentsOf: [
            .master("Включить режим призрака", snapshot.master),
            .read(snapshot.hideReadMessages),
            .stories(snapshot.hideReadStories),
            .online(snapshot.hideOnline),
            .typing(snapshot.hideTyping),
            .automaticOffline(snapshot.automaticOffline),
            .actionsHeader,
            .readOnActions(snapshot.readOnActions),
            .useScheduled(snapshot.useScheduled),
            .useScheduledInfo
        ])
    }
    return entries
}
'''
        new_entries = r'''private func ayuGhostEntries(_ snapshot: AyuRuntimeSnapshot, expanded: Bool) -> [AyuGhostEntry] {
    let enabledCount = [snapshot.hideReadMessages, snapshot.hideReadStories, snapshot.hideOnline, snapshot.hideTyping, snapshot.automaticOffline].filter { $0 }.count
    return [
        .header("Режим призрака \(enabledCount)/5", expanded),
        .actionsHeader,
        .readOnActions(snapshot.readOnActions),
        .useScheduled(snapshot.useScheduled),
        .useScheduledInfo
    ]
}
'''
        text = one(text, old_entries, new_entries, "Ghost actions outside dropdown")

    text = text.replace(
        'return ItemListTextItem(presentationData: presentationData, text: .markdown("Использует отложенную отправку, когда это требуется режиму призрака."), sectionId: self.section)',
        'return ItemListTextItem(presentationData: presentationData, text: .markdown("Сообщения отправляются без краткого выхода в онлайн."), sectionId: self.section)',
        1,
    )

    path.write_text(text, encoding="utf-8")

    enqueue = root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift"
    source = enqueue.read_text(encoding="utf-8")
    pulse_signature = "public func ayuGhostOnlinePulse(account: Account) {\n"
    if "AYU_GHOST_SCHEDULED_NO_PULSE_v0_3" not in source:
        pulse_guard = pulse_signature + '''    // AYU_GHOST_SCHEDULED_NO_PULSE_v0_3\n    // "Использовать отложку" means sending must not briefly advertise online.\n    // Ghost already suppresses normal presence; this removes the explicit 0.2 s pulse.\n    if AyuRuntimeSettings.snapshot.master && AyuRuntimeSettings.snapshot.useScheduled {\n        return\n    }\n'''
        source = one(source, pulse_signature, pulse_guard, "scheduled Ghost send pulse guard")
    enqueue.write_text(source, encoding="utf-8")


def history_scroll_content() -> str:
    return r'''// AYU_HISTORY_SCROLL_v0_3
private final class AyuWeakContextControllerBox {
    weak var value: ContextControllerProtocol?
}

private final class AyuEditHistoryContextContent: ContextControllerItemsContent {
    private final class ItemsNode: ASDisplayNode, ContextControllerItemsNode {
        private let rows: [String]
        private let backAction: () -> Void
        private let scrollNode: ASScrollNode
        private let backButton: HighlightTrackingButtonNode
        private let backTitleNode: ImmediateTextNode
        private let backIconNode: ASImageNode
        private let rowNodes: [ImmediateTextNode]
        private let separatorNodes: [ASDisplayNode]

        private(set) var apparentHeight: CGFloat = 0.0

        init(rows: [String], backAction: @escaping () -> Void) {
            self.rows = rows
            self.backAction = backAction
            self.scrollNode = ASScrollNode()
            self.backButton = HighlightTrackingButtonNode()
            self.backTitleNode = ImmediateTextNode()
            self.backIconNode = ASImageNode()
            self.rowNodes = rows.map { _ in
                let node = ImmediateTextNode()
                node.maximumNumberOfLines = 0
                node.isUserInteractionEnabled = false
                return node
            }
            self.separatorNodes = rows.map { _ in ASDisplayNode() }

            super.init()

            self.scrollNode.canCancelAllTouchesInViews = true
            self.scrollNode.view.delaysContentTouches = false
            self.scrollNode.view.showsVerticalScrollIndicator = true
            self.scrollNode.view.scrollsToTop = false
            if #available(iOS 11.0, *) {
                self.scrollNode.view.contentInsetAdjustmentBehavior = .never
            }
            self.addSubnode(self.scrollNode)

            self.backTitleNode.isUserInteractionEnabled = false
            self.backIconNode.isUserInteractionEnabled = false
            self.scrollNode.addSubnode(self.backButton)
            self.backButton.addSubnode(self.backTitleNode)
            self.backButton.addSubnode(self.backIconNode)
            self.backButton.addTarget(self, action: #selector(self.backPressed), forControlEvents: .touchUpInside)

            for index in 0 ..< self.rowNodes.count {
                self.scrollNode.addSubnode(self.rowNodes[index])
                self.scrollNode.addSubnode(self.separatorNodes[index])
            }
        }

        @objc private func backPressed() {
            self.backAction()
        }

        func update(presentationData: PresentationData, constrainedWidth: CGFloat, maxHeight: CGFloat, bottomInset: CGFloat, transition: ContainedViewLayoutTransition) -> (cleanSize: CGSize, apparentHeight: CGFloat) {
            let width = min(360.0, constrainedWidth)
            let sideInset: CGFloat = 18.0
            let backHeight: CGFloat = 54.0
            let fontSize = floor(presentationData.listsFontSize.baseDisplaySize * 14.0 / 17.0)

            self.backTitleNode.attributedText = NSAttributedString(string: "Назад", font: Font.regular(presentationData.listsFontSize.baseDisplaySize), textColor: presentationData.theme.contextMenu.primaryColor)
            let backTitleSize = self.backTitleNode.updateLayout(CGSize(width: width - 82.0, height: 100.0))
            self.backTitleNode.frame = CGRect(origin: CGPoint(x: 60.0, y: floor((backHeight - backTitleSize.height) * 0.5)), size: backTitleSize)
            self.backIconNode.image = generateTintedImage(image: UIImage(bundleImageName: "Chat/Context Menu/Back"), color: presentationData.theme.contextMenu.primaryColor)
            if let icon = self.backIconNode.image {
                self.backIconNode.frame = CGRect(origin: CGPoint(x: 23.0, y: floor((backHeight - icon.size.height) * 0.5)), size: icon.size)
            }
            self.backButton.frame = CGRect(origin: .zero, size: CGSize(width: width, height: backHeight))

            var y = backHeight
            for index in 0 ..< self.rows.count {
                let node = self.rowNodes[index]
                node.attributedText = NSAttributedString(string: self.rows[index], font: Font.regular(fontSize), textColor: presentationData.theme.contextMenu.primaryColor)
                let textSize = node.updateLayout(CGSize(width: max(1.0, width - sideInset * 2.0), height: 10000.0))
                let rowHeight = max(54.0, ceil(textSize.height) + 22.0)
                node.frame = CGRect(origin: CGPoint(x: sideInset, y: y + 11.0), size: textSize)

                let separator = self.separatorNodes[index]
                separator.backgroundColor = presentationData.theme.contextMenu.itemSeparatorColor
                separator.frame = CGRect(origin: CGPoint(x: sideInset, y: y + rowHeight - UIScreenPixel), size: CGSize(width: max(0.0, width - sideInset * 2.0), height: UIScreenPixel))
                separator.isHidden = index == self.rows.count - 1
                y += rowHeight
            }

            let contentHeight = y
            let height = min(maxHeight, contentHeight)
            let size = CGSize(width: width, height: height)
            self.scrollNode.frame = CGRect(origin: .zero, size: size)
            self.scrollNode.view.contentInset.bottom = bottomInset
            self.scrollNode.view.contentSize = CGSize(width: width, height: contentHeight)
            self.scrollNode.view.alwaysBounceVertical = contentHeight > height
            self.apparentHeight = height
            return (size, height)
        }
    }

    private let rows: [String]
    private let backAction: () -> Void

    init(message: EngineRawMessage, revisions: [AyuSpyEditRevision], backAction: @escaping () -> Void) {
        var rows: [String] = []
        for (index, revision) in revisions.enumerated() {
            let title = index == 0 ? "Исходный текст" : "Версия \(index + 1)"
            rows.append("\(title) · до \(ayuDetailsDate(revision.editedAt))\n\(revision.previousText)")
        }
        rows.append("Текущая версия\n\(message.text)")
        self.rows = rows
        self.backAction = backAction
    }

    func node(requestUpdate: @escaping (ContainedViewLayoutTransition) -> Void, requestUpdateApparentHeight: @escaping (ContainedViewLayoutTransition) -> Void) -> ContextControllerItemsNode {
        return ItemsNode(rows: self.rows, backAction: self.backAction)
    }
}

'''


def patch_context_menu(root: Path) -> None:
    path = root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
    text = path.read_text(encoding="utf-8")

    if HISTORY_SCROLL_MARK not in text:
        anchor = "private struct MessageContextMenuData {\n"
        text = one(text, anchor, history_scroll_content() + anchor, "scrollable edit history content")

    history_old = r'''                actions.append(.action(ContextMenuActionItem(text: "История", icon: { _ in nil }, action: { controller, _ in
                    guard let controller else {
                        return
                    }
                    let historyItems = ayuEditHistoryMenuItems(message: ayuHistoryMessage, revisions: ayuHistory)
                    controller.pushItems(items: .single(ContextController.Items(content: .list(historyItems))))
                })))
'''
    history_new = r'''                actions.append(.action(ContextMenuActionItem(text: "История", icon: { theme in
                    return generateTintedImage(image: UIImage(bundleImageName: "Chat/Context Menu/Copy"), color: theme.actionSheet.primaryTextColor)
                }, action: { controller, _ in
                    guard let controller else {
                        return
                    }
                    let controllerBox = AyuWeakContextControllerBox()
                    controllerBox.value = controller
                    let historyContent = AyuEditHistoryContextContent(message: ayuHistoryMessage, revisions: ayuHistory, backAction: { [controllerBox] in
                        controllerBox.value?.popItems()
                    })
                    controller.pushItems(items: .single(ContextController.Items(content: .custom(historyContent))))
                })))
'''
    if history_old in text:
        text = text.replace(history_old, history_new, 1)
    elif "Context Menu/Copy" not in text or "AyuEditHistoryContextContent" not in text:
        raise RuntimeError("History action anchor missing")

    if CUSTOM_SECTION_MARK not in text:
        history_marker = "        // AYU_REQUESTED_UI_HISTORY_v0_3\n"
        text = one(
            text,
            history_marker,
            "        // AYU_CUSTOM_ACTION_SECTION_v0_3\n        var ayuCustomActionsStarted = false\n" + history_marker,
            "custom action section state",
        )

    section_separator = '''            if !ayuCustomActionsStarted {\n                if !actions.isEmpty {\n                    actions.append(.separator)\n                }\n                ayuCustomActionsStarted = true\n            }\n'''

    # Replace one separator block in each Ayu action region. The first action that
    # actually exists starts the custom section; later Ayu actions stay contiguous.
    regions = [
        ("        // AYU_REQUESTED_UI_HISTORY_v0_3\n", "        if AyuRuntimeSettings.suppressReadMessages"),
        ("        if AyuRuntimeSettings.suppressReadMessages", "        // AYU_VIEW_ONCE_BURN_v0_3\n"),
        ("        // AYU_VIEW_ONCE_BURN_v0_3\n", "        // AYU_SPY_DETAILS_v0_3\n"),
        ("        // AYU_SPY_DETAILS_v0_3\n", "        return ContextController.Items(content: .list(actions), tip: nil)\n"),
    ]
    old_separator = '''            if !actions.isEmpty {\n                actions.append(.separator)\n            }\n'''
    for start_anchor, end_anchor in regions:
        start = text.find(start_anchor)
        end = text.find(end_anchor, start + len(start_anchor))
        if start < 0 or end < 0:
            raise RuntimeError(f"custom action region missing: {start_anchor.strip()}")
        region = text[start:end]
        if section_separator not in region:
            if old_separator not in region:
                raise RuntimeError(f"custom action separator anchor missing: {start_anchor.strip()}")
            region = region.replace(old_separator, section_separator, 1)
            text = text[:start] + region + text[end:]

    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_ui_polish_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    patch_async_deleted_persistence(root)
    patch_deleted_background_alpha(root)
    patch_deleted_bubble(root)
    patch_deleted_viewer(root)
    patch_low_latency_marker(root)
    patch_ghost_settings(root)
    patch_context_menu(root)

    manager_path = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    manager = manager_path.read_text(encoding="utf-8")
    if MARK not in manager:
        manager = "// AYU_UI_POLISH_v0_3\n" + manager
        manager_path.write_text(manager, encoding="utf-8")

    print("[ayu-ui-polish] scrollable History + one Ayu menu section + expandable Ghost switch + dark-theme deleted alpha + low-latency persistence installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
